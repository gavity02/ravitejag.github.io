"""Content Planner Agent - Creates detailed content plans from topics.

Takes a TopicSuggestion from the Research Agent and creates
a structured ContentPlan with all the details needed by
downstream agents (scriptwriter, visual generator, etc.).
"""

from __future__ import annotations

import random
import uuid

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import (
    ContentPlan,
    PipelineContext,
    VideoType,
)

# Detailed planning data for each video type
COUNTING_PLANS = [
    {"label": "Count to 10", "start": 1, "end": 10, "objects": "stars"},
    {"label": "Count to 20", "start": 1, "end": 20, "objects": "balloons"},
    {"label": "Count by 2s", "start": 2, "end": 20, "step": 2, "objects": "apples"},
    {"label": "Count to 5", "start": 1, "end": 5, "objects": "fish"},
    {"label": "Count backwards from 10", "start": 10, "end": 0, "step": -1, "objects": "rockets"},
]

COLOR_SETS = [
    ["red", "blue", "yellow", "green"],
    ["orange", "purple", "pink", "brown"],
    ["red", "orange", "yellow", "green", "blue", "purple"],  # Rainbow
    ["black", "white", "gray", "gold"],
]

SHAPE_SETS = [
    ["circle", "square", "triangle", "rectangle"],
    ["star", "heart", "diamond", "oval"],
    ["pentagon", "hexagon", "octagon", "crescent"],
]

ALPHABET_PLANS = [
    {"start": "A", "end": "F"},
    {"start": "G", "end": "L"},
    {"start": "M", "end": "R"},
    {"start": "S", "end": "Z"},
    {"start": "A", "end": "Z"},  # Full alphabet
]

ANIMAL_SETS = [
    {"theme": "farm", "animals": ["cow", "pig", "chicken", "horse", "sheep", "duck"]},
    {"theme": "jungle", "animals": ["lion", "elephant", "monkey", "giraffe", "zebra"]},
    {"theme": "ocean", "animals": ["fish", "whale", "dolphin", "turtle", "octopus"]},
    {"theme": "pets", "animals": ["dog", "cat", "bird", "rabbit", "hamster"]},
]

LULLABY_SONGS = [
    {"name": "Twinkle Twinkle Little Star", "key": "C", "tempo": 80},
    {"name": "Rock-a-Bye Baby", "key": "F", "tempo": 70},
    {"name": "Hush Little Baby", "key": "G", "tempo": 75},
    {"name": "Brahms Lullaby", "key": "Eb", "tempo": 65},
    {"name": "All the Pretty Horses", "key": "Am", "tempo": 72},
]

NURSERY_RHYMES = [
    {"name": "Mary Had a Little Lamb", "tempo": 110},
    {"name": "Baa Baa Black Sheep", "tempo": 100},
    {"name": "Humpty Dumpty", "tempo": 95},
    {"name": "Jack and Jill", "tempo": 105},
    {"name": "Itsy Bitsy Spider", "tempo": 100},
    {"name": "Old MacDonald Had a Farm", "tempo": 110},
    {"name": "Row Row Row Your Boat", "tempo": 90},
    {"name": "Head Shoulders Knees and Toes", "tempo": 120},
]


class PlannerAgent(BaseAgent):
    """Creates detailed content plans from research topics."""

    @property
    def name(self) -> str:
        return "planner"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.CONTENT_PLANNED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Create a content plan based on the researched topic."""
        topic = context.topic
        if topic is None:
            raise ValueError("No topic found in context - research agent must run first")

        video_id = f"vid_{uuid.uuid4().hex[:8]}"
        context.video_id = video_id

        plan = self._create_plan(video_id, topic.video_type)
        plan.title_working = self._generate_title(topic)

        context.plan = plan
        self.logger.info(
            "Planned: %s (type=%s, duration=%ds)",
            plan.title_working,
            plan.video_type.value,
            plan.target_duration_seconds,
        )
        return context

    def _create_plan(
        self, video_id: str, video_type: VideoType
    ) -> ContentPlan:
        """Create a plan based on video type."""
        planners = {
            VideoType.COUNTING: self._plan_counting,
            VideoType.COLORS: self._plan_colors,
            VideoType.SHAPES: self._plan_shapes,
            VideoType.ALPHABET: self._plan_alphabet,
            VideoType.ANIMALS: self._plan_animals,
            VideoType.LULLABY: self._plan_lullaby,
            VideoType.NURSERY_RHYME: self._plan_nursery_rhyme,
        }

        planner = planners.get(video_type, self._plan_counting)
        return planner(video_id)

    def _plan_counting(self, video_id: str) -> ContentPlan:
        spec = random.choice(COUNTING_PLANS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.COUNTING,
            title_working=f"Learn to Count {spec['label']}",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details={
                "start": spec["start"],
                "end": spec["end"],
                "step": spec.get("step", 1),
                "objects": spec["objects"],
            },
        )

    def _plan_colors(self, video_id: str) -> ContentPlan:
        colors = random.choice(COLOR_SETS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.COLORS,
            title_working=f"Learn Colors: {', '.join(c.title() for c in colors[:3])} & More!",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details={"colors": colors},
        )

    def _plan_shapes(self, video_id: str) -> ContentPlan:
        shapes = random.choice(SHAPE_SETS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.SHAPES,
            title_working=f"Learn Shapes: {', '.join(s.title() for s in shapes[:3])} & More!",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details={"shapes": shapes},
        )

    def _plan_alphabet(self, video_id: str) -> ContentPlan:
        spec = random.choice(ALPHABET_PLANS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.ALPHABET,
            title_working=f"Learn the Alphabet: {spec['start']} to {spec['end']}",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details=spec,
        )

    def _plan_animals(self, video_id: str) -> ContentPlan:
        spec = random.choice(ANIMAL_SETS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.ANIMALS,
            title_working=f"{spec['theme'].title()} Animals for Babies",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details=spec,
        )

    def _plan_lullaby(self, video_id: str) -> ContentPlan:
        spec = random.choice(LULLABY_SONGS)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.LULLABY,
            title_working=f"{spec['name']} - Baby Lullaby",
            target_duration_seconds=self.config.content.lullaby_duration_seconds,
            topic_details=spec,
        )

    def _plan_nursery_rhyme(self, video_id: str) -> ContentPlan:
        spec = random.choice(NURSERY_RHYMES)
        return ContentPlan(
            video_id=video_id,
            video_type=VideoType.NURSERY_RHYME,
            title_working=f"{spec['name']} | Nursery Rhyme for Babies",
            target_duration_seconds=self.config.content.default_duration_seconds,
            topic_details=spec,
        )

    def _generate_title(self, topic) -> str:
        """Generate a working title from the topic suggestion."""
        title = topic.title_idea
        # Ensure it's not too long (YouTube limit is 100 chars)
        if len(title) > 80:
            title = title[:77] + "..."
        return title
