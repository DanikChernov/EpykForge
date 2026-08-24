from __future__ import annotations

from typing import Any

from forge.agents.fleet import AgentFleet
from forge.domain.models import (
    EventType,
    Machine,
    MachineEvent,
    MachineState,
    TelemetrySample,
    WorkOrder,
)
from forge.repositories.local_store import LocalStore
from forge.telemetry.tracing import TraceRecorder


class EventIngestionService:
    def __init__(self, *, store: LocalStore, fleet: AgentFleet, traces: TraceRecorder):
        self.store = store
        self.fleet = fleet
        self.traces = traces

    def ingest(self, event: MachineEvent) -> dict[str, Any]:
        existing = self.store.get("events", event.event_id)
        if existing:
            return {"status": "duplicate", "event_id": event.event_id}

        with self.traces.span(
            trace_id=event.trace_id or event.correlation_id,
            correlation_id=event.correlation_id,
            name="event.ingest",
            attributes={"event_type": event.event_type.value, "machine_id": event.machine_id},
        ):
            self.store.append("events", event.model_dump(mode="json"))
            self._apply_event_to_machine(event)
            incident_id: str | None = None
            if event.event_type == EventType.ALARM:
                finding = self.fleet.observe_event(event)
                incident = self.fleet.create_incident_from_finding(event, finding)
                if incident:
                    incident_id = incident.incident_id
                    self.fleet.run_incident_pipeline(incident.incident_id)
            return {"status": "accepted", "event_id": event.event_id, "incident_id": incident_id}

    def _apply_event_to_machine(self, event: MachineEvent) -> None:
        if not event.machine_id:
            return

        def update(state: dict[str, Any]) -> None:
            raw = state["machines"].get(event.machine_id)
            if not raw:
                return
            machine = Machine.model_validate(raw)
            if event.event_type == EventType.TELEMETRY:
                telemetry = TelemetrySample.model_validate(event.payload)
                machine.telemetry = telemetry
                machine.telemetry_history.append(telemetry)
                machine.telemetry_history = machine.telemetry_history[-40:]
                if machine.current_work_order_id and machine.current_work_order_id in state["work_orders"]:
                    wo = WorkOrder.model_validate(state["work_orders"][machine.current_work_order_id])
                    wo.observed_cycle_time_sec = telemetry.observed_cycle_time_sec or wo.observed_cycle_time_sec
                    state["work_orders"][wo.work_order_id] = wo.model_dump(mode="json")
            elif event.event_type == EventType.FEED_HOLD:
                machine.state = MachineState.FEED_HOLD
            elif event.event_type == EventType.RUNNING:
                machine.state = MachineState.RUNNING
            elif event.event_type == EventType.ALARM:
                machine.state = MachineState.ALARM
                code = event.payload.get("code")
                if code:
                    machine.active_alarm_codes = sorted(set(machine.active_alarm_codes + [str(code)]))
                machine.at_risk = True
                machine.health_score = 27
            elif event.event_type == EventType.MAINTENANCE:
                machine.state = MachineState.MAINTENANCE
            elif event.event_type == EventType.RECOVERY:
                machine.state = MachineState.RECOVERY
            state["machines"][machine.machine_id] = machine.model_dump(mode="json")

        self.store.transaction(update)
