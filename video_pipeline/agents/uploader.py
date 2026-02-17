"""Upload Agent - Handles uploading finished videos to YouTube.

Uses the YouTube Data API v3 to upload videos with SEO-optimized
metadata. Supports dry-run mode for testing without actual uploads.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import PipelineContext, UploadResult


class UploadAgent(BaseAgent):
    """Uploads composed videos to YouTube via the Data API.

    Pipeline position: after SEOAgent.
    Produces: UploadResult attached to the pipeline context.
    """

    @property
    def name(self) -> str:
        return "uploader"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.VIDEO_UPLOADED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Upload the video to YouTube.

        Steps:
            1. Validate that video file and SEO metadata exist.
            2. If dry-run mode, skip the actual upload.
            3. Otherwise, authenticate and upload via YouTube API.
            4. Record the result in the pipeline context.
        """
        if context.video is None:
            raise ValueError(
                "No video in context - composer agent must run first"
            )
        if context.seo is None:
            raise ValueError(
                "No SEO metadata in context - SEO agent must run first"
            )

        video_path = Path(context.video.video_path)
        if not video_path.exists():
            raise FileNotFoundError(
                f"Video file does not exist: {video_path}"
            )

        video_id = context.video_id

        # Dry-run mode: simulate upload without touching YouTube
        if getattr(self.config, "dry_run", False):
            self.logger.info(
                "DRY RUN: Would upload %s (%s MB) with title: %s",
                video_path,
                context.video.file_size_mb,
                context.seo.title,
            )
            context.upload = UploadResult(
                video_id=video_id,
                youtube_video_id="dry_run_simulated",
                youtube_url="https://youtube.com/watch?v=dry_run_simulated",
                upload_status="simulated",
                uploaded_at=datetime.now(),
            )
            return context

        # Real upload via YouTube Data API
        youtube_video_id = await self._upload_to_youtube(context)

        context.upload = UploadResult(
            video_id=video_id,
            youtube_video_id=youtube_video_id,
            youtube_url=f"https://youtube.com/watch?v={youtube_video_id}",
            upload_status="uploaded",
            uploaded_at=datetime.now(),
        )

        self.logger.info(
            "Video uploaded: %s -> %s",
            video_path.name,
            context.upload.youtube_url,
        )
        return context

    async def _upload_to_youtube(
        self, context: PipelineContext
    ) -> str:
        """Upload a video to YouTube using the Data API v3.

        Returns the YouTube video ID on success.
        Requires a valid OAuth2 credentials file configured in
        ``config.youtube.credentials_path``.
        """
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise RuntimeError(
                "google-api-python-client and google-auth are required "
                "for YouTube uploads. Install them with: "
                "pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from exc

        creds_path = Path(self.config.youtube.credentials_file)
        if not creds_path.exists():
            raise FileNotFoundError(
                f"YouTube credentials file not found: {creds_path}. "
                "Run the OAuth2 flow first to generate credentials."
            )

        creds_data = json.loads(creds_path.read_text())
        credentials = Credentials.from_authorized_user_info(creds_data)

        youtube = build("youtube", "v3", credentials=credentials)

        seo = context.seo
        body = {
            "snippet": {
                "title": seo.title,
                "description": seo.description,
                "tags": seo.tags,
                "categoryId": seo.category_id,
                "defaultLanguage": seo.default_language,
            },
            "status": {
                "privacyStatus": self.config.youtube.default_privacy,
                "selfDeclaredMadeForKids": seo.made_for_kids,
            },
        }

        media = MediaFileUpload(
            str(context.video.video_path),
            mimetype="video/mp4",
            resumable=True,
        )

        self.logger.info("Starting YouTube upload...")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                self.logger.info(
                    "Upload progress: %d%%",
                    int(status.progress() * 100),
                )

        youtube_video_id = response["id"]

        # Upload thumbnail if available
        if seo.thumbnail_path and Path(seo.thumbnail_path).exists():
            try:
                youtube.thumbnails().set(
                    videoId=youtube_video_id,
                    media_body=MediaFileUpload(
                        str(seo.thumbnail_path), mimetype="image/png"
                    ),
                ).execute()
                self.logger.info("Thumbnail uploaded for %s", youtube_video_id)
            except Exception as e:
                self.logger.warning(
                    "Failed to upload thumbnail: %s", e
                )

        return youtube_video_id

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Checkpoint is valid if it contains an upload result."""
        return data.get("upload") is not None
