"""Base agent class that all pipeline agents inherit from.

Provides:
- Standardized lifecycle (start, run, complete, fail)
- Automatic event publishing via the message bus
- Retry logic with exponential backoff
- Logging
- Checkpoint save/load for resumability
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .bus import Event, EventType, MessageBus
from .config import PipelineConfig
from .models import PipelineContext


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Subclasses must implement:
        - name (property): unique agent identifier
        - _execute(context): the actual work
        - completion_event_type (property): event to publish on success

    Usage:
        agent = MyAgent(config, bus)
        context = await agent.run(context)
    """

    def __init__(
        self, config: PipelineConfig, bus: MessageBus
    ) -> None:
        self.config = config
        self.bus = bus
        self.logger = logging.getLogger(f"agent.{self.name}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this agent."""
        ...

    @property
    @abstractmethod
    def completion_event_type(self) -> EventType:
        """Event type to publish when this agent completes."""
        ...

    @abstractmethod
    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Execute the agent's work. Implemented by subclasses."""
        ...

    async def run(self, context: PipelineContext) -> PipelineContext:
        """Run the agent with retry logic and event publishing."""
        # Check for checkpoint
        checkpoint = self._load_checkpoint(context.video_id)
        if checkpoint:
            self.logger.info(
                "Resuming from checkpoint for video %s",
                context.video_id,
            )
            return PipelineContext(**checkpoint)

        await self.bus.publish(
            Event(
                event_type=EventType.AGENT_STARTED,
                agent_name=self.name,
                video_id=context.video_id,
            )
        )

        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self._execute(context)

                # Save checkpoint
                self._save_checkpoint(result)

                await self.bus.publish(
                    Event(
                        event_type=self.completion_event_type,
                        agent_name=self.name,
                        video_id=context.video_id,
                    )
                )
                await self.bus.publish(
                    Event(
                        event_type=EventType.AGENT_COMPLETED,
                        agent_name=self.name,
                        video_id=context.video_id,
                    )
                )

                return result

            except Exception as e:
                last_error = e
                self.logger.warning(
                    "Attempt %d/%d failed: %s",
                    attempt,
                    self.config.max_retries,
                    str(e),
                )

                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay_seconds * (2 ** (attempt - 1))
                    await self.bus.publish(
                        Event(
                            event_type=EventType.AGENT_RETRY,
                            agent_name=self.name,
                            video_id=context.video_id,
                            data={"attempt": attempt, "delay": delay},
                            error=str(e),
                        )
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        error_msg = f"Agent {self.name} failed after {self.config.max_retries} attempts: {last_error}"
        context.errors.append(error_msg)
        self.logger.error(error_msg)

        await self.bus.publish(
            Event(
                event_type=EventType.AGENT_FAILED,
                agent_name=self.name,
                video_id=context.video_id,
                error=error_msg,
            )
        )

        raise RuntimeError(error_msg) from last_error

    def _checkpoint_path(self, video_id: str) -> Path:
        """Get the checkpoint file path for this agent and video."""
        cp_dir = Path(self.config.checkpoint_dir)
        return cp_dir / f"{video_id}_{self.name}.json"

    def _save_checkpoint(self, context: PipelineContext) -> None:
        """Save pipeline context as checkpoint."""
        if not self.config.checkpoint_enabled:
            return
        try:
            cp_dir = Path(self.config.checkpoint_dir)
            cp_dir.mkdir(parents=True, exist_ok=True)
            cp_path = self._checkpoint_path(context.video_id)
            cp_path.write_text(context.model_dump_json(indent=2))
            self.logger.debug("Checkpoint saved: %s", cp_path)
        except Exception as e:
            self.logger.warning("Failed to save checkpoint: %s", e)

    def _load_checkpoint(self, video_id: str) -> dict[str, Any] | None:
        """Load checkpoint if it exists."""
        if not self.config.checkpoint_enabled:
            return None
        cp_path = self._checkpoint_path(video_id)
        if cp_path.exists():
            try:
                data = json.loads(cp_path.read_text())
                # Verify the checkpoint has our agent's output
                if self._validate_checkpoint(data):
                    return data
            except Exception as e:
                self.logger.warning("Failed to load checkpoint: %s", e)
        return None

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Validate that checkpoint data contains this agent's output.

        Override in subclasses for specific validation.
        """
        return False  # Default: don't use checkpoints unless overridden

    def _ensure_dir(self, path: Path) -> Path:
        """Ensure a directory exists and return it."""
        path.mkdir(parents=True, exist_ok=True)
        return path
