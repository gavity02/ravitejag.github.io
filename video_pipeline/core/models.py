"""Data models for the video pipeline.

All data passed between agents uses these Pydantic models for
validation and type safety.
"""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class VideoType(str, enum.Enum):
    """Types of video content."""

    COUNTING = "counting"
    COLORS = "colors"
    SHAPES = "shapes"
    ALPHABET = "alphabet"
    ANIMALS = "animals"
    LULLABY = "lullaby"
    NURSERY_RHYME = "nursery_rhyme"
    ANIME_DANCE = "anime_dance"


class TopicSuggestion(BaseModel):
    """A suggested video topic from the research agent."""

    video_type: VideoType
    title_idea: str
    keywords: list[str] = Field(default_factory=list)
    estimated_search_volume: str = "unknown"  # low/medium/high/unknown
    competition_level: str = "unknown"  # low/medium/high/unknown
    reasoning: str = ""


class ContentPlan(BaseModel):
    """A planned piece of content from the planner agent."""

    video_id: str  # unique identifier for this video
    video_type: VideoType
    title_working: str
    target_duration_seconds: int = 180  # 3 min default
    target_audience: str = "babies and toddlers 0-3 years"
    topic_details: dict = Field(default_factory=dict)
    # e.g., {"start": 1, "end": 10} for counting,
    #       {"colors": ["red", "blue"]} for colors
    priority: int = 1  # 1 = highest


class ScriptScene(BaseModel):
    """A single scene in a video script."""

    scene_number: int
    duration_seconds: float = 5.0
    narration_text: str = ""
    visual_description: str = ""
    background_color: str = "#FFFFFF"
    elements: list[dict] = Field(default_factory=list)
    # e.g., [{"type": "number", "value": "1", "color": "#FF0000"}]
    transition: str = "fade"  # fade, cut, slide


class Script(BaseModel):
    """Complete video script."""

    video_id: str
    video_type: VideoType
    title: str
    scenes: list[ScriptScene]
    total_duration_seconds: float = 0
    voice_style: str = "cheerful"  # cheerful, calm, energetic
    music_style: str = "upbeat"  # upbeat, calm, playful


class VisualAsset(BaseModel):
    """Visual assets generated for a video."""

    video_id: str
    frame_dir: Path  # directory containing frame images
    frame_count: int = 0
    fps: int = 24
    resolution: tuple[int, int] = (1920, 1080)
    thumbnail_path: Optional[Path] = None


class AudioAsset(BaseModel):
    """Audio assets generated for a video."""

    video_id: str
    narration_path: Optional[Path] = None  # full narration audio
    music_path: Optional[Path] = None  # background music
    narration_segments: list[dict] = Field(default_factory=list)
    # [{"scene": 1, "path": "...", "duration": 3.5}]
    total_duration_seconds: float = 0


class VideoAsset(BaseModel):
    """Final composed video."""

    video_id: str
    video_path: Path
    thumbnail_path: Optional[Path] = None
    duration_seconds: float = 0
    file_size_mb: float = 0
    resolution: tuple[int, int] = (1920, 1080)


class SEOMetadata(BaseModel):
    """SEO-optimized metadata for YouTube upload."""

    video_id: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category_id: str = "24"  # Entertainment (YouTube category)
    default_language: str = "en"
    made_for_kids: bool = True
    thumbnail_path: Optional[Path] = None


class UploadResult(BaseModel):
    """Result from uploading to YouTube."""

    video_id: str
    youtube_video_id: str = ""
    youtube_url: str = ""
    upload_status: str = "pending"  # pending, uploaded, failed
    error_message: str = ""
    uploaded_at: Optional[datetime] = None


class AnalyticsSnapshot(BaseModel):
    """Performance analytics for a video."""

    video_id: str
    youtube_video_id: str = ""
    views: int = 0
    watch_time_hours: float = 0
    likes: int = 0
    subscribers_gained: int = 0
    ctr_percent: float = 0  # click-through rate
    avg_view_duration_seconds: float = 0
    revenue_estimate_usd: float = 0
    collected_at: Optional[datetime] = None


class PipelineContext(BaseModel):
    """Shared context passed through the pipeline for a single video."""

    video_id: str
    topic: Optional[TopicSuggestion] = None
    plan: Optional[ContentPlan] = None
    script: Optional[Script] = None
    visuals: Optional[VisualAsset] = None
    audio: Optional[AudioAsset] = None
    video: Optional[VideoAsset] = None
    seo: Optional[SEOMetadata] = None
    upload: Optional[UploadResult] = None
    analytics: Optional[AnalyticsSnapshot] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: list[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.video is not None

    @property
    def is_uploaded(self) -> bool:
        return (
            self.upload is not None
            and self.upload.upload_status == "uploaded"
        )
