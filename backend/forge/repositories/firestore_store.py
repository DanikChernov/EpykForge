from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from forge.repositories.local_store import COLLECTIONS, empty_state


class FirestoreStore:
    """Firestore collection store with staged seed-batch activation.

    Runtime writes go to the currently active batch. Seed imports write a new
    inactive batch first and then swap the active pointer, so dashboards never
    observe the empty state caused by deleting collections before re-seeding.
    """

    def __init__(self, project: str | None = None):
        try:
            from google.cloud import firestore
        except Exception as exc:  # pragma: no cover - requires cloud dependencies
            raise RuntimeError(f"google-cloud-firestore unavailable: {exc}") from exc
        self.client = firestore.Client(project=project)

    @staticmethod
    def _doc_id_for_item(item: dict[str, Any]) -> str | None:
        for key in (
            "event_id",
            "span_id",
            "run_id",
            "machine_id",
            "work_order_id",
            "incident_id",
            "ticket_id",
            "agent_id",
            "decision_id",
            "notification_id",
            "document_id",
            "execution_id",
            "memory_id",
            "approval_id",
            "proposal_id",
            "identity_id",
            "policy_id",
            "part_number",
            "operation_id",
            "alarm_code",
            "history_id",
            "fixture_id",
            "id",
        ):
            value = item.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _active_doc_id(state: dict[str, Any]) -> str:
        meta = state.get("_meta", {})
        batch_id = str(meta.get("seed_batch_id") or "forge-seed")
        seeded_at = str(meta.get("seeded_at") or "unversioned")
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{batch_id}-{seeded_at}").strip("-")
        return cleaned[:240] or "forge-seed-unversioned"

    def _active_batch_id(self) -> str | None:
        doc = self.client.collection("seed_control").document("default").get()
        if not doc.exists:
            return None
        value = doc.to_dict() or {}
        active = value.get("active_firestore_batch_id")
        return str(active) if active else None

    def _collection_ref(self, collection: str, batch_id: str | None = None):
        active = batch_id if batch_id is not None else self._active_batch_id()
        if active:
            return self.client.collection("seed_batches").document(active).collection(collection)
        return self.client.collection(collection)

    def _write_state_to_batch(self, batch_id: str, state: dict[str, Any], *, replace: bool) -> None:
        meta = deepcopy(state.get("_meta", {}))
        meta["active_firestore_batch_id"] = batch_id
        self.client.collection("seed_batches").document(batch_id).set(meta)

        for collection in COLLECTIONS:
            bucket = deepcopy(state.get(collection, {} if collection not in {"events", "traces"} else []))
            expected_doc_ids: set[str] = set()
            batch = self.client.batch()
            writes = 0
            items = (
                bucket
                if isinstance(bucket, list)
                else [{"_doc_id": str(doc_id), **value} for doc_id, value in bucket.items()]
            )
            for item in items:
                doc_id = item.pop("_doc_id", None) or self._doc_id_for_item(item)
                if not doc_id:
                    continue
                doc_id = str(doc_id)
                expected_doc_ids.add(doc_id)
                batch.set(self._collection_ref(collection, batch_id=batch_id).document(doc_id), item)
                writes += 1
                if writes % 450 == 0:
                    batch.commit()
                    batch = self.client.batch()
            batch.commit()

            if replace:
                stale = [
                    doc.reference
                    for doc in self._collection_ref(collection, batch_id=batch_id).stream()
                    if doc.id not in expected_doc_ids
                ]
                delete_batch = self.client.batch()
                for count, ref in enumerate(stale, start=1):
                    delete_batch.delete(ref)
                    if count % 450 == 0:
                        delete_batch.commit()
                        delete_batch = self.client.batch()
                delete_batch.commit()

    def reset(self, state: dict[str, Any]) -> None:
        serializable = deepcopy(state)
        batch_id = self._active_doc_id(serializable)
        self._write_state_to_batch(batch_id, serializable, replace=True)
        control = deepcopy(serializable.get("_meta", {}))
        control["active_firestore_batch_id"] = batch_id
        self.client.collection("seed_control").document("default").set(control)

    def read_state(self) -> dict[str, Any]:
        state = empty_state()
        active_batch_id = self._active_batch_id()
        if active_batch_id:
            meta_doc = self.client.collection("seed_batches").document(active_batch_id).get()
            if meta_doc.exists:
                state["_meta"] = meta_doc.to_dict() or {}
                state["_meta"]["active_firestore_batch_id"] = active_batch_id
        for collection in COLLECTIONS:
            snapshots = list(self._collection_ref(collection, batch_id=active_batch_id).stream())
            docs = [doc.to_dict() | {"_doc_id": doc.id} for doc in snapshots]
            if collection in {"events", "traces"}:
                state[collection] = sorted(
                    docs,
                    key=lambda item: item.get("timestamp") or item.get("started_at") or "",
                )
            else:
                state[collection] = {str(item.pop("_doc_id")): item for item in docs}
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        active_batch_id = self._active_batch_id()
        if not active_batch_id:
            self.reset(state)
            return
        self._write_state_to_batch(active_batch_id, state, replace=True)

    def transaction(self, fn: Callable[[dict[str, Any]], Any]) -> Any:
        state = self.read_state()
        result = fn(state)
        self.write_state(state)
        return result

    def list(self, collection: str) -> list[dict[str, Any]]:
        snapshots = list(self._collection_ref(collection).stream())
        docs = [doc.to_dict() | {"_doc_id": doc.id} for doc in snapshots]
        if collection in {"events", "traces"}:
            return sorted(docs, key=lambda item: item.get("timestamp") or item.get("started_at") or "")
        for item in docs:
            item.pop("_doc_id", None)
        return docs

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        if collection in {"events", "traces"}:
            for item in self.list(collection):
                if item.get("event_id") == doc_id or item.get("span_id") == doc_id:
                    return item
            return None
        doc = self._collection_ref(collection).document(doc_id).get()
        return doc.to_dict() if doc.exists else None

    def upsert(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        self._collection_ref(collection).document(doc_id).set(deepcopy(value))

    def append(self, collection: str, value: dict[str, Any]) -> None:
        doc_id = self._doc_id_for_item(value)
        if not doc_id:
            doc_id = self._collection_ref(collection).document().id
        self.upsert(collection, str(doc_id), value)
