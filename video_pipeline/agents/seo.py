"""SEO Agent - Optimizes YouTube metadata for maximum discoverability.

Generates search-optimized titles, descriptions, and tags so that
uploaded videos rank well in YouTube search and recommendations.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import PipelineContext, SEOMetadata, VideoType


# Power words proven to boost CTR in educational kids' content
_POWER_WORDS: list[str] = [
    "Learn",
    "Fun",
    "Easy",
    "Best",
    "Amazing",
    "Simple",
    "Happy",
    "Colorful",
    "Bright",
    "Playful",
]

# Video-type specific tag pools
_TYPE_TAG_MAP: dict[VideoType, list[str]] = {
    VideoType.COUNTING: [
        "counting", "numbers", "123", "learn to count",
        "math for kids", "number song",
    ],
    VideoType.COLORS: [
        "colors", "learn colors", "colour", "rainbow",
        "color song", "primary colors",
    ],
    VideoType.SHAPES: [
        "shapes", "learn shapes", "circle", "square",
        "triangle", "geometry for kids",
    ],
    VideoType.ALPHABET: [
        "alphabet", "abc", "letters", "phonics",
        "abc song", "learn letters",
    ],
    VideoType.ANIMALS: [
        "animals", "animal sounds", "farm animals",
        "zoo animals", "pets", "animal names",
    ],
    VideoType.LULLABY: [
        "lullaby", "baby sleep", "bedtime music",
        "sleep music", "soothing", "relaxing",
    ],
    VideoType.NURSERY_RHYME: [
        "nursery rhyme", "kids song", "children song",
        "sing along", "rhymes", "preschool songs",
    ],
}


class SEOAgent(BaseAgent):
    """Optimizes video metadata for YouTube search and discovery.

    Pipeline position: after VideoComposerAgent.
    Produces: SEOMetadata attached to the pipeline context.
    """

    @property
    def name(self) -> str:
        return "seo"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.SEO_OPTIMIZED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Generate SEO-optimized metadata for the composed video.

        Steps:
            1. Build an optimized title with power words.
            2. Format the description from the config template.
            3. Generate tags from defaults + script keywords + type tags.
            4. Attach SEOMetadata to the context.
        """
        if context.script is None:
            raise ValueError(
                "No script in context - scriptwriter agent must run first"
            )

        video_id = context.video_id
        script = context.script
        video_type = script.video_type
        thumbnail_path = (
            context.video.thumbnail_path if context.video else None
        )

        # 1. Optimized title
        title = self._optimize_title(script.title, video_type)

        # 2. Description
        description = self._build_description(script.title, video_type)

        # 3. Tags
        tags = self._generate_tags(script, video_type)

        context.seo = SEOMetadata(
            video_id=video_id,
            title=title,
            description=description,
            tags=tags,
            category_id="24",  # Entertainment
            made_for_kids=True,
            thumbnail_path=thumbnail_path,
        )

        self.logger.info(
            "SEO optimized: title=%r (%d chars), %d tags",
            title,
            len(title),
            len(tags),
        )
        return context

    # ------------------------------------------------------------------
    # Title helpers
    # ------------------------------------------------------------------

    def _optimize_title(
        self, raw_title: str, video_type: VideoType
    ) -> str:
        """Create an SEO-friendly title.

        Rules:
            - Inject a power word if none is present.
            - Keep it under 70 characters (sweet spot for YouTube).
            - No emojis (cleaner look, broader compatibility).
            - Append audience cue if space allows.
        """
        title = raw_title.strip()

        # Strip any emojis that may have leaked in from upstream
        title = self._strip_emojis(title)

        # Inject a power word at the front when the title lacks one
        has_power_word = any(
            pw.lower() in title.lower() for pw in _POWER_WORDS
        )
        if not has_power_word:
            # Pick a contextually appropriate power word
            power_word = self._pick_power_word(video_type)
            candidate = f"{power_word} {title}"
            if len(candidate) <= 70:
                title = candidate

        # Append audience cue if there is room
        audience_cues = [
            "for Babies and Toddlers",
            "for Babies",
            "for Kids",
        ]
        for cue in audience_cues:
            if cue.lower() in title.lower():
                break
            candidate = f"{title} | {cue}"
            if len(candidate) <= 70:
                title = candidate
                break

        # Hard truncation safety net
        if len(title) > 70:
            title = title[:67] + "..."

        return title

    def _pick_power_word(self, video_type: VideoType) -> str:
        """Select a power word that fits the video type."""
        mapping: dict[VideoType, str] = {
            VideoType.COUNTING: "Learn",
            VideoType.COLORS: "Colorful",
            VideoType.SHAPES: "Fun",
            VideoType.ALPHABET: "Learn",
            VideoType.ANIMALS: "Amazing",
            VideoType.LULLABY: "Happy",
            VideoType.NURSERY_RHYME: "Fun",
        }
        return mapping.get(video_type, "Learn")

    @staticmethod
    def _strip_emojis(text: str) -> str:
        """Remove emoji characters from a string."""
        emoji_pattern = re.compile(
            "[\U00010000-\U0010FFFF]"  # supplementary planes
            "|[\u2600-\u27BF]"  # misc symbols
            "|[\uFE00-\uFE0F]"  # variation selectors
            "|[\u200D]",  # zero-width joiner
            flags=re.UNICODE,
        )
        return emoji_pattern.sub("", text).strip()

    # ------------------------------------------------------------------
    # Description helpers
    # ------------------------------------------------------------------

    def _build_description(
        self, topic: str, video_type: VideoType
    ) -> str:
        """Format the description from the config template."""
        template = self.config.seo.description_template
        channel = self.config.seo.channel_name

        description = template.format(
            topic=topic,
            channel_name=channel.replace(" ", ""),
        )

        # Append extra hashtags based on video type
        type_hashtags = {
            VideoType.COUNTING: "#Counting #Numbers #123",
            VideoType.COLORS: "#Colors #Rainbow #LearnColors",
            VideoType.SHAPES: "#Shapes #Geometry #LearnShapes",
            VideoType.ALPHABET: "#ABC #Alphabet #Letters",
            VideoType.ANIMALS: "#Animals #AnimalSounds #ZooAnimals",
            VideoType.LULLABY: "#Lullaby #BabySleep #SoothingMusic",
            VideoType.NURSERY_RHYME: "#NurseryRhyme #KidsSongs #SingAlong",
        }
        extra = type_hashtags.get(video_type, "")
        if extra:
            description = f"{description}\n{extra}"

        return description

    # ------------------------------------------------------------------
    # Tag helpers
    # ------------------------------------------------------------------

    def _generate_tags(
        self,
        script: Any,
        video_type: VideoType,
    ) -> list[str]:
        """Build a tag list from multiple sources.

        Sources combined (in priority order):
            1. Config default tags.
            2. Video-type specific tags.
            3. Keywords extracted from script scenes.

        YouTube enforces a 500-character total limit on tags.
        """
        tags: list[str] = []
        seen: set[str] = set()

        def _add(tag: str) -> None:
            """Add a tag if it has not been seen yet."""
            normalized = tag.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                tags.append(tag.strip())

        # 1. Default tags from config
        for tag in self.config.seo.default_tags:
            _add(tag)

        # 2. Type-specific tags
        type_tags = _TYPE_TAG_MAP.get(video_type, [])
        for tag in type_tags:
            _add(tag)

        # 3. Keywords from script scenes
        for scene in script.scenes:
            # Pull keywords from visual descriptions and narration
            words = self._extract_keywords(scene.visual_description)
            words += self._extract_keywords(scene.narration_text)
            for word in words:
                _add(word)

        # 4. Add the title itself as a long-tail keyword
        _add(script.title)

        # Enforce YouTube 500-char limit
        trimmed: list[str] = []
        total_len = 0
        for tag in tags:
            # Each tag is separated by commas in YouTube's internal repr
            addition = len(tag) + (1 if trimmed else 0)  # comma separator
            if total_len + addition > 500:
                break
            trimmed.append(tag)
            total_len += addition

        return trimmed

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from a text block.

        Filters out common stop words and returns unique terms that
        are likely to be useful as YouTube tags.
        """
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "not", "no", "so", "if", "then", "than",
            "too", "very", "just", "about", "up", "out", "it", "its",
            "this", "that", "these", "those", "i", "you", "he", "she",
            "we", "they", "me", "him", "her", "us", "them", "my", "your",
            "his", "our", "their", "what", "which", "who", "whom", "how",
            "all", "each", "every", "both", "few", "more", "most", "some",
            "any", "other", "into", "over", "after", "before", "between",
            "here", "there", "now", "let", "see", "look", "say", "says",
        }

        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        keywords: list[str] = []
        seen: set[str] = set()
        for w in words:
            if w not in stop_words and w not in seen:
                seen.add(w)
                keywords.append(w)
        return keywords

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Checkpoint is valid if it contains SEO metadata."""
        return data.get("seo") is not None
