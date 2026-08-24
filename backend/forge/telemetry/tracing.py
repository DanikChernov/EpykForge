from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from forge.domain.models import TraceSpan
from forge.repositories.local_store import LocalStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceRecorder:
    def __init__(self, store: LocalStore):
        self.store = store

    @contextmanager
    def span(
        self,
        *,
        trace_id: str,
        correlation_id: str,
        name: str,
        agent_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        span = TraceSpan(
            trace_id=trace_id,
            correlation_id=correlation_id,
            name=name,
            agent_id=agent_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        start = perf_counter()
        try:
            yield span
        except Exception as exc:
            span.status = "ERROR"
            span.attributes["error"] = str(exc)
            raise
        finally:
            span.ended_at = _now_iso()
            span.duration_ms = int((perf_counter() - start) * 1000)
            self.store.append("traces", span.model_dump(mode="json"))
