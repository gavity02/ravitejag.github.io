"""Research Agent - Discovers trending baby content topics on YouTube.

Uses YouTube search suggestions and public data to find
what topics have demand. No API key required for basic research.
"""

from __future__ import annotations

import json
import random
import urllib.parse
import urllib.request
from pathlib import Path

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import PipelineContext, TopicSuggestion, VideoType

# Pre-built topic database organized by type.
# These are based on real high-performing baby content patterns.
TOPIC_DATABASE: dict[VideoType, list[dict]] = {
    VideoType.COUNTING: [
        {
            "title": "Count to 10 with Colorful Animals",
            "keywords": ["counting for babies", "learn to count", "123 for toddlers", "numbers for kids"],
            "search_volume": "high",
        },
        {
            "title": "Count Fruits 1 to 20",
            "keywords": ["count fruits", "fruit counting", "learn numbers with fruits"],
            "search_volume": "medium",
        },
        {
            "title": "Counting Stars - Numbers 1 to 10",
            "keywords": ["counting stars", "night counting", "bedtime counting"],
            "search_volume": "medium",
        },
        {
            "title": "Count Colorful Balls 1 to 15",
            "keywords": ["counting balls", "bouncing balls counting", "ball pit counting"],
            "search_volume": "high",
        },
        {
            "title": "Count Vehicles 1 to 10 - Cars Trucks Buses",
            "keywords": ["count vehicles", "counting cars", "trucks for babies"],
            "search_volume": "high",
        },
    ],
    VideoType.COLORS: [
        {
            "title": "Learn Colors with Balloons",
            "keywords": ["learn colors", "colors for babies", "balloon colors", "color learning"],
            "search_volume": "high",
        },
        {
            "title": "Rainbow Colors Song for Babies",
            "keywords": ["rainbow colors", "color song", "ROYGBIV for kids"],
            "search_volume": "high",
        },
        {
            "title": "Colors of Fruits and Vegetables",
            "keywords": ["fruit colors", "vegetable colors", "food colors for kids"],
            "search_volume": "medium",
        },
        {
            "title": "Mixing Colors - Red + Blue = Purple",
            "keywords": ["mixing colors", "color mixing for kids", "primary colors"],
            "search_volume": "medium",
        },
    ],
    VideoType.SHAPES: [
        {
            "title": "Learn Shapes - Circle Square Triangle",
            "keywords": ["learn shapes", "shapes for babies", "basic shapes", "geometry for toddlers"],
            "search_volume": "high",
        },
        {
            "title": "Shapes in Real Life for Toddlers",
            "keywords": ["shapes everywhere", "real life shapes", "shapes around us"],
            "search_volume": "medium",
        },
        {
            "title": "Shape Sorting Fun for Babies",
            "keywords": ["shape sorting", "shapes game", "shape puzzle for kids"],
            "search_volume": "medium",
        },
    ],
    VideoType.ALPHABET: [
        {
            "title": "ABC Song - Learn the Alphabet",
            "keywords": ["abc song", "alphabet for babies", "learn abc", "abcd song"],
            "search_volume": "high",
        },
        {
            "title": "Phonics Sounds A to Z for Toddlers",
            "keywords": ["phonics", "letter sounds", "a to z sounds", "phonics for babies"],
            "search_volume": "high",
        },
        {
            "title": "Animals A to Z - Alphabet Animals",
            "keywords": ["alphabet animals", "animal abc", "a is for ant"],
            "search_volume": "medium",
        },
    ],
    VideoType.ANIMALS: [
        {
            "title": "Farm Animals and Their Sounds",
            "keywords": ["farm animals", "animal sounds", "cow moo", "animals for babies"],
            "search_volume": "high",
        },
        {
            "title": "Ocean Animals for Babies - Under the Sea",
            "keywords": ["ocean animals", "sea animals", "fish for babies", "under the sea"],
            "search_volume": "medium",
        },
        {
            "title": "Wild Animals Safari for Toddlers",
            "keywords": ["wild animals", "safari animals", "lion tiger", "jungle animals"],
            "search_volume": "medium",
        },
    ],
    VideoType.LULLABY: [
        {
            "title": "Gentle Lullaby for Baby Sleep - 1 Hour",
            "keywords": ["lullaby", "baby sleep music", "bedtime music", "soothing music baby"],
            "search_volume": "high",
        },
        {
            "title": "Twinkle Twinkle Little Star - Calming Version",
            "keywords": ["twinkle twinkle", "star lullaby", "calming baby music"],
            "search_volume": "high",
        },
        {
            "title": "Rain Sounds with Soft Music for Baby",
            "keywords": ["rain sounds baby", "white noise baby", "rain lullaby"],
            "search_volume": "medium",
        },
    ],
    VideoType.NURSERY_RHYME: [
        {
            "title": "Wheels on the Bus - Animated",
            "keywords": ["wheels on the bus", "nursery rhymes", "kids songs", "bus song"],
            "search_volume": "high",
        },
        {
            "title": "Old MacDonald Had a Farm",
            "keywords": ["old macdonald", "farm song", "eieio", "nursery rhyme animals"],
            "search_volume": "high",
        },
        {
            "title": "Itsy Bitsy Spider - Fun Animation",
            "keywords": ["itsy bitsy spider", "incy wincy spider", "spider song kids"],
            "search_volume": "high",
        },
    ],
}


class ResearchAgent(BaseAgent):
    """Researches trending baby content topics.

    Strategy:
    1. Rotates through video types to maintain variety
    2. Uses YouTube search suggestions for real-time trend data
    3. Falls back to curated topic database if scraping fails
    4. Tracks previously used topics to avoid repetition
    """

    @property
    def name(self) -> str:
        return "research"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.TOPIC_RESEARCHED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        # Determine which video type to produce next
        video_type = self._pick_video_type()
        self.logger.info("Researching topics for: %s", video_type.value)

        # Try to get YouTube search suggestions for fresh data
        suggestions = await self._get_youtube_suggestions(video_type)

        # Fall back to curated database
        if not suggestions:
            suggestions = self._get_from_database(video_type)

        if not suggestions:
            raise RuntimeError(f"No topics found for {video_type.value}")

        # Pick the best suggestion
        topic = self._rank_and_pick(suggestions)
        self.logger.info("Selected topic: %s", topic.title_idea)

        context.topic = topic
        return context

    def _pick_video_type(self) -> VideoType:
        """Pick the next video type, rotating through configured types."""
        history_file = Path(self.config.data_dir) / "type_history.json"
        allowed_types = [
            VideoType(t) for t in self.config.content.video_types
        ]

        if history_file.exists():
            try:
                history = json.loads(history_file.read_text())
                last_type = history.get("last_type", "")
                # Pick the next type in rotation
                for i, vt in enumerate(allowed_types):
                    if vt.value == last_type:
                        next_idx = (i + 1) % len(allowed_types)
                        chosen = allowed_types[next_idx]
                        break
                else:
                    chosen = allowed_types[0]
            except Exception:
                chosen = random.choice(allowed_types)
        else:
            chosen = allowed_types[0]

        # Save the choice
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps({"last_type": chosen.value}))

        return chosen

    async def _get_youtube_suggestions(
        self, video_type: VideoType
    ) -> list[TopicSuggestion]:
        """Fetch YouTube search autocomplete suggestions."""
        queries = {
            VideoType.COUNTING: "counting for babies",
            VideoType.COLORS: "learn colors for toddlers",
            VideoType.SHAPES: "shapes for babies",
            VideoType.ALPHABET: "abc for babies",
            VideoType.ANIMALS: "animals for babies",
            VideoType.LULLABY: "lullaby for baby sleep",
            VideoType.NURSERY_RHYME: "nursery rhymes for babies",
        }

        query = queries.get(video_type, "baby learning videos")
        url = (
            "http://suggestqueries.google.com/complete/search"
            f"?client=youtube&ds=yt&q={urllib.parse.quote(query)}"
        )

        suggestions = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                # Response is JSONP-like: window.google.ac.h(...)
                # Extract the JSON array
                start = raw.index("[")
                data = json.loads(raw[start:])
                if data and len(data) > 1:
                    for item in data[1]:
                        title = item[0] if isinstance(item, list) else str(item)
                        suggestions.append(
                            TopicSuggestion(
                                video_type=video_type,
                                title_idea=title,
                                keywords=[title, query],
                                estimated_search_volume="medium",
                                competition_level="medium",
                                reasoning="YouTube autocomplete suggestion",
                            )
                        )
        except Exception as e:
            self.logger.warning(
                "YouTube suggestions failed (expected if offline): %s", e
            )

        return suggestions

    def _get_from_database(
        self, video_type: VideoType
    ) -> list[TopicSuggestion]:
        """Get topics from the built-in curated database."""
        topics_data = TOPIC_DATABASE.get(video_type, [])

        # Check which topics we've already used
        used_file = Path(self.config.data_dir) / "used_topics.json"
        used_titles: set[str] = set()
        if used_file.exists():
            try:
                used_titles = set(json.loads(used_file.read_text()))
            except Exception:
                pass

        suggestions = []
        for td in topics_data:
            if td["title"] not in used_titles:
                suggestions.append(
                    TopicSuggestion(
                        video_type=video_type,
                        title_idea=td["title"],
                        keywords=td.get("keywords", []),
                        estimated_search_volume=td.get("search_volume", "unknown"),
                        competition_level="medium",
                        reasoning="Curated topic database",
                    )
                )

        # If all topics are used, reset and reuse
        if not suggestions:
            self.logger.info("All topics used for %s, resetting", video_type.value)
            for td in topics_data:
                suggestions.append(
                    TopicSuggestion(
                        video_type=video_type,
                        title_idea=td["title"],
                        keywords=td.get("keywords", []),
                        estimated_search_volume=td.get("search_volume", "unknown"),
                        competition_level="medium",
                        reasoning="Curated topic database (recycled)",
                    )
                )

        return suggestions

    def _rank_and_pick(
        self, suggestions: list[TopicSuggestion]
    ) -> TopicSuggestion:
        """Rank suggestions and pick the best one."""
        # Simple scoring: prefer high search volume, low competition
        volume_score = {"high": 3, "medium": 2, "low": 1, "unknown": 1}
        competition_score = {"low": 3, "medium": 2, "high": 1, "unknown": 2}

        def score(s: TopicSuggestion) -> float:
            vs = volume_score.get(s.estimated_search_volume, 1)
            cs = competition_score.get(s.competition_level, 2)
            # Add some randomness to avoid always picking the same topic
            return vs + cs + random.uniform(0, 2)

        suggestions.sort(key=score, reverse=True)
        chosen = suggestions[0]

        # Record that we used this topic
        used_file = Path(self.config.data_dir) / "used_topics.json"
        used_file.parent.mkdir(parents=True, exist_ok=True)
        used_titles: list[str] = []
        if used_file.exists():
            try:
                used_titles = json.loads(used_file.read_text())
            except Exception:
                pass
        used_titles.append(chosen.title_idea)
        used_file.write_text(json.dumps(used_titles))

        return chosen
