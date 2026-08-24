from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from forge.repositories.local_store import COLLECTIONS, empty_state


class FirestoreStore:
    """Firestore collection store with the same interface as LocalStore."""

    def __init__(self, project: str | None = None):
        try:
            from google.cloud import firestore
        except Exception as exc:  # pragma: no cover - requires cloud dependencies
            raise RuntimeError(f"google-cloud-firestore unavailable: {exc}") from exc
        self.client = firestore.Client(project=project)

    def reset(self, state: dict[str, Any]) -> None:
        for collection in COLLECTIONS:
            docs = list(self.client.collection(collection).stream())
            batch = self.client.batch()
            for count, doc in enumerate(docs, start=1):
                batch.delete(doc.reference)
                if count % 450 == 0:
                    batch.commit()
                    batch = self.client.batch()
            batch.commit()

        serializable = deepcopy(state)
        for collection, bucket in serializable.items():
            if isinstance(bucket, list):
                for item in bucket:
                    doc_id = item.get("event_id") or item.get("span_id") or item.get("id")
                    if doc_id:
                        self.upsert(collection, doc_id, item)
            else:
                for doc_id, value in bucket.items():
                    self.upsert(collection, str(doc_id), value)

    def read_state(self) -> dict[str, Any]:
        state = empty_state()
        for collection in COLLECTIONS:
            snapshots = list(self.client.collection(collection).stream())
            docs = [doc.to_dict() | {"_doc_id": doc.id} for doc in snapshots]
            if collection in {"events", "traces"}:
                state[collection] = sorted(docs, key=lambda item: item.get("timestamp") or item.get("started_at") or "")
            else:
                state[collection] = {
                    str(item.pop("_doc_id")): item
                    for item in docs
                }
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        self.reset(state)

    def transaction(self, fn: Callable[[dict[str, Any]], Any]) -> Any:
        state = self.read_state()
        result = fn(state)
        self.write_state(state)
        return result

    def list(self, collection: str) -> list[dict[str, Any]]:
        if collection in {"events", "traces"}:
            return self.read_state().get(collection, [])
        return list(self.read_state().get(collection, {}).values())

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        if collection in {"events", "traces"}:
            for item in self.list(collection):
                if item.get("event_id") == doc_id or item.get("span_id") == doc_id:
                    return item
            return None
        doc = self.client.collection(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    def upsert(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        self.client.collection(collection).document(doc_id).set(deepcopy(value))

    def append(self, collection: str, value: dict[str, Any]) -> None:
        doc_id = value.get("event_id") or value.get("span_id") or value.get("id")
        if not doc_id:
            doc_id = self.client.collection(collection).document().id
        self.upsert(collection, str(doc_id), value)
