from __future__ import annotations

from collections.abc import Callable
from typing import Any

from forge.domain.models import (
    ActionStatus,
    Approval,
    Incident,
    IncidentStatus,
    Machine,
    MachineState,
    MaintenanceTicket,
    Notification,
    OperationalMemory,
    ScheduleProposal,
    SecurityEvent,
    Severity,
    WorkOrder,
    new_id,
    utc_now_iso,
)
from forge.domain.state_machine import transition_incident
from forge.policies.permissions import PolicyService
from forge.repositories.local_store import LocalStore


class ToolValidationError(ValueError):
    pass


class ToolExecutor:
    def __init__(self, store: LocalStore, policy: PolicyService):
        self.store = store
        self.policy = policy

    def _idempotent(self, key: str, factory: Callable[[], Any]) -> Any:
        state = self.store.read_state()
        if key in state.get("idempotency", {}):
            return state["idempotency"][key]
        result = factory()

        def write(updated: dict[str, Any]) -> None:
            updated.setdefault("idempotency", {})[key] = result

        self.store.transaction(write)
        return result

    def _record_execution(
        self,
        *,
        action_type: str,
        principal: str,
        status: ActionStatus,
        incident_id: str | None,
        summary: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        execution = {
            "execution_id": new_id("exe"),
            "action_type": action_type,
            "principal": principal,
            "status": status.value,
            "incident_id": incident_id,
            "summary": summary,
            "params": params or {},
            "timestamp": utc_now_iso(),
        }
        self.store.upsert("action_executions", execution["execution_id"], execution)
        return execution

    def create_maintenance_ticket(
        self,
        *,
        principal: str,
        incident_id: str,
        machine_id: str,
        severity: Severity,
        title: str,
        description: str,
        checklist: list[str],
        evidence_event_ids: list[str],
        trace_id: str,
    ) -> MaintenanceTicket:
        decision = self.policy.evaluate(
            principal=principal,
            action="create_maintenance_ticket",
            resource=machine_id,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)

        def create() -> dict[str, Any]:
            if not self.store.get("incidents", incident_id):
                raise ToolValidationError(f"Unknown incident {incident_id}")
            if not self.store.get("machines", machine_id):
                raise ToolValidationError(f"Unknown machine {machine_id}")
            ticket = MaintenanceTicket(
                ticket_id="MT-1042" if incident_id == "INC-1042" else new_id("mt"),
                incident_id=incident_id,
                machine_id=machine_id,
                severity=severity,
                title=title,
                description=description,
                checklist=checklist,
                evidence_event_ids=evidence_event_ids,
            )
            self.store.upsert("maintenance_tasks", ticket.ticket_id, ticket.model_dump(mode="json"))
            self._record_execution(
                action_type="create_maintenance_ticket",
                principal=principal,
                status=ActionStatus.EXECUTED,
                incident_id=incident_id,
                summary=f"Created {ticket.ticket_id}",
                params={"machine_id": machine_id},
            )
            return ticket.model_dump(mode="json")

        return MaintenanceTicket.model_validate(self._idempotent(f"ticket:{incident_id}:{machine_id}", create))

    def set_machine_maintenance(
        self,
        *,
        principal: str,
        incident_id: str,
        machine_id: str,
        trace_id: str,
    ) -> Machine:
        decision = self.policy.evaluate(
            principal=principal,
            action="set_machine_maintenance",
            resource=machine_id,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)

        def update(state: dict[str, Any]) -> dict[str, Any]:
            raw = state["machines"].get(machine_id)
            if not raw:
                raise ToolValidationError(f"Unknown machine {machine_id}")
            machine = Machine.model_validate(raw)
            machine.state = MachineState.MAINTENANCE
            machine.active_alarm_codes = sorted(set(machine.active_alarm_codes + ["AXIS_SERVO_OVERLOAD_X"]))
            machine.at_risk = True
            state["machines"][machine_id] = machine.model_dump(mode="json")
            return machine.model_dump(mode="json")

        machine = Machine.model_validate(self.store.transaction(update))
        self._record_execution(
            action_type="set_machine_maintenance",
            principal=principal,
            status=ActionStatus.EXECUTED,
            incident_id=incident_id,
            summary=f"{machine_id} set to MAINTENANCE",
            params={"machine_id": machine_id},
        )
        return machine

    def create_notification(
        self,
        *,
        principal: str,
        severity: Severity,
        title: str,
        message: str,
        incident_id: str | None,
        machine_id: str | None,
        trace_id: str,
    ) -> Notification:
        decision = self.policy.evaluate(
            principal=principal,
            action="create_notification",
            resource=machine_id,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)
        notification = Notification(
            notification_id=new_id("ntf"),
            severity=severity,
            title=title,
            message=message,
            incident_id=incident_id,
            machine_id=machine_id,
        )
        self.store.upsert("notifications", notification.notification_id, notification.model_dump(mode="json"))
        self._record_execution(
            action_type="create_notification",
            principal=principal,
            status=ActionStatus.EXECUTED,
            incident_id=incident_id,
            summary=title,
            params={"machine_id": machine_id},
        )
        return notification

    def create_schedule_proposal(
        self,
        *,
        principal: str,
        incident_id: str,
        work_order_id: str,
        from_machine_id: str,
        to_machine_id: str,
        quantity: int,
        estimated_minutes_saved: int,
        risk: str,
        trace_id: str,
    ) -> ScheduleProposal:
        decision = self.policy.evaluate(
            principal=principal,
            action="create_schedule_proposal",
            resource=work_order_id,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)
        if not self.store.get("work_orders", work_order_id):
            raise ToolValidationError(f"Unknown work order {work_order_id}")
        if not self.store.get("machines", to_machine_id):
            raise ToolValidationError(f"Unknown target machine {to_machine_id}")
        proposal = ScheduleProposal(
            proposal_id="SCH-1042" if incident_id == "INC-1042" else new_id("sch"),
            incident_id=incident_id,
            work_order_id=work_order_id,
            from_machine_id=from_machine_id,
            to_machine_id=to_machine_id,
            quantity=quantity,
            estimated_minutes_saved=estimated_minutes_saved,
            risk=risk,
        )
        self.store.upsert("schedule_proposals", proposal.proposal_id, proposal.model_dump(mode="json"))
        approval = Approval(
            approval_id="APV-1042" if incident_id == "INC-1042" else new_id("apv"),
            incident_id=incident_id,
            proposal_id=proposal.proposal_id,
            action_type="apply_schedule_change",
        )
        self.store.upsert("approvals", approval.approval_id, approval.model_dump(mode="json"))
        self._record_execution(
            action_type="create_schedule_proposal",
            principal=principal,
            status=ActionStatus.PROPOSED,
            incident_id=incident_id,
            summary=f"Proposed {work_order_id} move to {to_machine_id}",
            params=proposal.model_dump(mode="json"),
        )
        return proposal

    def apply_schedule_change(
        self,
        *,
        principal: str,
        approval_id: str,
        trace_id: str,
        decision_note: str = "Approved by synthetic supervisor",
    ) -> ScheduleProposal:
        approval_raw = self.store.get("approvals", approval_id)
        if not approval_raw:
            raise ToolValidationError(f"Unknown approval {approval_id}")
        approval = Approval.model_validate(approval_raw)
        proposal_raw = self.store.get("schedule_proposals", approval.proposal_id)
        if not proposal_raw:
            raise ToolValidationError(f"Unknown schedule proposal {approval.proposal_id}")
        proposal = ScheduleProposal.model_validate(proposal_raw)

        decision = self.policy.evaluate(
            principal=principal,
            action="apply_schedule_change",
            resource=proposal.work_order_id,
            incident_id=proposal.incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)
        if approval.status != ActionStatus.PROPOSED:
            return proposal

        def update(state: dict[str, Any]) -> dict[str, Any]:
            wo = WorkOrder.model_validate(state["work_orders"][proposal.work_order_id])
            wo.assigned_machine_id = proposal.to_machine_id
            wo.risk = wo.risk if wo.risk.value == "HIGH" else wo.risk
            state["work_orders"][wo.work_order_id] = wo.model_dump(mode="json")
            source = Machine.model_validate(state["machines"][proposal.from_machine_id])
            target = Machine.model_validate(state["machines"][proposal.to_machine_id])
            target.current_work_order_id = wo.work_order_id
            target.current_operation = wo.operation
            target.state = MachineState.SETUP
            target.at_risk = True
            source.at_risk = True
            state["machines"][target.machine_id] = target.model_dump(mode="json")
            state["machines"][source.machine_id] = source.model_dump(mode="json")
            proposal.status = ActionStatus.APPROVED
            proposal.approved_at = utc_now_iso()
            proposal.approved_by = principal
            state["schedule_proposals"][proposal.proposal_id] = proposal.model_dump(mode="json")
            approval.status = ActionStatus.APPROVED
            approval.decided_at = proposal.approved_at
            approval.decided_by = principal
            approval.decision_note = decision_note
            state["approvals"][approval.approval_id] = approval.model_dump(mode="json")
            incident = Incident.model_validate(state["incidents"][proposal.incident_id])
            if incident.status == IncidentStatus.AWAITING_APPROVAL:
                incident = transition_incident(incident, IncidentStatus.ACTIONING)
                incident = transition_incident(incident, IncidentStatus.MONITORING)
            state["incidents"][incident.incident_id] = incident.model_dump(mode="json")
            return proposal.model_dump(mode="json")

        applied = ScheduleProposal.model_validate(self.store.transaction(update))
        self._record_execution(
            action_type="apply_schedule_change",
            principal=principal,
            status=ActionStatus.EXECUTED,
            incident_id=proposal.incident_id,
            summary=f"Applied schedule change {proposal.proposal_id}",
            params=applied.model_dump(mode="json"),
        )
        self.create_notification(
            principal=principal,
            severity=Severity.HIGH,
            title="Schedule change approved",
            message=f"{proposal.work_order_id} remaining quantity moved to {proposal.to_machine_id}.",
            incident_id=proposal.incident_id,
            machine_id=proposal.to_machine_id,
            trace_id=trace_id,
        )
        return applied

    def reject_schedule_change(
        self,
        *,
        principal: str,
        approval_id: str,
        trace_id: str,
        decision_note: str,
    ) -> Approval:
        approval_raw = self.store.get("approvals", approval_id)
        if not approval_raw:
            raise ToolValidationError(f"Unknown approval {approval_id}")
        approval = Approval.model_validate(approval_raw)
        proposal = ScheduleProposal.model_validate(self.store.get("schedule_proposals", approval.proposal_id))

        def update(state: dict[str, Any]) -> dict[str, Any]:
            approval.status = ActionStatus.REJECTED
            approval.decided_at = utc_now_iso()
            approval.decided_by = principal
            approval.decision_note = decision_note
            state["approvals"][approval.approval_id] = approval.model_dump(mode="json")
            proposal.status = ActionStatus.REJECTED
            state["schedule_proposals"][proposal.proposal_id] = proposal.model_dump(mode="json")
            incident = Incident.model_validate(state["incidents"][proposal.incident_id])
            if incident.status == IncidentStatus.AWAITING_APPROVAL:
                incident = transition_incident(incident, IncidentStatus.ESCALATED)
            state["incidents"][incident.incident_id] = incident.model_dump(mode="json")
            return approval.model_dump(mode="json")

        self.policy.evaluate(
            principal=principal,
            action="apply_schedule_change",
            resource=proposal.work_order_id,
            incident_id=proposal.incident_id,
            trace_id=trace_id,
        )
        return Approval.model_validate(self.store.transaction(update))

    def write_operational_memory(
        self,
        *,
        principal: str,
        incident_id: str,
        machine_id: str,
        content: str,
        trace_id: str,
    ) -> OperationalMemory:
        decision = self.policy.evaluate(
            principal=principal,
            action="write_operational_memory",
            resource=incident_id,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        if decision.effect.value == "DENY":
            raise PermissionError(decision.reason)
        memory = OperationalMemory(
            incident_id=incident_id,
            machine_id=machine_id,
            memory_type="historical_outcome",
            content=content,
            confidence=0.91,
            source="EPYK Forge supervisor-agent",
        )
        self.store.upsert("memories", memory.memory_id, memory.model_dump(mode="json"))
        self._record_execution(
            action_type="write_operational_memory",
            principal=principal,
            status=ActionStatus.EXECUTED,
            incident_id=incident_id,
            summary="Operational memory recorded",
            params={"memory_id": memory.memory_id},
        )
        return memory

    def record_security_event(
        self,
        *,
        principal: str,
        incident_id: str | None,
        title: str,
        description: str,
        denied_tool: str | None,
        trace_id: str,
    ) -> SecurityEvent:
        event = SecurityEvent(
            severity=Severity.HIGH,
            category="prompt_injection" if denied_tool else "policy",
            title=title,
            description=description,
            principal=principal,
            denied_tool=denied_tool,
            trace_id=trace_id,
            incident_id=incident_id,
        )
        self.store.upsert("security_events", event.security_event_id, event.model_dump(mode="json"))
        return event

    def deny_external_http_request(
        self,
        *,
        principal: str,
        incident_id: str,
        target: str,
        trace_id: str,
    ) -> None:
        decision = self.policy.evaluate(
            principal=principal,
            action="external_http_request",
            resource=target,
            incident_id=incident_id,
            trace_id=trace_id,
        )
        self.record_security_event(
            principal=principal,
            incident_id=incident_id,
            title="Untrusted retrieval attempted to request external exfiltration",
            description=f"Policy decision {decision.effect.value}: {decision.reason}. Target: {target}",
            denied_tool="external_http_request",
            trace_id=trace_id,
        )
