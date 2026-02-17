"""Analytics Agent - Collects performance metrics from YouTube.

Retrieves view counts, watch time, CTR, and other metrics via the
YouTube Analytics API so the pipeline can learn which content
performs best and inform future topic research.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import AnalyticsSnapshot, PipelineContext


class AnalyticsAgent(BaseAgent):
    """Collects YouTube performance analytics for uploaded videos.

    Pipeline position: after UploadAgent (optional / deferred).
    Produces: AnalyticsSnapshot attached to the pipeline context.
    """

    @property
    def name(self) -> str:
        return "analytics"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.ANALYTICS_COLLECTED

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Collect analytics for an uploaded video.

        Steps:
            1. Verify the video has been uploaded.
            2. If dry-run mode, return zeroed-out placeholder metrics.
            3. Otherwise, query YouTube Analytics API for real data.
            4. Attach the snapshot to the pipeline context.
        """
        if context.upload is None:
            raise ValueError(
                "No upload result in context - uploader agent must run first"
            )

        video_id = context.video_id
        youtube_video_id = context.upload.youtube_video_id

        # Dry-run mode: return placeholder analytics
        if getattr(self.config, "dry_run", False):
            self.logger.info(
                "DRY RUN: Skipping analytics collection for %s",
                video_id,
            )
            context.analytics = AnalyticsSnapshot(
                video_id=video_id,
                youtube_video_id=youtube_video_id,
                views=0,
                watch_time_hours=0,
                likes=0,
                subscribers_gained=0,
                ctr_percent=0,
                avg_view_duration_seconds=0,
                revenue_estimate_usd=0,
                collected_at=datetime.now(),
            )
            return context

        # Real analytics collection
        snapshot = await self._fetch_analytics(
            video_id, youtube_video_id
        )
        context.analytics = snapshot

        self.logger.info(
            "Analytics collected for %s: %d views, %.1f hrs watch time, %.1f%% CTR",
            youtube_video_id,
            snapshot.views,
            snapshot.watch_time_hours,
            snapshot.ctr_percent,
        )
        return context

    async def _fetch_analytics(
        self, video_id: str, youtube_video_id: str
    ) -> AnalyticsSnapshot:
        """Fetch analytics from YouTube Analytics API.

        Requires a valid OAuth2 credentials file with YouTube Analytics
        scope configured in ``config.youtube.credentials_path``.
        """
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
        except ImportError as exc:
            raise RuntimeError(
                "google-api-python-client and google-auth are required "
                "for YouTube analytics. Install them with: "
                "pip install google-api-python-client google-auth"
            ) from exc

        creds_path = Path(self.config.youtube.credentials_file)
        if not creds_path.exists():
            raise FileNotFoundError(
                f"YouTube credentials file not found: {creds_path}"
            )

        creds_data = json.loads(creds_path.read_text())
        credentials = Credentials.from_authorized_user_info(creds_data)

        youtube = build("youtube", "v3", credentials=credentials)
        youtube_analytics = build(
            "youtubeAnalytics", "v2", credentials=credentials
        )

        # Get basic video stats from Data API
        video_response = youtube.videos().list(
            part="statistics",
            id=youtube_video_id,
        ).execute()

        stats = {}
        if video_response.get("items"):
            stats = video_response["items"][0].get("statistics", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))

        # Get detailed analytics from Analytics API
        today = datetime.now().strftime("%Y-%m-%d")
        analytics_response = youtube_analytics.reports().query(
            ids="channel==MINE",
            startDate="2020-01-01",
            endDate=today,
            metrics="estimatedMinutesWatched,averageViewDuration,subscribersGained",
            filters=f"video=={youtube_video_id}",
        ).execute()

        watch_minutes = 0.0
        avg_view_duration = 0.0
        subscribers_gained = 0

        rows = analytics_response.get("rows", [])
        if rows:
            row = rows[0]
            watch_minutes = float(row[0]) if len(row) > 0 else 0
            avg_view_duration = float(row[1]) if len(row) > 1 else 0
            subscribers_gained = int(row[2]) if len(row) > 2 else 0

        # CTR requires cardClickRate or impressionClickThroughRate
        ctr = 0.0
        try:
            ctr_response = youtube_analytics.reports().query(
                ids="channel==MINE",
                startDate="2020-01-01",
                endDate=today,
                metrics="impressions,impressionClickThroughRate",
                filters=f"video=={youtube_video_id}",
            ).execute()
            ctr_rows = ctr_response.get("rows", [])
            if ctr_rows and len(ctr_rows[0]) > 1:
                ctr = float(ctr_rows[0][1])
        except Exception as e:
            self.logger.warning("Could not fetch CTR data: %s", e)

        return AnalyticsSnapshot(
            video_id=video_id,
            youtube_video_id=youtube_video_id,
            views=views,
            watch_time_hours=round(watch_minutes / 60, 2),
            likes=likes,
            subscribers_gained=subscribers_gained,
            ctr_percent=round(ctr, 2),
            avg_view_duration_seconds=avg_view_duration,
            revenue_estimate_usd=0,  # requires YouTube Partner API
            collected_at=datetime.now(),
        )

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Checkpoint is valid if it contains analytics data."""
        return data.get("analytics") is not None
