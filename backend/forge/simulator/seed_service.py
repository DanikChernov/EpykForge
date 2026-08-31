from __future__ import annotations

import threading
from typing import Any

from forge.agents.manifests import build_agent_manifests
from forge.domain.models import utc_now_iso
from forge.domain.state_machine import (
    SCENARIO_MESSAGES,
    ScenarioStatus,
    is_active_incident,
    scenario_controls,
)
from forge.repositories.local_store import LocalStore, empty_state
from forge.simulator.seed import SEED_PROFILE, build_seed_state
from forge.simulator.seed_validator import SeedValidationError, validate_seed_state


class DemoDataDisabled(RuntimeError):
    pass


class SeedImportInProgress(RuntimeError):
    pass


class SeedService:
    _import_lock = threading.Lock()

    def __init__(self, *, store: LocalStore, model: str):
        self.store = store
        self.model = model

    def import_complete_seed(self) -> dict[str, Any]:
        acquired = self._import_lock.acquire(timeout=5)
        if not acquired:
            return self.status() | {
                "import_status": "in_progress",
                "message": "A seed import is already running.",
            }
        try:
            candidate = build_seed_state(self.model)
            validation = validate_seed_state(candidate)
            
            # Set import-in-progress flag in metadata before the actual import
            current_state = self.store.read_state()
            current_state.setdefault("_meta", {})["import_in_progress"] = True
            current_state.setdefault("_meta", {})["import_started_at"] = utc_now_iso()
            self.store.write_state(current_state)
            
            # Now perform the actual reset atomically
            self.store.reset(candidate)
            
            # Mark import complete
            final_state = self.store.read_state()
            final_state["_meta"]["import_in_progress"] = False
            final_state["_meta"]["import_completed_at"] = utc_now_iso()
            self.store.write_state(final_state)
            
            return self.status() | {"import_status": "imported", "validation": validation}
        except SeedValidationError:
            # Clear import-in-progress flag on validation failure
            try:
                current_state = self.store.read_state()
                current_state.setdefault("_meta", {})["import_in_progress"] = False
                current_state.setdefault("_meta", {})["import_failed_at"] = utc_now_iso()
                self.store.write_state(current_state)
            except Exception:
                pass
            raise
        finally:
            self._import_lock.release()

    def enable(self) -> dict[str, Any]:
        state = self.store.read_state()
        scenario = state.get("scenario_state", {}).get("default")
        if not state.get("machines") or not state.get("work_orders") or not state.get("knowledge_documents") or not scenario:
            return self.import_complete_seed()
        scenario["demo_data_enabled"] = True
        scenario["status"] = ScenarioStatus.READY.value
        scenario["message"] = SCENARIO_MESSAGES[ScenarioStatus.READY]
        scenario["seed_profile"] = SEED_PROFILE
        scenario["updated_at"] = utc_now_iso()
        self.store.write_state(state)
        return self.status()

    def disable(self) -> dict[str, Any]:
        seeded_at = utc_now_iso()
        state = empty_state()
        state["_meta"] = {
            "seed_schema_version": "disabled",
            "seed_batch_id": "disabled",
            "seeded_at": seeded_at,
            "scenario_id": "disabled",
            "synthetic": True,
            "seed_profile": SEED_PROFILE,
            "facility_name": "Northstar Precision Works",
        }
        state["agent_registry"] = {
            manifest.agent_id: manifest.model_dump(mode="json")
            for manifest in build_agent_manifests(self.model)
        }
        state["agent_identities"] = {
            manifest.agent_id: {
                "identity_id": manifest.agent_id,
                "principal": manifest.agent_id,
                "uri": manifest.identity,
                "allowed_tools": manifest.allowed_tools,
                "denied_tools": manifest.denied_tools,
                "physical_control_allowed": False,
                "synthetic": True,
            }
            for manifest in build_agent_manifests(self.model)
        }
        state["permission_policies"] = {
            "POLICY-DENY-PHYSICAL-CONTROL": {
                "policy_id": "POLICY-DENY-PHYSICAL-CONTROL",
                "effect": "DENY",
                "operations": ["machine.control", "plc.write", "servo.reset"],
                "synthetic": True,
            }
        }
        state["scenario_state"] = {
            "default": {
                "status": ScenarioStatus.DISABLED.value,
                "message": SCENARIO_MESSAGES[ScenarioStatus.DISABLED],
                "hero_started_at": None,
                "run_id": None,
                "security_attack_enabled": False,
                "force_next_agent_failure": None,
                "forced_failures_seen": [],
                "provider_fallbacks": [],
                "demo_mode": True,
                "demo_data_enabled": False,
                "seed_profile": SEED_PROFILE,
                "updated_at": seeded_at,
                "synthetic": True,
            }
        }
        self.store.reset(state)
        return self.status()

    def status(self) -> dict[str, Any]:
        return self.status_from_state(self.store.read_state())

    def status_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        scenario = state.get("scenario_state", {}).get("default", {})
        scenario_status = scenario.get("status", "UNKNOWN")
        active_incidents = [
            incident
            for incident in state.get("incidents", {}).values()
            if is_active_incident(str(incident.get("status")))
        ]
        active_incident_status = str(active_incidents[0]["status"]) if active_incidents else None
        demo_data_enabled = bool(scenario.get("demo_data_enabled", False))
        try:
            status_enum = ScenarioStatus(scenario_status)
            message = scenario.get("message") or SCENARIO_MESSAGES[status_enum]
        except ValueError:
            message = scenario.get("message") or "Scenario state is unknown."
        return {
            "demo_data_enabled": demo_data_enabled,
            "seed_profile": scenario.get("seed_profile", SEED_PROFILE),
            "seed_schema_version": state.get("_meta", {}).get("seed_schema_version"),
            "seed_batch_id": state.get("_meta", {}).get("seed_batch_id"),
            "seeded_at": state.get("_meta", {}).get("seeded_at"),
            "scenario_id": scenario.get("scenario_id") or state.get("_meta", {}).get("scenario_id"),
            "scenario_status": scenario_status,
            "scenario_message": message,
            "run_id": scenario.get("run_id"),
            "provider_fallbacks": scenario.get("provider_fallbacks", []),
            "collections": {
                "machines": len(state.get("machines", {})),
                "work_orders": len(state.get("work_orders", {})),
                "knowledge_documents": len(state.get("knowledge_documents", {})),
                "events": len(state.get("events", [])),
                "incidents": len(state.get("incidents", {})),
                "active_incidents": len(active_incidents),
                "agent_registry": len(state.get("agent_registry", {})),
                "agent_identities": len(state.get("agent_identities", {})),
                "security_events": len(state.get("security_events", {})),
                "traces": len(state.get("traces", [])),
            },
            "controls": scenario_controls(
                status=str(scenario_status),
                demo_data_enabled=demo_data_enabled,
                active_incident_status=active_incident_status,
            ),
        }

    def require_enabled(self) -> None:
        if not self.status()["demo_data_enabled"]:
            raise DemoDataDisabled("Synthetic demo seed data is disabled. Import or enable demo data first.")
