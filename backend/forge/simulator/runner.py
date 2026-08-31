from __future__ import annotations

import time
from typing import Any

from forge.domain.models import (
    EventType,
    Incident,
    IncidentStatus,
    Machine,
    MachineEvent,
    MachineState,
    TelemetrySample,
    utc_now_iso,
)
from forge.domain.state_machine import ScenarioStatus, transition_incident, transition_scenario
from forge.events.ingestion import EventIngestionService
from forge.repositories.local_store import LocalStore
from forge.simulator.seed_service import DemoDataDisabled
from forge.tools.actions import ToolExecutor

HERO_CORRELATION_ID = "trc_servo_overload_cascade"


class DemoScenarioRunner:
    def __init__(self, *, store: LocalStore, ingestion: EventIngestionService, tools: ToolExecutor):
        self.store = store
        self.ingestion = ingestion
        self.tools = tools

    def _sleep(self, seconds: float, speed: float) -> None:
        if speed <= 0:
            return
        time.sleep(max(seconds / speed, 0))

    def emit(self, event: MachineEvent) -> dict[str, Any]:
        return self.ingestion.ingest(event)

    def run_hero(self, *, speed: float = 8.0, sleep: bool = True) -> dict[str, Any]:
        self._require_demo_enabled()
        self._reject_if_active_incident()
        self._transition_scenario_status(ScenarioStatus.RUNNING_PRECURSOR)
        samples = [
            (70, 187, "servo-load rising above baseline"),
            (78, 190, "cycle-time drift emerging"),
            (86, 194, "repeated short feed hold likely"),
            (92, 196, "critical axis load trend before alarm"),
        ]
        emitted: list[str] = []
        for idx, (x_load, cycle, note) in enumerate(samples, start=1):
            event = MachineEvent(
                event_id=f"evt_mc04_pre_{idx}",
                event_type=EventType.TELEMETRY,
                source="factory-simulator",
                machine_id="MC-04",
                work_order_id="MO-4821",
                correlation_id=HERO_CORRELATION_ID,
                trace_id=HERO_CORRELATION_ID,
                payload=TelemetrySample(
                    x_axis_load_pct=x_load,
                    y_axis_load_pct=43,
                    z_axis_load_pct=40,
                    spindle_load_pct=55,
                    observed_cycle_time_sec=cycle,
                    target_cycle_time_sec=184,
                    tool_life_remaining_pct=61,
                ).model_dump(mode="json")
                | {"note": note},
            )
            self.emit(event)
            emitted.append(event.event_id)
            if idx in {2, 3}:
                feed_hold = MachineEvent(
                    event_id=f"evt_mc04_feed_hold_{idx}",
                    event_type=EventType.FEED_HOLD,
                    source="factory-simulator",
                    machine_id="MC-04",
                    work_order_id="MO-4821",
                    correlation_id=HERO_CORRELATION_ID,
                    trace_id=HERO_CORRELATION_ID,
                    payload={"duration_seconds": 9, "note": "short automatic feed hold"},
                )
                self.emit(feed_hold)
                emitted.append(feed_hold.event_id)
            if sleep:
                self._sleep(4, speed)

        self._transition_scenario_status(ScenarioStatus.ALARMED)
        alarm = MachineEvent(
            event_id="evt_mc04_alarm_servo_x",
            event_type=EventType.ALARM,
            source="factory-simulator",
            machine_id="MC-04",
            work_order_id="MO-4821",
            correlation_id=HERO_CORRELATION_ID,
            trace_id=HERO_CORRELATION_ID,
            payload={
                "code": "AXIS_SERVO_OVERLOAD_X",
                "severity": "CRITICAL",
                "message": "X-axis servo overload detected by synthetic controller",
            },
        )
        result = self.emit(alarm)
        emitted.append(alarm.event_id)
        if result.get("incident_id"):
            self._transition_scenario_status(ScenarioStatus.INCIDENT_ACTIVE)
            incident_raw = self.store.get("incidents", str(result["incident_id"]))
            if incident_raw and incident_raw.get("status") == IncidentStatus.AWAITING_APPROVAL.value:
                self._transition_scenario_status(ScenarioStatus.AWAITING_APPROVAL)
        return {"status": "started", "events": emitted, "incident_id": result.get("incident_id")}

    def inject_servo_alarm(self) -> dict[str, Any]:
        self._require_demo_enabled()
        self._reject_if_active_incident()
        if self._scenario_status() == ScenarioStatus.READY:
            self._transition_scenario_status(ScenarioStatus.RUNNING_PRECURSOR)
        if self._scenario_status() == ScenarioStatus.RUNNING_PRECURSOR:
            self._transition_scenario_status(ScenarioStatus.ALARMED)
        alarm = MachineEvent(
            event_id="evt_mc04_alarm_servo_x_manual",
            event_type=EventType.ALARM,
            source="synthetic-demo-controls",
            machine_id="MC-04",
            work_order_id="MO-4821",
            correlation_id=HERO_CORRELATION_ID,
            trace_id=HERO_CORRELATION_ID,
            payload={"code": "AXIS_SERVO_OVERLOAD_X", "severity": "CRITICAL"},
        )
        result = self.emit(alarm)
        if result.get("incident_id"):
            self._transition_scenario_status(ScenarioStatus.INCIDENT_ACTIVE)
            incident_raw = self.store.get("incidents", str(result["incident_id"]))
            if incident_raw and incident_raw.get("status") == IncidentStatus.AWAITING_APPROVAL.value:
                self._transition_scenario_status(ScenarioStatus.AWAITING_APPROVAL)
        return result

    def enable_security_attack(self) -> dict[str, Any]:
        self._require_demo_enabled()
        def update(state: dict[str, Any]) -> dict[str, Any]:
            scenario = state["scenario_state"]["default"]
            scenario["security_attack_enabled"] = True
            scenario["updated_at"] = utc_now_iso()
            return scenario

        return self.store.transaction(update)

    def run_security_test(self) -> dict[str, Any]:
        self.enable_security_attack()
        result = self.run_hero(speed=99, sleep=False)
        return result | {"security_events": len(self.store.list("security_events"))}

    def inject_failure(self, agent_id: str = "diagnostic-agent") -> dict[str, Any]:
        self._require_demo_enabled()
        def update(state: dict[str, Any]) -> dict[str, Any]:
            scenario = state["scenario_state"]["default"]
            scenario["force_next_agent_failure"] = agent_id
            scenario["forced_failures_seen"] = []
            scenario["updated_at"] = utc_now_iso()
            return scenario

        return self.store.transaction(update)

    def run_retry_test(self, agent_id: str = "diagnostic-agent") -> dict[str, Any]:
        self.inject_failure(agent_id)
        result = self.run_hero(speed=99, sleep=False)
        runs = [
            run
            for run in self.store.list("agent_runs")
            if run.get("incident_id") == result.get("incident_id") and run.get("agent_id") == agent_id
        ]
        return result | {"retry_runs": runs}

    def resolve_maintenance_step(self) -> dict[str, Any]:
        self._require_demo_enabled()
        incident_raw = self.store.get("incidents", "INC-1042")
        if not incident_raw:
            return {"status": "missing_incident"}
        incident = Incident.model_validate(incident_raw)
        event = MachineEvent(
            event_id="evt_mc04_recovery_verified",
            event_type=EventType.RECOVERY,
            source="synthetic-demo-controls",
            machine_id="MC-04",
            work_order_id="MO-4821",
            correlation_id=incident.correlation_id,
            trace_id=incident.correlation_id,
            payload={
                "technician_note": "Synthetic technician cleared chip accumulation near X-axis cover area.",
                "verification_cycles": 3,
                "x_axis_load_pct": 58,
                "observed_cycle_time_sec": 186,
            },
        )
        self.emit(event)

        def update(state: dict[str, Any]) -> dict[str, Any]:
            current = Incident.model_validate(state["incidents"]["INC-1042"])
            machine = Machine.model_validate(state["machines"]["MC-04"])
            machine.state = MachineState.RUNNING
            machine.active_alarm_codes = []
            machine.health_score = 88
            machine.at_risk = False
            state["machines"][machine.machine_id] = machine.model_dump(mode="json")
            if current.status == IncidentStatus.MONITORING:
                current = transition_incident(current, IncidentStatus.RESOLVED)
                current.resolution_summary = (
                    "Synthetic maintenance resolved MC-04 after chip accumulation inspection; "
                    "verification cycles returned X-axis load and cycle time to acceptable limits."
                )
                current.learned_at = utc_now_iso()
                current = transition_incident(current, IncidentStatus.LEARNED)
            state["incidents"][current.incident_id] = current.model_dump(mode="json")
            return current.model_dump(mode="json")

        incident = self.store.transaction(update)
        self.tools.write_operational_memory(
            principal="supervisor-agent",
            incident_id="INC-1042",
            machine_id="MC-04",
            content="MC-04 AXIS_SERVO_OVERLOAD_X with rising X-axis load and normal spindle load was resolved after chip accumulation was cleared near the X-axis cover area.",
            trace_id=HERO_CORRELATION_ID,
        )
        if self._scenario_status() == ScenarioStatus.MONITORING:
            self._transition_scenario_status(ScenarioStatus.RESOLVED)
            self._transition_scenario_status(ScenarioStatus.LEARNED)
        return {"status": "resolved", "incident": incident}

    def _scenario_status(self) -> ScenarioStatus:
        scenario = self.store.get("scenario_state", "default") or {}
        return ScenarioStatus(scenario.get("status", ScenarioStatus.READY.value))

    def _transition_scenario_status(self, target: ScenarioStatus) -> None:
        def update(state: dict[str, Any]) -> None:
            scenario = state["scenario_state"]["default"]
            scenario["status"] = transition_scenario(scenario["status"], target).value
            scenario["updated_at"] = utc_now_iso()

        self.store.transaction(update)

    def _reject_if_active_incident(self) -> None:
        active = [
            incident
            for incident in self.store.list("incidents")
            if incident.get("status") not in {"LEARNED", "FAILED", "ESCALATED", "CANCELLED"}
        ]
        if active:
            raise ValueError("Reset the demo before starting another hero scenario")

    def _require_demo_enabled(self) -> None:
        scenario = self.store.get("scenario_state", "default") or {}
        if not scenario.get("demo_data_enabled", False):
            raise DemoDataDisabled("Synthetic demo seed data is disabled. Import or enable demo data first.")
