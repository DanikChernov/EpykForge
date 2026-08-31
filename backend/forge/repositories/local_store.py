from __future__ import annotations

import json
import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

COLLECTIONS = [
    "machines",
    "work_orders",
    "incidents",
    "maintenance_tasks",
    "production_schedule",
    "events",
    "agent_runs",
    "agent_registry",
    "policy_decisions",
    "notifications",
    "knowledge_documents",
    "scenario_state",
    "traces",
    "security_events",
    "action_executions",
    "memories",
    "approvals",
    "schedule_proposals",
    "agent_identities",
    "permission_policies",
    "parts",
    "operations",
    "alarm_definitions",
    "maintenance_history",
    "notification_rules",
    "security_fixtures",
    "retry_fixtures",
    "model_invocations",
    "idempotency",
]


def empty_state() -> dict[str, Any]:
    state: dict[str, Any] = {"_meta": {}}
    for collection in COLLECTIONS:
        state[collection] = {} if collection not in {"events", "traces"} else []
    return state


class LocalStore:
    """Small JSON-backed store used locally and in tests.

    The interface intentionally mirrors collection-style document access so the
    application can switch to Firestore without rewriting domain logic.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.reset(empty_state())

    def reset(self, state: dict[str, Any]) -> None:
        with self._lock:
            serializable = deepcopy(state)
            serializable.setdefault("_meta", {})
            for collection in COLLECTIONS:
                serializable.setdefault(collection, {} if collection not in {"events", "traces"} else [])
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(serializable, indent=2, sort_keys=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)

    def read_state(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def write_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            serializable = deepcopy(state)
            serializable.setdefault("_meta", {})
            for collection in COLLECTIONS:
                serializable.setdefault(collection, {} if collection not in {"events", "traces"} else [])
            payload = json.dumps(serializable, indent=2, sort_keys=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.path)

    def transaction(self, fn: Callable[[dict[str, Any]], Any]) -> Any:
        with self._lock:
            state = self.read_state()
            result = fn(state)
            self.write_state(state)
            return result

    def list(self, collection: str) -> list[dict[str, Any]]:
        state = self.read_state()
        bucket = state.get(collection, {})
        if isinstance(bucket, list):
            return deepcopy(bucket)
        return deepcopy(list(bucket.values()))

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        state = self.read_state()
        bucket = state.get(collection, {})
        if isinstance(bucket, list):
            for item in bucket:
                if item.get("event_id") == doc_id or item.get("span_id") == doc_id:
                    return deepcopy(item)
            return None
        item = bucket.get(doc_id)
        return deepcopy(item) if item is not None else None

    def upsert(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        def write(state: dict[str, Any]) -> None:
            bucket = state.setdefault(collection, {})
            if isinstance(bucket, list):
                raise TypeError(f"{collection} is append-only")
            bucket[doc_id] = deepcopy(value)

        self.transaction(write)

    def append(self, collection: str, value: dict[str, Any]) -> None:
        def write(state: dict[str, Any]) -> None:
            bucket = state.setdefault(collection, [])
            if not isinstance(bucket, list):
                raise TypeError(f"{collection} is keyed, not append-only")
            bucket.append(deepcopy(value))

        self.transaction(write)
