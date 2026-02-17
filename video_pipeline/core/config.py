"""Pipeline configuration management.

Loads config from YAML file with sensible defaults for
zero-cost operation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class YouTubeConfig(BaseModel):
    """YouTube API configuration."""

    client_secrets_file: str = "client_secrets.json"
    credentials_file: str = "youtube_credentials.json"
    # YouTube API quota: 10,000 units/day. Upload = 1600 units.
    # So max ~6 uploads/day before hitting quota.
    daily_upload_limit: int = 5
    default_category_id: str = "24"  # Entertainment
    default_privacy: str = "private"  # Start private, review, then publish


class TTSConfig(BaseModel):
    """Text-to-speech configuration."""

    engine: str = "edge-tts"  # edge-tts (free) or elevenlabs (paid)
    voice: str = "en-US-AnaNeural"  # Friendly female voice, good for kids
    rate: str = "-10%"  # Slightly slower for baby content
    volume: str = "+0%"
    pitch: str = "+5Hz"  # Slightly higher pitch


class VisualConfig(BaseModel):
    """Visual generation configuration."""

    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 24
    background_colors: list[str] = Field(
        default_factory=lambda: [
            "#FF6B6B",  # Coral red
            "#4ECDC4",  # Teal
            "#45B7D1",  # Sky blue
            "#96CEB4",  # Sage green
            "#FFEAA7",  # Soft yellow
            "#DDA0DD",  # Plum
            "#98D8C8",  # Mint
            "#F7DC6F",  # Warm yellow
            "#BB8FCE",  # Lavender
            "#85C1E9",  # Light blue
        ]
    )
    font_dir: str = ""  # Path to custom fonts, empty = system fonts
    # Pillow doesn't need a GPU - runs on CPU fine


class MusicConfig(BaseModel):
    """Background music configuration."""

    mode: str = "procedural"  # procedural, file, none
    music_dir: str = "music"  # Directory for music files
    volume_percent: int = 15  # Background music volume (% of narration)
    # Procedural music settings
    tempo_bpm: int = 100
    key: str = "C"
    instrument: str = "music_box"  # music_box, piano, xylophone


class ContentConfig(BaseModel):
    """Content generation settings."""

    video_types: list[str] = Field(
        default_factory=lambda: [
            "counting",
            "colors",
            "shapes",
            "alphabet",
            "animals",
            "lullaby",
        ]
    )
    default_duration_seconds: int = 180  # 3 minutes
    lullaby_duration_seconds: int = 600  # 10 minutes (longer = more watch time)
    counting_range: tuple[int, int] = (1, 10)
    videos_per_batch: int = 5  # How many videos to produce per run


class SEOConfig(BaseModel):
    """SEO optimization settings."""

    channel_name: str = "Baby Learning Fun"
    default_tags: list[str] = Field(
        default_factory=lambda: [
            "baby",
            "toddler",
            "learning",
            "educational",
            "kids",
            "nursery",
            "counting",
            "colors",
            "shapes",
            "alphabet",
        ]
    )
    description_template: str = (
        "Fun and educational video for babies and toddlers! "
        "Learn {topic} with colorful animations and friendly narration. "
        "Perfect for early learning and development.\n\n"
        "#{channel_name} #BabyLearning #Educational #Toddler"
    )


class PipelineConfig(BaseModel):
    """Main pipeline configuration."""

    # Directories
    output_dir: str = "output"
    data_dir: str = "data"
    temp_dir: str = ".tmp"

    # Sub-configs
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    visual: VisualConfig = Field(default_factory=VisualConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)
    seo: SEOConfig = Field(default_factory=SEOConfig)

    # Pipeline settings
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    log_level: str = "INFO"
    checkpoint_enabled: bool = True  # Save progress between stages
    checkpoint_dir: str = ".checkpoints"

    # LLM settings (optional, for enhanced script generation)
    llm_enabled: bool = False
    llm_base_url: str = "http://localhost:11434/v1"  # Ollama default
    llm_model: str = "llama3.2"
    llm_api_key: str = "ollama"  # Ollama doesn't need a real key


def load_config(config_path: Optional[str | Path] = None) -> PipelineConfig:
    """Load configuration from YAML file, falling back to defaults."""
    if config_path is None:
        config_path = Path("config.yaml")
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        return PipelineConfig(**raw)

    return PipelineConfig()
