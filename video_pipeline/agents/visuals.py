"""Visual Generator Agent - Creates video frames using AI image generation.

Generates all visual frames for a video based on the script's scene
descriptions. Uses Replicate (Flux/SDXL) for high-quality 3D animated
visuals, with a Pillow-based fallback for zero-cost operation.

Each scene generates one AI image that is duplicated across all frames
for that scene's duration (at the configured FPS). This keeps costs
manageable (~1 API call per scene) while producing smooth, professional
3D-animated children's content.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import (
    PipelineContext,
    Script,
    ScriptScene,
    VisualAsset,
    VideoType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style prompt templates per video type
# ---------------------------------------------------------------------------

VIDEO_TYPE_STYLES: dict[str, str] = {
    "counting": (
        "cute 3D animated scene for toddlers, "
        "large colorful number displayed prominently, "
        "adorable cartoon objects arranged neatly, "
        "soft pastel nursery background, playful atmosphere"
    ),
    "colors": (
        "cute 3D animated scene for toddlers, "
        "single vibrant color theme filling the scene, "
        "adorable 3D objects in that color, "
        "soft gradient background, cheerful and bright"
    ),
    "shapes": (
        "cute 3D animated scene for toddlers, "
        "large friendly 3D shape floating in center, "
        "colorful playroom background, "
        "soft shadows, educational toy aesthetic"
    ),
    "alphabet": (
        "cute 3D animated scene for toddlers, "
        "large colorful 3D letter on the left, "
        "adorable 3D cartoon object on the right, "
        "bright cheerful nursery background"
    ),
    "animals": (
        "cute 3D animated scene for toddlers, "
        "adorable friendly cartoon animal character, "
        "big expressive eyes, rounded body, "
        "colorful farm or nature background, "
        "Pixar-style character design"
    ),
    "lullaby": (
        "dreamy soft 3D animated night scene, "
        "gentle moonlight, twinkling stars, "
        "sleeping baby animals, soft clouds, "
        "calming purple and blue color palette, "
        "serene peaceful atmosphere"
    ),
    "nursery_rhyme": (
        "cute 3D animated storybook scene, "
        "colorful cartoon characters acting out the lyrics, "
        "bright cheerful background, "
        "whimsical fairy-tale atmosphere"
    ),
    "anime_dance": (
        "anime-style neon cityscape at night, "
        "vibrant neon signs glowing pink cyan and purple, "
        "stylish anime character dancing, "
        "wet reflective streets, cinematic lighting"
    ),
}

# Element-specific prompt fragments
ELEMENT_PROMPTS: dict[str, str] = {
    "number": "a large, bold, colorful 3D number '{value}' as the centerpiece",
    "letter": "a large, bold, colorful 3D letter '{value}' prominently displayed",
    "animal": "a cute, friendly, round 3D cartoon {value} with big eyes and a smile",
    "shape": "a large, colorful, smooth 3D {value} shape floating with soft shadows",
    "color_display": "everything in the scene is {value} colored, showcasing the color {value}",
    "color_swatch": "a beautiful display of the color {value}, with {value} colored 3D objects",
    "lullaby_visual": "soft dreamy nighttime scene with gentle stars and a crescent moon",
    "nursery_visual": "bright cheerful storybook illustration style",
    "neon_cityscape": "dense Tokyo cityscape at night with glowing neon signs",
    "dancer_silhouette": "anime character in a dynamic {value} dance pose",
    "neon_reflection": "wet street reflecting neon lights in vibrant colors",
}

# Alphabet object mapping for richer prompts
ALPHABET_OBJECTS: dict[str, str] = {
    "A": "a shiny red 3D apple",
    "B": "a bouncy colorful 3D ball",
    "C": "an adorable 3D cartoon cat",
    "D": "a cute 3D cartoon puppy dog",
    "E": "a friendly grey 3D cartoon elephant",
    "F": "a colorful 3D tropical fish",
    "G": "a bunch of purple 3D grapes",
    "H": "a colorful 3D party hat",
    "I": "a delicious 3D ice cream cone",
    "J": "a wobbly 3D cup of colorful juice",
    "K": "a colorful 3D kite flying",
    "L": "a majestic 3D cartoon lion with fluffy mane",
    "M": "a glowing 3D crescent moon",
    "N": "a cozy 3D bird's nest with eggs",
    "O": "a bright 3D orange fruit",
    "P": "a cute 3D cartoon penguin",
    "Q": "a regal 3D cartoon queen with crown",
    "R": "a beautiful 3D rainbow arc",
    "S": "a glowing 3D golden star",
    "T": "a cute 3D cartoon turtle",
    "U": "a colorful 3D open umbrella",
    "V": "a shiny 3D wooden violin",
    "W": "a friendly 3D cartoon blue whale",
    "X": "a colorful 3D toy xylophone",
    "Y": "a ball of colorful 3D yarn",
    "Z": "a cute 3D cartoon zebra with stripes",
}


def _build_scene_prompt(
    scene: ScriptScene,
    video_type: str,
    style_prefix: str,
) -> str:
    """Build a complete image generation prompt from a scene."""
    parts: list[str] = [style_prefix.rstrip(", ")]

    # Add video-type-specific style
    type_style = VIDEO_TYPE_STYLES.get(video_type, "")
    if type_style:
        parts.append(type_style)

    # Build element-specific descriptions
    for element in scene.elements:
        etype = element.get("type", "")
        value = str(element.get("value", ""))

        template = ELEMENT_PROMPTS.get(etype)
        if template:
            parts.append(template.format(value=value))

        # For alphabet, add the specific object
        if etype == "letter" and value.upper() in ALPHABET_OBJECTS:
            parts.append(ALPHABET_OBJECTS[value.upper()])

        # For counting, describe the objects
        if etype == "object":
            count = element.get("count", 1)
            parts.append(
                f"{count} cute 3D cartoon {value} arranged in the scene"
            )

    # Use the visual_description as additional context
    if scene.visual_description:
        parts.append(scene.visual_description)

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Pillow fallback helpers (kept for zero-cost mode)
# ---------------------------------------------------------------------------

BRIGHT_COLORS: list[str] = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempt to load a TrueType font, falling back to the default bitmap font."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _contrasting_text_color(hex_bg: str) -> str:
    """Return black or white text depending on background luminance."""
    hex_bg = hex_bg.lstrip("#")
    if len(hex_bg) != 6:
        return "#000000"
    r, g, b = int(hex_bg[:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.5 else "#FFFFFF"


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

class VisualGeneratorAgent(BaseAgent):
    """Generates video frames using AI image generation (Replicate Flux/SDXL).

    For each scene, generates one high-quality AI image using Replicate,
    then duplicates it across all frames for that scene's duration at the
    configured FPS. Falls back to Pillow-based rendering if Replicate is
    unavailable.

    Output: ``<output_dir>/<video_id>/frames/frame_NNNNN.png``
    """

    @property
    def name(self) -> str:
        return "visuals"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.VISUALS_GENERATED

    # ------------------------------------------------------------------ #
    # Main execution
    # ------------------------------------------------------------------ #

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Read the script, generate images, and populate *context.visuals*."""
        script: Script | None = context.script
        if script is None:
            raise ValueError(
                "No script found in context -- the scriptwriter agent must run first"
            )

        width, height = self.config.visual.resolution
        fps: int = self.config.visual.fps

        # Prepare output directories
        base_dir = Path(self.config.output_dir) / context.video_id
        frame_dir = self._ensure_dir(base_dir / "frames")

        # Determine engine
        engine = getattr(self.config.visual, "engine", "pillow")
        api_token = (
            getattr(self.config.visual, "replicate_api_token", "")
            or os.environ.get("REPLICATE_API_TOKEN", "")
        )

        use_ai = engine == "replicate" and bool(api_token)

        if use_ai:
            self.logger.info(
                "Using Replicate AI for %s (%d scenes, %dx%d @ %d fps)",
                context.video_id,
                len(script.scenes),
                width,
                height,
                fps,
            )
        else:
            if engine == "replicate" and not api_token:
                self.logger.warning(
                    "Replicate API token not set. Falling back to Pillow. "
                    "Set REPLICATE_API_TOKEN env var or replicate_api_token in config."
                )
            self.logger.info(
                "Using Pillow fallback for %s (%d scenes, %dx%d @ %d fps)",
                context.video_id,
                len(script.scenes),
                width,
                height,
                fps,
            )

        total_frames = 0
        for scene_idx, scene in enumerate(script.scenes):
            if use_ai:
                rendered = await self._render_scene_ai(
                    scene, script, frame_dir, fps, total_frames,
                    width, height, api_token,
                )
            else:
                rendered = self._render_scene_pillow(
                    scene, frame_dir, fps, total_frames,
                )
            total_frames += rendered

        # Generate thumbnail
        thumbnail_path = await self._generate_thumbnail(
            script, base_dir, use_ai, api_token,
        )

        context.visuals = VisualAsset(
            video_id=context.video_id,
            frame_dir=frame_dir,
            frame_count=total_frames,
            fps=fps,
            resolution=(width, height),
            thumbnail_path=thumbnail_path,
        )

        self.logger.info(
            "Visual generation complete: %d frames, thumbnail at %s",
            total_frames,
            thumbnail_path,
        )
        return context

    # ------------------------------------------------------------------ #
    # AI-powered scene rendering (Replicate)
    # ------------------------------------------------------------------ #

    async def _render_scene_ai(
        self,
        scene: ScriptScene,
        script: Script,
        frame_dir: Path,
        fps: int,
        frame_offset: int,
        width: int,
        height: int,
        api_token: str,
    ) -> int:
        """Generate one AI image for the scene and duplicate across frames."""
        num_frames = max(1, int(scene.duration_seconds * fps))

        # Build the prompt
        style_prefix = getattr(self.config.visual, "style_prefix", "")
        video_type = script.video_type.value
        prompt = _build_scene_prompt(scene, video_type, style_prefix)

        self.logger.info(
            "Scene %d: generating AI image (%d frames, %.1fs)",
            scene.scene_number,
            num_frames,
            scene.duration_seconds,
        )
        self.logger.debug("Prompt: %s", prompt[:200])

        # Generate image via Replicate
        try:
            img = await self._generate_replicate_image(
                prompt, width, height, api_token,
            )
        except Exception as e:
            self.logger.error(
                "Replicate generation failed for scene %d: %s. "
                "Falling back to Pillow for this scene.",
                scene.scene_number,
                e,
            )
            return self._render_scene_pillow(
                scene, frame_dir, fps, frame_offset,
            )

        # Save the AI image as all frames for this scene
        for i in range(num_frames):
            frame_index = frame_offset + i
            filename = f"frame_{frame_index:05d}.png"
            img.save(frame_dir / filename)

        self.logger.debug(
            "Scene %d: saved %d frames from AI image",
            scene.scene_number,
            num_frames,
        )
        return num_frames

    async def _generate_replicate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        api_token: str,
    ) -> Image.Image:
        """Call Replicate API to generate a single image."""
        import replicate

        # Set the API token
        os.environ["REPLICATE_API_TOKEN"] = api_token

        model = getattr(
            self.config.visual,
            "replicate_model",
            "black-forest-labs/flux-1.1-pro",
        )
        negative = getattr(self.config.visual, "negative_prompt", "")

        # Determine aspect ratio string from resolution
        aspect_ratio = self._get_aspect_ratio(width, height)

        # Build input params based on model
        input_params: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }

        # Add width/height for models that support it
        if "flux" not in model.lower():
            input_params["width"] = width
            input_params["height"] = height
            if negative:
                input_params["negative_prompt"] = negative

        self.logger.debug("Calling Replicate model: %s", model)

        # Run prediction (this blocks until complete)
        output = await asyncio.to_thread(
            replicate.run,
            model,
            input=input_params,
        )

        # Output is typically a URL or list of URLs
        if isinstance(output, list):
            image_url = str(output[0])
        elif hasattr(output, "url"):
            image_url = str(output.url)
        else:
            image_url = str(output)

        # Download the generated image
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()

        img = Image.open(BytesIO(response.content)).convert("RGB")

        # Resize to exact resolution if needed
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)

        return img

    @staticmethod
    def _get_aspect_ratio(width: int, height: int) -> str:
        """Convert resolution to an aspect ratio string for Flux models."""
        ratio = width / height
        # Common aspect ratios
        if abs(ratio - 16 / 9) < 0.05:
            return "16:9"
        elif abs(ratio - 9 / 16) < 0.05:
            return "9:16"
        elif abs(ratio - 4 / 3) < 0.05:
            return "4:3"
        elif abs(ratio - 3 / 4) < 0.05:
            return "3:4"
        elif abs(ratio - 1.0) < 0.05:
            return "1:1"
        else:
            return "16:9"  # Default to widescreen

    # ------------------------------------------------------------------ #
    # AI thumbnail generation
    # ------------------------------------------------------------------ #

    async def _generate_thumbnail(
        self,
        script: Script,
        base_dir: Path,
        use_ai: bool,
        api_token: str,
    ) -> Path:
        """Generate a thumbnail, using AI if available."""
        thumb_path = base_dir / "thumbnail.png"

        if use_ai:
            try:
                title = script.title or "Baby Learning Video"
                style_prefix = getattr(self.config.visual, "style_prefix", "")
                video_type = script.video_type.value
                type_style = VIDEO_TYPE_STYLES.get(video_type, "")

                prompt = (
                    f"{style_prefix} {type_style}, "
                    f"YouTube video thumbnail for '{title}', "
                    "eye-catching, vibrant, centered composition, "
                    "no text, no words, no letters"
                )

                img = await self._generate_replicate_image(
                    prompt, 1280, 720, api_token,
                )
                img.save(thumb_path)
                self.logger.info("AI thumbnail saved: %s", thumb_path)
                return thumb_path
            except Exception as e:
                self.logger.warning(
                    "AI thumbnail failed: %s. Using Pillow fallback.", e,
                )

        # Pillow fallback thumbnail
        return self._generate_thumbnail_pillow(script, base_dir)

    # ------------------------------------------------------------------ #
    # Pillow fallback rendering (original basic shapes/text)
    # ------------------------------------------------------------------ #

    def _render_scene_pillow(
        self,
        scene: ScriptScene,
        frame_dir: Path,
        fps: int,
        frame_offset: int = 0,
    ) -> int:
        """Render all frames for a single scene using Pillow (fallback)."""
        num_frames = max(1, int(scene.duration_seconds * fps))
        width, height = self.config.visual.resolution

        img = self._render_frame_pillow(scene, width, height)

        for i in range(num_frames):
            frame_index = frame_offset + i
            filename = f"frame_{frame_index:05d}.png"
            img.save(frame_dir / filename)

        self.logger.debug(
            "Scene %d: rendered %d Pillow frames (%.1fs)",
            scene.scene_number,
            num_frames,
            scene.duration_seconds,
        )
        return num_frames

    def _render_frame_pillow(
        self, scene: ScriptScene, width: int, height: int
    ) -> Image.Image:
        """Create a single PIL Image for the given scene (fallback mode)."""
        bg_color = scene.background_color or "#FFFFFF"
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        if not scene.elements:
            if scene.visual_description:
                self._draw_centred_text(
                    draw, scene.visual_description, width, height,
                    font_size=60, fill=_contrasting_text_color(bg_color),
                )
            return img

        for element in scene.elements:
            etype: str = element.get("type", "")
            renderer = self._pillow_renderers().get(etype)
            if renderer is not None:
                renderer(draw, img, element, width, height, scene)

        return img

    def _pillow_renderers(self) -> dict[str, Any]:
        """Map of element type -> Pillow renderer callable."""
        return {
            "title": self._render_title,
            "text": self._render_title,
            "number": self._render_number,
            "color_display": self._render_color_display,
            "color_swatch": self._render_color_display,
            "shape": self._render_shape,
            "letter": self._render_letter,
            "animal": self._render_animal,
            "text_overlay": self._render_text_overlay,
            "lullaby_visual": self._render_lullaby_visual,
            "nursery_visual": self._render_nursery_visual,
        }

    # ------------------------------------------------------------------ #
    # Pillow element renderers (kept as fallback)
    # ------------------------------------------------------------------ #

    def _render_title(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        text: str = element.get("value", element.get("text", "Title"))
        color: str = element.get("color", scene.background_color or "#4ECDC4")
        img.paste(Image.new("RGB", (width, height), color), (0, 0))
        draw = ImageDraw.Draw(img)
        text_color = _contrasting_text_color(color)
        self._draw_centred_text(draw, text, width, height, font_size=100, fill=text_color)

    def _render_number(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        number_text: str = str(element.get("value", "1"))
        color: str = element.get("color", "#FF6B6B")
        count = int(element.get("value", 1))
        font_large = _load_font(200)
        bbox = draw.textbbox((0, 0), number_text, font=font_large)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((width - tw) / 2, (height - th) / 2 - 40),
            number_text, fill=color, font=font_large,
        )
        obj_radius = 25
        positions = self._distribute_objects(count, width, height, margin=120, avoid_centre=True)
        for px, py in positions:
            draw.ellipse(
                [px - obj_radius, py - obj_radius, px + obj_radius, py + obj_radius],
                fill=color, outline="#000000", width=2,
            )

    def _render_color_display(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        color_name: str = element.get("value", "red")
        hex_color: str = element.get("color", "#FF0000")
        img.paste(Image.new("RGB", (width, height), hex_color), (0, 0))
        draw = ImageDraw.Draw(img)
        text_color = _contrasting_text_color(hex_color)
        self._draw_centred_text(draw, color_name.upper(), width, height, font_size=140, fill=text_color)

    def _render_shape(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        shape_name: str = element.get("value", "circle").lower()
        fill_color: str = element.get("color", "#E74C3C")
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.25
        # Simple circle fallback for all shapes
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=fill_color, outline="#000000", width=3,
        )
        label_font = _load_font(60)
        label = shape_name.upper()
        lbox = draw.textbbox((0, 0), label, font=label_font)
        lw = lbox[2] - lbox[0]
        draw.text(((width - lw) / 2, cy + radius + 40), label, fill="#333333", font=label_font)

    def _render_letter(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        letter: str = str(element.get("value", "A")).upper()
        color: str = element.get("color", "#3498DB")
        font_big = _load_font(240)
        bbox = draw.textbbox((0, 0), letter, font=font_big)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((width - tw) / 2, (height - th) / 2 - 80), letter, fill=color, font=font_big)

    def _render_animal(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        animal_name: str = element.get("value", "cat")
        color: str = element.get("color", "#DAA520")
        cx, cy = width / 2, height / 2 - 60
        radius = min(width, height) * 0.18
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=color, outline="#333333", width=4,
        )
        eye_r = radius * 0.12
        eye_y = cy - radius * 0.15
        for ex in (cx - radius * 0.3, cx + radius * 0.3):
            draw.ellipse(
                [ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
                fill="#FFFFFF", outline="#000000", width=1,
            )
        font_label = _load_font(72)
        label = animal_name.upper()
        lbox = draw.textbbox((0, 0), label, font=font_label)
        lw = lbox[2] - lbox[0]
        draw.text(((width - lw) / 2, cy + radius + 40), label, fill="#333333", font=font_label)

    def _render_text_overlay(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        text: str = element.get("value", element.get("text", ""))
        if not text:
            return
        font = _load_font(48)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        bar_height = th + 40
        bar_y = height - bar_height
        draw.rectangle([0, bar_y, width, height], fill="#000000AA")
        draw.text(((width - tw) / 2, bar_y + 20), text, fill="#FFFFFF", font=font)

    def _render_lullaby_visual(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        for y in range(height):
            ratio = y / height
            r = int(10 + 20 * ratio)
            g = int(10 + 10 * ratio)
            b = int(40 + 40 * (1 - ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        num_stars = random.randint(40, 80)
        for _ in range(num_stars):
            sx = random.randint(0, width)
            sy = random.randint(0, height)
            sr = random.randint(2, 6)
            brightness = random.randint(180, 255)
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(brightness, brightness, int(brightness * 0.9)))
        text: str = element.get("value", element.get("text", ""))
        if text:
            self._draw_centred_text(draw, text, width, height, font_size=72, fill="#FFFDE7")

    def _render_nursery_visual(
        self, draw: ImageDraw.ImageDraw, img: Image.Image,
        element: dict[str, Any], width: int, height: int,
        scene: ScriptScene,
    ) -> None:
        bg = element.get("color", random.choice(BRIGHT_COLORS))
        img.paste(Image.new("RGB", (width, height), bg), (0, 0))
        draw = ImageDraw.Draw(img)
        text: str = element.get("value", element.get("text", scene.visual_description))
        if text:
            text_color = _contrasting_text_color(bg)
            self._draw_centred_text(draw, text, width, height, font_size=72, fill=text_color)

    # ------------------------------------------------------------------ #
    # Pillow thumbnail fallback
    # ------------------------------------------------------------------ #

    def _generate_thumbnail_pillow(self, script: Script, base_dir: Path) -> Path:
        """Create a 1280x720 thumbnail with Pillow (fallback)."""
        thumb_w, thumb_h = 1280, 720
        bg_color = random.choice(BRIGHT_COLORS)
        img = Image.new("RGB", (thumb_w, thumb_h), bg_color)
        draw = ImageDraw.Draw(img)
        title = script.title or "Baby Learning Video"
        text_color = _contrasting_text_color(bg_color)
        self._draw_centred_text(draw, title, thumb_w, thumb_h, font_size=80, fill=text_color)
        thumb_path = base_dir / "thumbnail.png"
        img.save(thumb_path)
        self.logger.info("Pillow thumbnail saved: %s", thumb_path)
        return thumb_path

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #

    def _draw_centred_text(
        self, draw: ImageDraw.ImageDraw, text: str,
        width: int, height: int, font_size: int = 60,
        fill: str = "#000000",
    ) -> None:
        """Draw *text* centred on the canvas, wrapping if necessary."""
        font = _load_font(font_size)
        max_text_width = int(width * 0.9)
        lines = self._wrap_text(draw, text, font, max_text_width)
        line_heights: list[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_heights.append(bbox[3] - bbox[1])
        spacing = 10
        total_h = sum(line_heights) + spacing * (len(lines) - 1)
        y = (height - total_h) / 2
        for line, lh in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            draw.text(((width - lw) / 2, y), line, fill=fill, font=font)
            y += lh + spacing

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        """Word-wrap *text* so that each line fits within *max_width* pixels."""
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current_line = words[0]
        for word in words[1:]:
            test_line = f"{current_line} {word}"
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines

    @staticmethod
    def _distribute_objects(
        count: int, width: int, height: int,
        margin: int = 100, avoid_centre: bool = False,
    ) -> list[tuple[int, int]]:
        """Return *count* (x, y) positions spread across the canvas."""
        positions: list[tuple[int, int]] = []
        centre_x_min = width * 0.33
        centre_x_max = width * 0.67
        centre_y_min = height * 0.25
        centre_y_max = height * 0.75
        attempts = 0
        while len(positions) < count and attempts < count * 20:
            x = random.randint(margin, width - margin)
            y = random.randint(margin, height - margin)
            if avoid_centre and (
                centre_x_min < x < centre_x_max
                and centre_y_min < y < centre_y_max
            ):
                attempts += 1
                continue
            positions.append((x, y))
            attempts += 1
        return positions

    # ------------------------------------------------------------------ #
    # Checkpoint validation
    # ------------------------------------------------------------------ #

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Accept checkpoint only when visuals are already present."""
        return data.get("visuals") is not None
