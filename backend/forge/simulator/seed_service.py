from __future__ import annotations

from typing import Any

from forge.agents.manifests import build_agent_manifests
from forge.domain.models import utc_now_iso
from forge.repositories.local_store import LocalStore, empty_state
from forge.simulator.seed import build_seed_state

SEED_PROFILE = "northstar-precision-works-complete-demo"


class DemoDataDisabled(RuntimeError):
    pass


class SeedService:
    def __init__(self, *, store: LocalStore, model: str):
        self.store = store
        self.model = model

    def import_complete_seed(self) -> dict[str, Any]:
        state = build_seed_state(self.model)
        self.store.reset(state)
        return self.status()

    def enable(self) -> dict[str, Any]:
        state = self.store.read_state()
        scenario = state.get("scenario_state", {}).get("default")
        if not state.get("machines") or not state.get("work_orders") or not state.get("knowledge_documents"):
            return self.import_complete_seed()
        scenario["demo_data_enabled"] = True
        scenario["status"] = "RESET"
        scenario["seed_profile"] = SEED_PROFILE
        scenario["updated_at"] = utc_now_iso()
        self.store.write_state(state)
        return self.status()

    def disable(self) -> dict[str, Any]:
        state = empty_state()
        state["agent_registry"] = {
            manifest.agent_id: manifest.model_dump(mode="json")
            for manifest in build_agent_manifests(self.model)
        }
        state["scenario_state"] = {
            "default": {
                "status": "DISABLED",
                "hero_started_at": None,
                "security_attack_enabled": False,
                "force_next_agent_failure": None,
                "forced_failures_seen": [],
                "demo_mode": True,
                "demo_data_enabled": False,
                "seed_profile": SEED_PROFILE,
                "updated_at": utc_now_iso(),
            }
        }
        self.store.reset(state)
        return self.status()

    def status(self) -> dict[str, Any]:
        state = self.store.read_state()
        scenario = state.get("scenario_state", {}).get("default", {})
        return {
            "demo_data_enabled": bool(scenario.get("demo_data_enabled", False)),
            "seed_profile": scenario.get("seed_profile", SEED_PROFILE),
            "scenario_status": scenario.get("status", "UNKNOWN"),
            "collections": {
                "machines": len(state.get("machines", {})),
                "work_orders": len(state.get("work_orders", {})),
                "knowledge_documents": len(state.get("knowledge_documents", {})),
                "events": len(state.get("events", [])),
                "incidents": len(state.get("incidents", {})),
                "agent_registry": len(state.get("agent_registry", {})),
            },
        }

    def require_enabled(self) -> None:
        if not self.status()["demo_data_enabled"]:
            raise DemoDataDisabled("Synthetic demo seed data is disabled. Import or enable demo data first.")
