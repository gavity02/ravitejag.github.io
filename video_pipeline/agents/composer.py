"""Video Composer Agent - Assembles final video from visual frames and audio.

Takes VisualAsset (frames) and AudioAsset (narration + music) from
upstream agents and combines them into a finished MP4 using moviepy.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import PipelineContext, VideoAsset


class VideoComposerAgent(BaseAgent):
    """Composes final video from rendered frames and audio tracks.

    Pipeline position: after VisualGeneratorAgent and AudioAgent.
    Produces: a finished MP4 file ready for SEO tagging and upload.
    """

    @property
    def name(self) -> str:
        return "composer"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.VIDEO_COMPOSED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Assemble the final video from frames and audio.

        Steps:
            1. Load visual frames as an ImageSequenceClip.
            2. Load narration audio segments and background music.
            3. Composite audio tracks, set on video clip.
            4. Write the finished MP4 to the output directory.
        """
        if context.visuals is None:
            raise ValueError(
                "No visual assets in context - visual generator must run first"
            )
        if context.audio is None:
            raise ValueError(
                "No audio assets in context - audio agent must run first"
            )

        video_id = context.video_id
        frame_dir = Path(context.visuals.frame_dir)
        fps = context.visuals.fps
        resolution = context.visuals.resolution

        if not frame_dir.exists():
            raise FileNotFoundError(
                f"Frame directory does not exist: {frame_dir}"
            )

        # Collect sorted frame image paths
        frame_paths = sorted(
            str(p)
            for p in frame_dir.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        )
        if not frame_paths:
            raise FileNotFoundError(
                f"No image frames found in {frame_dir}"
            )

        self.logger.info(
            "Composing video: %d frames at %d fps, resolution %s",
            len(frame_paths),
            fps,
            resolution,
        )

        # Prepare output directory
        output_dir = self._ensure_dir(
            Path(self.config.output_dir) / video_id
        )
        video_path = output_dir / "final_video.mp4"
        thumbnail_path = context.visuals.thumbnail_path

        # Build video clip — support both moviepy v1 and v2
        try:
            from moviepy import (
                AudioFileClip,
                CompositeAudioClip,
                ImageSequenceClip,
                concatenate_videoclips,
            )
        except ImportError:
            from moviepy.editor import (
                AudioFileClip,
                CompositeAudioClip,
                ImageSequenceClip,
                concatenate_videoclips,
            )

        video_clip = ImageSequenceClip(frame_paths, fps=fps)

        # Assemble audio tracks
        audio_clips = self._load_audio_clips(
            context.audio.narration_segments,
            context.audio.narration_path,
            context.audio.music_path,
            AudioFileClip,
            CompositeAudioClip,
        )

        if audio_clips:
            composite_audio = CompositeAudioClip(audio_clips)
            # Trim audio to video length (or vice-versa)
            composite_audio = composite_audio.subclip(
                0, min(composite_audio.duration, video_clip.duration)
            )
            video_clip = video_clip.set_audio(composite_audio)
        else:
            self.logger.warning(
                "No audio files found - producing silent video"
            )

        # Write final video
        self.logger.info("Writing video to %s", video_path)
        video_clip.write_videofile(
            str(video_path),
            codec="libx264",
            audio_codec="aac",
            logger=None,  # suppress moviepy's verbose output
        )

        duration = video_clip.duration
        video_clip.close()
        for clip in audio_clips:
            clip.close()

        file_size_bytes = os.path.getsize(video_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        context.video = VideoAsset(
            video_id=video_id,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            duration_seconds=duration,
            file_size_mb=file_size_mb,
            resolution=resolution,
        )

        self.logger.info(
            "Video composed: %.1fs, %.1f MB, %s",
            duration,
            file_size_mb,
            video_path,
        )
        return context

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_audio_clips(
        self,
        narration_segments: list[dict],
        narration_path: Path | None,
        music_path: Path | None,
        AudioFileClip: type,
        CompositeAudioClip: type,
    ) -> list[Any]:
        """Load and prepare narration + music audio clips.

        Returns a list of audio clips suitable for CompositeAudioClip.
        Gracefully handles missing files so the pipeline can still
        produce a silent video when audio is unavailable.
        """
        clips: list[Any] = []

        # Load narration segments (each has a scene-level audio file)
        for segment in narration_segments:
            seg_path = segment.get("path")
            if seg_path and Path(seg_path).exists():
                try:
                    clip = AudioFileClip(str(seg_path))
                    # Offset the segment to its scene start time if provided
                    start_time = segment.get("start_time", 0)
                    if start_time > 0:
                        clip = clip.set_start(start_time)
                    clips.append(clip)
                except Exception as e:
                    self.logger.warning(
                        "Failed to load narration segment %s: %s",
                        seg_path,
                        e,
                    )

        # If no segments but a single narration file exists, use that
        if not clips and narration_path and Path(narration_path).exists():
            try:
                clips.append(AudioFileClip(str(narration_path)))
            except Exception as e:
                self.logger.warning(
                    "Failed to load narration audio %s: %s",
                    narration_path,
                    e,
                )

        # Load background music
        if music_path and Path(music_path).exists():
            try:
                music_clip = AudioFileClip(str(music_path))
                volume = self.config.music.volume_percent / 100
                music_clip = music_clip.volumex(volume)
                clips.append(music_clip)
            except Exception as e:
                self.logger.warning(
                    "Failed to load background music %s: %s",
                    music_path,
                    e,
                )

        return clips

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Checkpoint is valid if it contains a composed video."""
        return data.get("video") is not None
