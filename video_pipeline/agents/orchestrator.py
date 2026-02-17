"""Orchestrator - Coordinates all agents in the video production pipeline.

Manages the sequential execution of agents for each video,
handles errors, publishes pipeline-level events, and supports
batch production of multiple videos.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.bus import Event, EventType, MessageBus
from ..core.config import PipelineConfig
from ..core.models import PipelineContext

if TYPE_CHECKING:
    from ..core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Runs the full video production pipeline.

    Pipeline order:
        Research -> Planner -> Scriptwriter -> [Visuals, Audio] -> Composer -> SEO -> Upload -> Analytics

    Usage:
        orchestrator = Orchestrator(config, bus)
        results = await orchestrator.run_batch(count=5)
    """

    def __init__(self, config: PipelineConfig, bus: MessageBus) -> None:
        self.config = config
        self.bus = bus
        self._agents: dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the orchestrator."""
        self._agents[agent.name] = agent
        logger.info("Registered agent: %s", agent.name)

    async def run_single(self, video_id: str = "") -> PipelineContext:
        """Run the full pipeline for a single video.

        Returns the completed PipelineContext with all artifacts.
        """
        context = PipelineContext(
            video_id=video_id or "pending",
            started_at=datetime.now(),
        )

        await self.bus.publish(Event(
            event_type=EventType.PIPELINE_STARTED,
            agent_name="orchestrator",
            video_id=context.video_id,
        ))

        # Define the pipeline stages in order
        stages = [
            "research",
            "planner",
            "scriptwriter",
            "visuals",
            "audio",
            "composer",
            "seo",
            "uploader",
            "analytics",
        ]

        try:
            for stage_name in stages:
                agent = self._agents.get(stage_name)
                if agent is None:
                    logger.warning("Agent '%s' not registered, skipping", stage_name)
                    continue

                logger.info(
                    "=== Stage: %s (video: %s) ===",
                    stage_name,
                    context.video_id,
                )
                context = await agent.run(context)

            context.completed_at = datetime.now()

            await self.bus.publish(Event(
                event_type=EventType.PIPELINE_COMPLETED,
                agent_name="orchestrator",
                video_id=context.video_id,
                data={
                    "duration_seconds": (
                        context.completed_at - context.started_at
                    ).total_seconds()
                    if context.started_at
                    else 0,
                },
            ))

            logger.info(
                "Pipeline complete for %s in %.1fs",
                context.video_id,
                (context.completed_at - context.started_at).total_seconds()
                if context.started_at
                else 0,
            )

        except Exception as e:
            context.errors.append(str(e))
            await self.bus.publish(Event(
                event_type=EventType.PIPELINE_FAILED,
                agent_name="orchestrator",
                video_id=context.video_id,
                error=str(e),
            ))
            logger.error("Pipeline failed for %s: %s", context.video_id, e)

        return context

    async def run_batch(self, count: int | None = None) -> list[PipelineContext]:
        """Run the pipeline for multiple videos sequentially.

        Args:
            count: Number of videos to produce. Defaults to config.content.videos_per_batch.

        Returns:
            List of PipelineContext results.
        """
        if count is None:
            count = self.config.content.videos_per_batch

        results: list[PipelineContext] = []
        logger.info("Starting batch production of %d videos", count)

        for i in range(count):
            logger.info("--- Video %d/%d ---", i + 1, count)
            try:
                result = await self.run_single()
                results.append(result)

                # Log success/failure
                if result.errors:
                    logger.warning(
                        "Video %d had errors: %s",
                        i + 1,
                        result.errors,
                    )
                else:
                    logger.info(
                        "Video %d complete: %s",
                        i + 1,
                        result.video_id,
                    )
            except Exception as e:
                logger.error("Video %d failed fatally: %s", i + 1, e)
                results.append(PipelineContext(
                    video_id=f"failed_{i}",
                    errors=[str(e)],
                ))

        # Save batch summary
        self._save_batch_summary(results)

        succeeded = sum(1 for r in results if not r.errors)
        failed = sum(1 for r in results if r.errors)
        logger.info(
            "Batch complete: %d succeeded, %d failed out of %d",
            succeeded,
            failed,
            count,
        )

        return results

    def _save_batch_summary(self, results: list[PipelineContext]) -> None:
        """Save a summary of the batch run."""
        summary_dir = Path(self.config.data_dir)
        summary_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "succeeded": sum(1 for r in results if not r.errors),
            "failed": sum(1 for r in results if r.errors),
            "videos": [],
        }

        for r in results:
            video_info = {
                "video_id": r.video_id,
                "success": not bool(r.errors),
                "errors": r.errors,
            }
            if r.plan:
                video_info["title"] = r.plan.title_working
                video_info["type"] = r.plan.video_type.value
            if r.video:
                video_info["video_path"] = str(r.video.video_path)
                video_info["duration"] = r.video.duration_seconds
            if r.upload and r.upload.youtube_url:
                video_info["youtube_url"] = r.upload.youtube_url
            summary["videos"].append(video_info)

        summary_file = summary_dir / "batch_summary.json"
        try:
            summary_file.write_text(json.dumps(summary, indent=2))
            logger.info("Batch summary saved to %s", summary_file)
        except Exception as e:
            logger.warning("Failed to save batch summary: %s", e)
