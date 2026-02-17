"""Main entry point for the Baby Content Video Pipeline.

Usage:
    # Produce a single video
    python -m video_pipeline.main --single

    # Produce a batch of videos (default: 5)
    python -m video_pipeline.main --batch 5

    # Use custom config
    python -m video_pipeline.main --config my_config.yaml --batch 3

    # Dry run (research + plan + script only, no rendering)
    python -m video_pipeline.main --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .core.bus import MessageBus
from .core.config import PipelineConfig, load_config
from .agents.research import ResearchAgent
from .agents.planner import PlannerAgent
from .agents.scriptwriter import ScriptwriterAgent
from .agents.visuals import VisualGeneratorAgent
from .agents.audio import AudioAgent
from .agents.composer import VideoComposerAgent
from .agents.seo import SEOAgent
from .agents.uploader import UploadAgent
from .agents.analytics import AnalyticsAgent
from .agents.orchestrator import Orchestrator


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the pipeline."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("pipeline.log", mode="a"),
        ],
    )
    # Suppress noisy third-party loggers
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("moviepy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_pipeline(
    config: PipelineConfig,
    bus: MessageBus,
    dry_run: bool = False,
) -> Orchestrator:
    """Build the full pipeline with all agents registered."""
    orchestrator = Orchestrator(config, bus)

    # Always register these (lightweight)
    orchestrator.register_agent(ResearchAgent(config, bus))
    orchestrator.register_agent(PlannerAgent(config, bus))
    orchestrator.register_agent(ScriptwriterAgent(config, bus))

    if not dry_run:
        # Heavy agents - only for actual production
        orchestrator.register_agent(VisualGeneratorAgent(config, bus))
        orchestrator.register_agent(AudioAgent(config, bus))
        orchestrator.register_agent(VideoComposerAgent(config, bus))
        orchestrator.register_agent(SEOAgent(config, bus))
        orchestrator.register_agent(UploadAgent(config, bus))
        orchestrator.register_agent(AnalyticsAgent(config, bus))

    return orchestrator


async def run(args: argparse.Namespace) -> None:
    """Main async entry point."""
    config = load_config(args.config)
    setup_logging(config.log_level)

    logger = logging.getLogger("pipeline")
    logger.info("=" * 60)
    logger.info("Baby Content Video Pipeline v1.0")
    logger.info("=" * 60)

    # Ensure output directories exist
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    Path(config.temp_dir).mkdir(parents=True, exist_ok=True)

    bus = MessageBus()
    orchestrator = build_pipeline(config, bus, dry_run=args.dry_run)

    if args.dry_run:
        logger.info("DRY RUN mode - will only research, plan, and script")

    if args.single:
        logger.info("Producing 1 video...")
        result = await orchestrator.run_single()
        _print_result(result)
    else:
        count = args.batch or config.content.videos_per_batch
        logger.info("Producing %d videos...", count)
        results = await orchestrator.run_batch(count)
        _print_batch_results(results)


def _print_result(ctx) -> None:
    """Print a single video result summary."""
    print("\n" + "=" * 50)
    print("RESULT")
    print("=" * 50)
    print(f"  Video ID:  {ctx.video_id}")

    if ctx.plan:
        print(f"  Title:     {ctx.plan.title_working}")
        print(f"  Type:      {ctx.plan.video_type.value}")

    if ctx.script:
        print(f"  Scenes:    {len(ctx.script.scenes)}")
        print(f"  Duration:  {ctx.script.total_duration_seconds:.0f}s")

    if ctx.video:
        print(f"  Video:     {ctx.video.video_path}")
        print(f"  Size:      {ctx.video.file_size_mb:.1f} MB")

    if ctx.upload and ctx.upload.youtube_url:
        print(f"  YouTube:   {ctx.upload.youtube_url}")

    if ctx.errors:
        print(f"  ERRORS:    {ctx.errors}")

    print("=" * 50)


def _print_batch_results(results: list) -> None:
    """Print batch results summary."""
    succeeded = [r for r in results if not r.errors]
    failed = [r for r in results if r.errors]

    print("\n" + "=" * 50)
    print(f"BATCH COMPLETE: {len(succeeded)} succeeded, {len(failed)} failed")
    print("=" * 50)

    for r in succeeded:
        title = r.plan.title_working if r.plan else "Unknown"
        path = str(r.video.video_path) if r.video else "N/A"
        print(f"  OK   {r.video_id}: {title}")
        print(f"       -> {path}")

    for r in failed:
        print(f"  FAIL {r.video_id}: {r.errors[0] if r.errors else 'Unknown error'}")

    print("=" * 50)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Baby Content Video Pipeline - Automated YouTube video production",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m video_pipeline.main --single           # Produce 1 video
  python -m video_pipeline.main --batch 5           # Produce 5 videos
  python -m video_pipeline.main --dry-run           # Plan only, no rendering
  python -m video_pipeline.main --config custom.yaml  # Custom config
        """,
    )

    parser.add_argument(
        "--single",
        action="store_true",
        help="Produce a single video",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Number of videos to produce in batch mode",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only research, plan, and script - no rendering or upload",
    )

    args = parser.parse_args()

    # Default to single video if no mode specified
    if not args.single and args.batch is None:
        args.single = True

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
