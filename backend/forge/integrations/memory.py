from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from forge.domain.models import OperationalMemory
from forge.repositories.local_store import LocalStore


class MemoryService(Protocol):
    def write(self, memory: OperationalMemory) -> OperationalMemory:
        ...

    def list_for_machine(self, machine_id: str) -> list[OperationalMemory]:
        ...


@dataclass
class StoreMemoryService:
    store: LocalStore

    def write(self, memory: OperationalMemory) -> OperationalMemory:
        self.store.upsert("memories", memory.memory_id, memory.model_dump(mode="json"))
        return memory

    def list_for_machine(self, machine_id: str) -> list[OperationalMemory]:
        return [
            OperationalMemory.model_validate(row)
            for row in self.store.list("memories")
            if row.get("machine_id") == machine_id
        ]


class MemoryBankService:
    """Adapter shell for Agent Platform Memory Bank.

    This class is intentionally not wired in local mode. Activate it only after
    creating a Memory Bank-backed Agent Runtime and verifying the resource name.
    """

    def __init__(self, resource_name: str):
        self.resource_name = resource_name

    def write(self, memory: OperationalMemory) -> OperationalMemory:
        raise NotImplementedError("Memory Bank write requires verified Agent Runtime Memory Bank resource")

    def list_for_machine(self, machine_id: str) -> list[OperationalMemory]:
        raise NotImplementedError("Memory Bank retrieval requires verified Agent Runtime Memory Bank resource")
