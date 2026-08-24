from __future__ import annotations

from collections.abc import Callable

from forge.domain.models import MachineEvent
from forge.events.bus import EventBus


class PubSubEventBus(EventBus):
    """Google Pub/Sub publisher for cloud event boundaries."""

    def __init__(self, *, project_id: str, topic_prefix: str = "epyk-forge"):
        try:
            from google.cloud import pubsub_v1
        except Exception as exc:  # pragma: no cover - requires cloud dependencies
            raise RuntimeError(f"google-cloud-pubsub unavailable: {exc}") from exc
        self.project_id = project_id
        self.topic_prefix = topic_prefix
        self.publisher = pubsub_v1.PublisherClient()

    def publish(self, topic: str, event: MachineEvent) -> None:
        topic_path = self.publisher.topic_path(self.project_id, f"{self.topic_prefix}-{topic}")
        self.publisher.publish(
            topic_path,
            event.model_dump_json().encode("utf-8"),
            correlation_id=event.correlation_id,
            event_type=event.event_type.value,
        ).result(timeout=15)

    def subscribe(self, topic: str, handler: Callable[[MachineEvent], None]) -> None:
        raise NotImplementedError(
            "Cloud Pub/Sub subscriptions are deployed as push/pull infrastructure; "
            "do not start long-lived subscribers inside the web request process."
        )
