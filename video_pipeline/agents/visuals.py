"""Visual Generator Agent - Creates video frames using Pillow (PIL).

Generates all visual frames for a video based on the script's scene
descriptions. Uses only CPU-based Pillow rendering -- no GPU or AI
image generation required. Each scene is rendered into a sequence of
PNG frames at the configured resolution and FPS.

Supported visual element types:
    title, number, color_display, shape, letter, animal,
    text_overlay, lullaby_visual, nursery_visual
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

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

# ---------------------------------------------------------------------------
# Color palettes used across renderers
# ---------------------------------------------------------------------------

BRIGHT_COLORS: list[str] = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#FF9FF3", "#54A0FF", "#5F27CD", "#01A3A4", "#F368E0",
]

SHAPE_COLORS: list[str] = [
    "#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6",
    "#1ABC9C", "#E67E22", "#E91E63",
]

# Mapping from common color names to hex codes (used by color_display)
COLOR_NAME_TO_HEX: dict[str, str] = {
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#00AA00",
    "yellow": "#FFD700",
    "orange": "#FF8C00",
    "purple": "#8B00FF",
    "pink": "#FF69B4",
    "brown": "#8B4513",
    "black": "#000000",
    "white": "#FFFFFF",
    "gray": "#808080",
    "grey": "#808080",
    "gold": "#FFD700",
    "cyan": "#00CED1",
    "magenta": "#FF00FF",
    "teal": "#008080",
}

# Words associated with each letter (used by the letter renderer)
LETTER_WORDS: dict[str, str] = {
    "A": "Apple", "B": "Ball", "C": "Cat", "D": "Dog", "E": "Elephant",
    "F": "Fish", "G": "Giraffe", "H": "Hat", "I": "Ice cream", "J": "Juice",
    "K": "Kite", "L": "Lion", "M": "Moon", "N": "Nest", "O": "Orange",
    "P": "Pig", "Q": "Queen", "R": "Rabbit", "S": "Star", "T": "Tree",
    "U": "Umbrella", "V": "Violin", "W": "Whale", "X": "Xylophone",
    "Y": "Yarn", "Z": "Zebra",
}

# Animal placeholder colors
ANIMAL_COLORS: dict[str, str] = {
    "cow": "#F5F5DC", "pig": "#FFB6C1", "chicken": "#FFD700",
    "horse": "#8B4513", "sheep": "#F0F0F0", "duck": "#FFA500",
    "lion": "#DAA520", "elephant": "#A9A9A9", "monkey": "#D2691E",
    "giraffe": "#F0C050", "zebra": "#333333", "fish": "#4169E1",
    "whale": "#4682B4", "dolphin": "#87CEEB", "turtle": "#228B22",
    "octopus": "#800080", "dog": "#D2B48C", "cat": "#FFA07A",
    "bird": "#FF4500", "rabbit": "#FFFFFF", "hamster": "#DEB887",
}


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
# Shape drawing helpers
# ---------------------------------------------------------------------------

def _draw_circle(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    fill: str,
    outline: str = "#000000",
) -> None:
    """Draw a filled circle centred at (cx, cy)."""
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=fill,
        outline=outline,
        width=3,
    )


def _draw_square(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    half_size: float,
    fill: str,
    outline: str = "#000000",
) -> None:
    """Draw a filled square centred at (cx, cy)."""
    draw.rectangle(
        [cx - half_size, cy - half_size, cx + half_size, cy + half_size],
        fill=fill,
        outline=outline,
        width=3,
    )


def _draw_triangle(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    fill: str,
    outline: str = "#000000",
) -> None:
    """Draw an equilateral triangle centred at (cx, cy)."""
    points = [
        (cx, cy - radius),
        (cx - radius * math.cos(math.radians(30)), cy + radius * math.sin(math.radians(30))),
        (cx + radius * math.cos(math.radians(30)), cy + radius * math.sin(math.radians(30))),
    ]
    draw.polygon(points, fill=fill, outline=outline, width=3)


def _draw_star(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    outer_radius: float,
    fill: str,
    outline: str = "#000000",
    points: int = 5,
) -> None:
    """Draw a star polygon with *points* tips using alternating inner/outer radii."""
    inner_radius = outer_radius * 0.4
    coords: list[tuple[float, float]] = []
    for i in range(points * 2):
        angle = math.radians(-90 + i * 180 / points)
        r = outer_radius if i % 2 == 0 else inner_radius
        coords.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(coords, fill=fill, outline=outline, width=3)


def _draw_heart(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    size: float,
    fill: str,
    outline: str = "#000000",
) -> None:
    """Approximate a heart shape with two circles and a lower triangle."""
    r = size * 0.3
    # Two upper circles
    _draw_filled_ellipse(draw, cx - r, cy - r * 0.5, r, fill)
    _draw_filled_ellipse(draw, cx + r, cy - r * 0.5, r, fill)
    # Lower triangle
    tri_points = [
        (cx - size * 0.6, cy - r * 0.1),
        (cx + size * 0.6, cy - r * 0.1),
        (cx, cy + size * 0.7),
    ]
    draw.polygon(tri_points, fill=fill, outline=outline, width=2)
    # Re-draw circles on top so the outline is clean
    _draw_filled_ellipse(draw, cx - r, cy - r * 0.5, r, fill, outline)
    _draw_filled_ellipse(draw, cx + r, cy - r * 0.5, r, fill, outline)


def _draw_filled_ellipse(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    r: float,
    fill: str,
    outline: str | None = None,
) -> None:
    """Helper: draw a filled ellipse (used internally by _draw_heart)."""
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=fill,
        outline=outline,
        width=2 if outline else 0,
    )


def _draw_diamond(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    fill: str,
    outline: str = "#000000",
) -> None:
    """Draw a diamond (rhombus) centred at (cx, cy)."""
    points = [
        (cx, cy - radius),
        (cx + radius * 0.6, cy),
        (cx, cy + radius),
        (cx - radius * 0.6, cy),
    ]
    draw.polygon(points, fill=fill, outline=outline, width=3)


# Dispatcher for the supported shape names
SHAPE_DRAWERS: dict[str, Any] = {
    "circle": lambda d, cx, cy, r, f, o: _draw_circle(d, cx, cy, r, f, o),
    "square": lambda d, cx, cy, r, f, o: _draw_square(d, cx, cy, r, f, o),
    "triangle": lambda d, cx, cy, r, f, o: _draw_triangle(d, cx, cy, r, f, o),
    "star": lambda d, cx, cy, r, f, o: _draw_star(d, cx, cy, r, f, o),
    "heart": lambda d, cx, cy, r, f, o: _draw_heart(d, cx, cy, r, f, o),
    "diamond": lambda d, cx, cy, r, f, o: _draw_diamond(d, cx, cy, r, f, o),
}


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------

class VisualGeneratorAgent(BaseAgent):
    """Generates video frames from a script using Pillow.

    For each scene in the script the agent renders enough frames to cover
    the scene's duration at the configured FPS.  All frames are saved as
    ``frame_NNNNN.png`` inside ``<output_dir>/<video_id>/frames/``.
    A 1280x720 thumbnail is also generated.
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
        """Read the script, render all frames, and populate *context.visuals*."""
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

        self.logger.info(
            "Generating frames for %s (%d scenes, %dx%d @ %d fps)",
            context.video_id,
            len(script.scenes),
            width,
            height,
            fps,
        )

        total_frames = 0
        for scene in script.scenes:
            rendered = self._render_scene(scene, frame_dir, fps, total_frames)
            total_frames += rendered

        # Generate thumbnail
        thumbnail_path = self._generate_thumbnail(script, base_dir)

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
    # Scene rendering
    # ------------------------------------------------------------------ #

    def _render_scene(
        self,
        scene: ScriptScene,
        frame_dir: Path,
        fps: int,
        frame_offset: int = 0,
    ) -> int:
        """Render all frames for a single scene and return the frame count."""
        num_frames = max(1, int(scene.duration_seconds * fps))
        width, height = self.config.visual.resolution

        for i in range(num_frames):
            frame_index = frame_offset + i
            img = self._render_frame(scene, width, height)
            filename = f"frame_{frame_index:05d}.png"
            img.save(frame_dir / filename)

        self.logger.debug(
            "Scene %d: rendered %d frames (%.1fs)",
            scene.scene_number,
            num_frames,
            scene.duration_seconds,
        )
        return num_frames

    # ------------------------------------------------------------------ #
    # Single-frame rendering (dispatches by element type)
    # ------------------------------------------------------------------ #

    def _render_frame(
        self, scene: ScriptScene, width: int, height: int
    ) -> Image.Image:
        """Create a single PIL Image for the given scene."""
        bg_color = scene.background_color or "#FFFFFF"
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # If no elements are specified, fall back to rendering the visual
        # description as centred text.
        if not scene.elements:
            if scene.visual_description:
                self._draw_centred_text(
                    draw, scene.visual_description, width, height,
                    font_size=60, fill=_contrasting_text_color(bg_color),
                )
            return img

        for element in scene.elements:
            etype: str = element.get("type", "")
            renderer = self._element_renderers().get(etype)
            if renderer is not None:
                renderer(draw, img, element, width, height, scene)
            else:
                self.logger.warning("Unknown element type: %s", etype)

        return img

    def _element_renderers(self) -> dict[str, Any]:
        """Map of element type -> renderer callable."""
        return {
            "title": self._render_title,
            "number": self._render_number,
            "color_display": self._render_color_display,
            "shape": self._render_shape,
            "letter": self._render_letter,
            "animal": self._render_animal,
            "text_overlay": self._render_text_overlay,
            "lullaby_visual": self._render_lullaby_visual,
            "nursery_visual": self._render_nursery_visual,
            "neon_cityscape": self._render_neon_cityscape,
            "dancer_silhouette": self._render_dancer_silhouette,
            "neon_reflection": self._render_neon_reflection,
        }

    # ------------------------------------------------------------------ #
    # Element renderers
    # ------------------------------------------------------------------ #

    def _render_title(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Centred large text on a coloured background."""
        text: str = element.get("value", element.get("text", "Title"))
        color: str = element.get("color", scene.background_color or "#4ECDC4")

        # Fill the background with the element colour
        img.paste(Image.new("RGB", (width, height), color), (0, 0))
        draw = ImageDraw.Draw(img)  # refresh after paste

        text_color = _contrasting_text_color(color)
        self._draw_centred_text(
            draw, text, width, height, font_size=100, fill=text_color,
        )

    def _render_number(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Large number in the centre with small circles arranged around it."""
        number_text: str = str(element.get("value", "1"))
        color: str = element.get("color", "#FF6B6B")
        count = int(element.get("value", 1))

        # Draw the big number
        font_large = _load_font(200)
        bbox = draw.textbbox((0, 0), number_text, font=font_large)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((width - tw) / 2, (height - th) / 2 - 40),
            number_text,
            fill=color,
            font=font_large,
        )

        # Arrange small circles around the number
        obj_radius = 25
        margin = 120
        positions = self._distribute_objects(
            count, width, height, margin=margin, avoid_centre=True,
        )
        for px, py in positions:
            draw.ellipse(
                [px - obj_radius, py - obj_radius, px + obj_radius, py + obj_radius],
                fill=color,
                outline="#000000",
                width=2,
            )

    def _render_color_display(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Full-screen colour with the colour name in contrasting text."""
        color_name: str = element.get("value", "red")
        hex_color: str = element.get(
            "color",
            COLOR_NAME_TO_HEX.get(color_name.lower(), "#FF0000"),
        )

        img.paste(Image.new("RGB", (width, height), hex_color), (0, 0))
        draw = ImageDraw.Draw(img)

        text_color = _contrasting_text_color(hex_color)
        self._draw_centred_text(
            draw, color_name.upper(), width, height, font_size=140, fill=text_color,
        )

    def _render_shape(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Draw a named shape centred on a white background."""
        shape_name: str = element.get("value", "circle").lower()
        fill_color: str = element.get("color", random.choice(SHAPE_COLORS))
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.25

        drawer = SHAPE_DRAWERS.get(shape_name)
        if drawer is not None:
            drawer(draw, cx, cy, radius, fill_color, "#000000")
        else:
            # Fallback: draw the shape name as text
            self._draw_centred_text(
                draw, shape_name.upper(), width, height, font_size=100,
                fill="#333333",
            )

        # Label below the shape
        label_font = _load_font(60)
        label = shape_name.upper()
        lbox = draw.textbbox((0, 0), label, font=label_font)
        lw = lbox[2] - lbox[0]
        draw.text(
            ((width - lw) / 2, cy + radius + 40),
            label,
            fill="#333333",
            font=label_font,
        )

    def _render_letter(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Large letter centred with an associated word below."""
        letter: str = str(element.get("value", "A")).upper()
        color: str = element.get("color", "#3498DB")
        word: str = element.get("word", LETTER_WORDS.get(letter, ""))

        # Big letter
        font_big = _load_font(240)
        bbox = draw.textbbox((0, 0), letter, font=font_big)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((width - tw) / 2, (height - th) / 2 - 80),
            letter,
            fill=color,
            font=font_big,
        )

        # Word below
        if word:
            font_word = _load_font(64)
            wbox = draw.textbbox((0, 0), word, font=font_word)
            ww = wbox[2] - wbox[0]
            draw.text(
                ((width - ww) / 2, height / 2 + 100),
                word,
                fill="#555555",
                font=font_word,
            )

    def _render_animal(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Coloured circle placeholder with the animal name as text."""
        animal_name: str = element.get("value", "cat")
        color: str = element.get(
            "color",
            ANIMAL_COLORS.get(animal_name.lower(), "#DAA520"),
        )
        cx, cy = width / 2, height / 2 - 60
        radius = min(width, height) * 0.18

        # Placeholder circle
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=color,
            outline="#333333",
            width=4,
        )

        # Eyes (two small white circles with dark pupils)
        eye_r = radius * 0.12
        eye_y = cy - radius * 0.15
        for ex in (cx - radius * 0.3, cx + radius * 0.3):
            draw.ellipse(
                [ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r],
                fill="#FFFFFF",
                outline="#000000",
                width=1,
            )
            pupil_r = eye_r * 0.5
            draw.ellipse(
                [ex - pupil_r, eye_y - pupil_r, ex + pupil_r, eye_y + pupil_r],
                fill="#000000",
            )

        # Animal name label
        font_label = _load_font(72)
        label = animal_name.upper()
        lbox = draw.textbbox((0, 0), label, font=font_label)
        lw = lbox[2] - lbox[0]
        draw.text(
            ((width - lw) / 2, cy + radius + 40),
            label,
            fill="#333333",
            font=font_label,
        )

    def _render_text_overlay(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Semi-transparent text bar at the bottom of the frame."""
        text: str = element.get("value", element.get("text", ""))
        if not text:
            return

        font = _load_font(48)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Dark bar at the bottom
        bar_height = th + 40
        bar_y = height - bar_height
        draw.rectangle(
            [0, bar_y, width, height],
            fill="#000000AA",
        )
        draw.text(
            ((width - tw) / 2, bar_y + 20),
            text,
            fill="#FFFFFF",
            font=font,
        )

    def _render_lullaby_visual(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Dark gradient background with scattered star shapes (small circles)."""
        # Dark blue-to-purple vertical gradient
        for y in range(height):
            ratio = y / height
            r = int(10 + 20 * ratio)
            g = int(10 + 10 * ratio)
            b = int(40 + 40 * (1 - ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Scatter small star dots
        num_stars = random.randint(40, 80)
        for _ in range(num_stars):
            sx = random.randint(0, width)
            sy = random.randint(0, height)
            sr = random.randint(2, 6)
            brightness = random.randint(180, 255)
            star_color = (brightness, brightness, int(brightness * 0.9))
            draw.ellipse(
                [sx - sr, sy - sr, sx + sr, sy + sr],
                fill=star_color,
            )

        # Optional title text
        text: str = element.get("value", element.get("text", ""))
        if text:
            self._draw_centred_text(
                draw, text, width, height, font_size=72, fill="#FFFDE7",
            )

    def _render_nursery_visual(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Bright coloured background with the scene description as text."""
        bg = element.get("color", random.choice(BRIGHT_COLORS))
        img.paste(Image.new("RGB", (width, height), bg), (0, 0))
        draw = ImageDraw.Draw(img)

        text: str = element.get(
            "value",
            element.get("text", scene.visual_description),
        )
        if text:
            text_color = _contrasting_text_color(bg)
            self._draw_centred_text(
                draw, text, width, height, font_size=72, fill=text_color,
            )

    # ------------------------------------------------------------------ #
    # Anime dance renderers
    # ------------------------------------------------------------------ #

    def _render_neon_cityscape(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Render a neon-lit Tokyo cityscape at night.

        Draws a dark gradient sky, building silhouettes of varying heights,
        glowing neon sign rectangles, and scattered light bokeh.
        """
        accent: str = element.get("color", "#FF00FF")
        setting: str = element.get("value", "tokyo_balcony")

        # -- Dark gradient sky (top: deep navy -> bottom: dark purple) --
        for y in range(height):
            ratio = y / height
            r = int(5 + 15 * ratio)
            g = int(5 + 8 * ratio)
            b = int(20 + 25 * (1 - ratio))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # -- Building silhouettes along the bottom half --
        horizon_y = int(height * 0.45)
        num_buildings = random.randint(18, 30)
        building_width_range = (40, 120)

        for i in range(num_buildings):
            bx = int(i * width / num_buildings) + random.randint(-20, 20)
            bw = random.randint(*building_width_range)
            bh = random.randint(int(height * 0.15), int(height * 0.50))
            by = horizon_y + random.randint(-30, 30)

            # Dark building body
            shade = random.randint(8, 25)
            draw.rectangle(
                [bx, by, bx + bw, height],
                fill=(shade, shade, shade + 5),
            )

            # Lit windows (small yellow/white rectangles)
            win_size = 4
            win_gap = 12
            for wy in range(by + 8, by + bh, win_gap):
                for wx in range(bx + 6, bx + bw - 6, win_gap):
                    if random.random() < 0.4:
                        brightness = random.randint(160, 255)
                        warmth = random.randint(140, 220)
                        draw.rectangle(
                            [wx, wy, wx + win_size, wy + win_size],
                            fill=(brightness, warmth, random.randint(50, 120)),
                        )

        # -- Neon signs (glowing rectangles on some buildings) --
        accent_rgb = self._hex_to_rgb(accent)
        num_signs = random.randint(5, 10)
        for _ in range(num_signs):
            sx = random.randint(0, width - 80)
            sy = random.randint(horizon_y - 40, int(height * 0.7))
            sw = random.randint(40, 100)
            sh = random.randint(12, 25)

            # Glow aura (larger, semi-transparent rectangle behind)
            glow_expand = 6
            glow_color = tuple(min(255, c + 40) for c in accent_rgb) + (80,)
            glow_img = Image.new("RGBA", (sw + glow_expand * 2, sh + glow_expand * 2), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_img)
            glow_draw.rectangle(
                [0, 0, sw + glow_expand * 2, sh + glow_expand * 2],
                fill=glow_color,
            )
            img.paste(
                glow_img.convert("RGB"),
                (sx - glow_expand, sy - glow_expand),
            )
            # Bright sign core
            draw.rectangle(
                [sx, sy, sx + sw, sy + sh],
                fill=accent_rgb,
            )

        # -- Bokeh lights (circular glowing dots) --
        num_bokeh = random.randint(15, 35)
        for _ in range(num_bokeh):
            bkx = random.randint(0, width)
            bky = random.randint(0, height)
            bkr = random.randint(3, 15)
            # Pick a random neon color
            neon_options = ["#FF00FF", "#00FFFF", "#FF1493", "#00FF7F", "#FFD700"]
            bokeh_color = self._hex_to_rgb(random.choice(neon_options))
            # Dim the bokeh to simulate depth-of-field
            dimmed = tuple(max(0, c - random.randint(40, 100)) for c in bokeh_color)
            draw.ellipse(
                [bkx - bkr, bky - bkr, bkx + bkr, bky + bkr],
                fill=dimmed,
            )

        # -- Balcony railing (if applicable) --
        if "balcony" in setting or "rooftop" in setting:
            railing_y = int(height * 0.75)
            # Horizontal bar
            draw.rectangle(
                [0, railing_y, width, railing_y + 4],
                fill=(60, 60, 70),
            )
            # Vertical posts
            for rx in range(0, width, 50):
                draw.rectangle(
                    [rx, railing_y, rx + 3, railing_y + 40],
                    fill=(50, 50, 60),
                )

    def _render_dancer_silhouette(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Render a stylized dancer silhouette with neon edge-lighting.

        The dancer is drawn as a dark silhouette in the centre with a
        colored glow outline that simulates neon rim-lighting from the
        city behind them.
        """
        accent: str = element.get("color", "#00FFFF")
        pose: str = element.get("value", "groove_bounce")
        accent_rgb = self._hex_to_rgb(accent)

        cx = width // 2
        ground_y = int(height * 0.82)

        # Head
        head_r = 28
        head_y = ground_y - 260

        # Glow outline (slightly larger circles/lines behind the silhouette)
        glow_offset = 4

        # -- Draw glow layer first --
        glow_color = accent_rgb

        # Head glow
        draw.ellipse(
            [cx - head_r - glow_offset, head_y - head_r - glow_offset,
             cx + head_r + glow_offset, head_y + head_r + glow_offset],
            fill=None,
            outline=glow_color,
            width=3,
        )

        # Body glow line
        body_top = head_y + head_r
        body_bottom = ground_y - 80
        draw.line(
            [(cx, body_top), (cx, body_bottom)],
            fill=glow_color,
            width=8 + glow_offset,
        )

        # Pose-dependent arm and leg positions
        arm_y = body_top + 30
        if pose in ("arms_raised", "final_pose"):
            # Arms up
            draw.line([(cx, arm_y), (cx - 70, arm_y - 80)], fill=glow_color, width=6)
            draw.line([(cx, arm_y), (cx + 70, arm_y - 80)], fill=glow_color, width=6)
        elif pose in ("side_step", "pop_lock"):
            # One arm out, one down
            draw.line([(cx, arm_y), (cx - 100, arm_y + 10)], fill=glow_color, width=6)
            draw.line([(cx, arm_y), (cx + 40, arm_y + 70)], fill=glow_color, width=6)
        elif pose == "spin":
            # Arms out in T-pose mid-spin
            draw.line([(cx, arm_y), (cx - 90, arm_y)], fill=glow_color, width=6)
            draw.line([(cx, arm_y), (cx + 90, arm_y)], fill=glow_color, width=6)
        elif pose == "lean_back":
            draw.line([(cx, arm_y), (cx - 30, arm_y - 60)], fill=glow_color, width=6)
            draw.line([(cx, arm_y), (cx + 80, arm_y + 30)], fill=glow_color, width=6)
        else:
            # Default groove arms
            draw.line([(cx, arm_y), (cx - 60, arm_y + 40)], fill=glow_color, width=6)
            draw.line([(cx, arm_y), (cx + 60, arm_y + 40)], fill=glow_color, width=6)

        # Legs
        hip_y = body_bottom
        if pose in ("kick_out",):
            draw.line([(cx, hip_y), (cx - 30, ground_y)], fill=glow_color, width=6)
            draw.line([(cx, hip_y), (cx + 80, ground_y - 40)], fill=glow_color, width=6)
        elif pose in ("slide_glide",):
            draw.line([(cx, hip_y), (cx - 50, ground_y)], fill=glow_color, width=6)
            draw.line([(cx, hip_y), (cx + 50, ground_y)], fill=glow_color, width=6)
        else:
            draw.line([(cx, hip_y), (cx - 30, ground_y)], fill=glow_color, width=6)
            draw.line([(cx, hip_y), (cx + 30, ground_y)], fill=glow_color, width=6)

        # -- Now draw the dark silhouette on top --
        sil_color = (15, 15, 25)

        # Head
        draw.ellipse(
            [cx - head_r, head_y - head_r, cx + head_r, head_y + head_r],
            fill=sil_color,
        )

        # Hair flare (anime style - spiky strands)
        for angle_offset in range(-40, 50, 15):
            hx = cx + int(35 * math.cos(math.radians(angle_offset - 90)))
            hy = head_y + int(35 * math.sin(math.radians(angle_offset - 90)))
            draw.line([(cx, head_y - head_r + 5), (hx, hy - 15)], fill=sil_color, width=5)

        # Body torso
        draw.line([(cx, body_top), (cx, body_bottom)], fill=sil_color, width=7)

        # Arms (same positions but dark)
        if pose in ("arms_raised", "final_pose"):
            draw.line([(cx, arm_y), (cx - 70, arm_y - 80)], fill=sil_color, width=5)
            draw.line([(cx, arm_y), (cx + 70, arm_y - 80)], fill=sil_color, width=5)
        elif pose in ("side_step", "pop_lock"):
            draw.line([(cx, arm_y), (cx - 100, arm_y + 10)], fill=sil_color, width=5)
            draw.line([(cx, arm_y), (cx + 40, arm_y + 70)], fill=sil_color, width=5)
        elif pose == "spin":
            draw.line([(cx, arm_y), (cx - 90, arm_y)], fill=sil_color, width=5)
            draw.line([(cx, arm_y), (cx + 90, arm_y)], fill=sil_color, width=5)
        elif pose == "lean_back":
            draw.line([(cx, arm_y), (cx - 30, arm_y - 60)], fill=sil_color, width=5)
            draw.line([(cx, arm_y), (cx + 80, arm_y + 30)], fill=sil_color, width=5)
        else:
            draw.line([(cx, arm_y), (cx - 60, arm_y + 40)], fill=sil_color, width=5)
            draw.line([(cx, arm_y), (cx + 60, arm_y + 40)], fill=sil_color, width=5)

        # Legs
        if pose in ("kick_out",):
            draw.line([(cx, hip_y), (cx - 30, ground_y)], fill=sil_color, width=5)
            draw.line([(cx, hip_y), (cx + 80, ground_y - 40)], fill=sil_color, width=5)
        elif pose in ("slide_glide",):
            draw.line([(cx, hip_y), (cx - 50, ground_y)], fill=sil_color, width=5)
            draw.line([(cx, hip_y), (cx + 50, ground_y)], fill=sil_color, width=5)
        else:
            draw.line([(cx, hip_y), (cx - 30, ground_y)], fill=sil_color, width=5)
            draw.line([(cx, hip_y), (cx + 30, ground_y)], fill=sil_color, width=5)

    def _render_neon_reflection(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        element: dict[str, Any],
        width: int,
        height: int,
        scene: ScriptScene,
    ) -> None:
        """Render neon light reflections on the ground/floor.

        Draws horizontal streaks of colored light in the bottom portion
        of the frame to simulate wet-floor or polished-surface reflections
        of the neon city behind the dancer.
        """
        accent: str = element.get("color", "#FF00FF")
        mode: str = element.get("value", "floor")
        accent_rgb = self._hex_to_rgb(accent)

        floor_start = int(height * 0.82)

        # Determine intensity based on mode
        num_streaks = 25 if mode == "full_bloom" else 15

        for _ in range(num_streaks):
            sx = random.randint(0, width)
            sy = random.randint(floor_start, height)
            streak_w = random.randint(30, 120)
            streak_h = random.randint(2, 5)

            # Dim the accent based on distance from the dancer
            dist_from_centre = abs(sx - width // 2) / (width // 2)
            dim_factor = max(0.2, 1.0 - dist_from_centre)
            dimmed = tuple(int(c * dim_factor) for c in accent_rgb)

            draw.rectangle(
                [sx, sy, sx + streak_w, sy + streak_h],
                fill=dimmed,
            )

        # Add a few bright reflection spots near centre
        for _ in range(5 if mode == "full_bloom" else 3):
            rx = width // 2 + random.randint(-80, 80)
            ry = random.randint(floor_start + 5, height - 10)
            rr = random.randint(4, 10)
            draw.ellipse(
                [rx - rr, ry - rr, rx + rr, ry + rr],
                fill=accent_rgb,
            )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert a hex color string to an (R, G, B) tuple."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return (255, 0, 255)
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )

    # ------------------------------------------------------------------ #
    # Thumbnail generation
    # ------------------------------------------------------------------ #

    def _generate_thumbnail(self, script: Script, base_dir: Path) -> Path:
        """Create a 1280x720 thumbnail with a bright background and title text."""
        thumb_w, thumb_h = 1280, 720
        bg_color = random.choice(BRIGHT_COLORS)

        img = Image.new("RGB", (thumb_w, thumb_h), bg_color)
        draw = ImageDraw.Draw(img)

        title = script.title or "Baby Learning Video"
        text_color = _contrasting_text_color(bg_color)
        self._draw_centred_text(
            draw, title, thumb_w, thumb_h, font_size=80, fill=text_color,
        )

        thumb_path = base_dir / "thumbnail.png"
        img.save(thumb_path)
        self.logger.info("Thumbnail saved: %s", thumb_path)
        return thumb_path

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #

    def _draw_centred_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        width: int,
        height: int,
        font_size: int = 60,
        fill: str = "#000000",
    ) -> None:
        """Draw *text* centred on the canvas, wrapping if necessary."""
        font = _load_font(font_size)

        # Simple word-wrap: split into lines that fit within 90% of width
        max_text_width = int(width * 0.9)
        lines = self._wrap_text(draw, text, font, max_text_width)

        # Compute total text block height
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
        count: int,
        width: int,
        height: int,
        margin: int = 100,
        avoid_centre: bool = False,
    ) -> list[tuple[int, int]]:
        """Return *count* (x, y) positions spread across the canvas.

        When *avoid_centre* is True, positions will stay away from the
        middle third of the frame (so they don't overlap a centred number).
        """
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
