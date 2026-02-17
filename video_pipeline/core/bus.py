"""Event-based message bus for inter-agent communication.

Agents publish events when they start, complete, or fail.
Other agents and the orchestrator subscribe to these events.
This provides observability and loose coupling between agents.
"""

from __future__ import annotations

import asyncio
import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventType(str, enum.Enum):
    """Types of events agents can publish."""

    # Lifecycle events
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_RETRY = "agent.retry"

    # Pipeline events
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"

    # Data events - published when an agent produces output
    TOPIC_RESEARCHED = "data.topic_researched"
    CONTENT_PLANNED = "data.content_planned"
    SCRIPT_WRITTEN = "data.script_written"
    VISUALS_GENERATED = "data.visuals_generated"
    AUDIO_GENERATED = "data.audio_generated"
    VIDEO_COMPOSED = "data.video_composed"
    SEO_OPTIMIZED = "data.seo_optimized"
    VIDEO_UPLOADED = "data.video_uploaded"
    ANALYTICS_COLLECTED = "data.analytics_collected"


@dataclass
class Event:
    """An event published by an agent."""

    event_type: EventType
    agent_name: str
    video_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: str = ""


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class MessageBus:
    """Async event bus for agent communication.

    Usage:
        bus = MessageBus()
        bus.subscribe(EventType.SCRIPT_WRITTEN, my_handler)
        await bus.publish(Event(
            event_type=EventType.SCRIPT_WRITTEN,
            agent_name="scriptwriter",
            video_id="vid_001",
            data={"scenes": 10}
        ))
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._event_log: list[Event] = []
        self._max_log_size = 10000

    def subscribe(
        self, event_type: EventType, handler: EventHandler
    ) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug(
            "Handler %s subscribed to %s",
            handler.__qualname__,
            event_type.value,
        )

    def unsubscribe(
        self, event_type: EventType, handler: EventHandler
    ) -> None:
        """Remove a handler from an event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size:]

        level = (
            logging.ERROR
            if event.event_type == EventType.AGENT_FAILED
            else logging.INFO
        )
        logger.log(
            level,
            "[%s] %s | agent=%s | video=%s%s",
            event.timestamp.strftime("%H:%M:%S"),
            event.event_type.value,
            event.agent_name,
            event.video_id,
            f" | error={event.error}" if event.error else "",
        )

        handlers = self._subscribers.get(event.event_type, [])
        if handlers:
            tasks = [handler(event) for handler in handlers]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "Handler %s failed for event %s: %s",
                        handlers[i].__qualname__,
                        event.event_type.value,
                        result,
                    )

    def get_events(
        self,
        event_type: EventType | None = None,
        video_id: str = "",
        agent_name: str = "",
    ) -> list[Event]:
        """Query the event log with optional filters."""
        events = self._event_log
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if video_id:
            events = [e for e in events if e.video_id == video_id]
        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]
        return events

    def clear_log(self) -> None:
        """Clear the event log."""
        self._event_log.clear()
