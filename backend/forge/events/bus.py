from __future__ import annotations

from collections.abc import Callable

from forge.domain.models import MachineEvent


class EventBus:
    def publish(self, topic: str, event: MachineEvent) -> None:
        raise NotImplementedError

    def subscribe(self, topic: str, handler: Callable[[MachineEvent], None]) -> None:
        raise NotImplementedError


class InProcessEventBus(EventBus):
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[MachineEvent], None]]] = {}

    def publish(self, topic: str, event: MachineEvent) -> None:
        for handler in self._subscribers.get(topic, []):
            handler(event)

    def subscribe(self, topic: str, handler: Callable[[MachineEvent], None]) -> None:
        self._subscribers.setdefault(topic, []).append(handler)
