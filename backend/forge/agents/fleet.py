from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from forge.agents.adk_runtime import build_adk_agents
from forge.agents.model_service import BaseModelService
from forge.config.settings import Settings
from forge.domain.models import (
    WORKFLOW_STAGE_DEFINITIONS,
    ActionProposal,
    AgentRun,
    AgentRunStatus,
    Diagnosis,
    Incident,
    IncidentEvidence,
    IncidentStatus,
    KnowledgeReference,
    KnowledgeResult,
    Machine,
    MachineEvent,
    ObserverFinding,
    PolicyEffect,
    ProbableCause,
    RecoveryPlan,
    Severity,
    SupervisorDecision,
    WorkflowStage,
    WorkOrder,
    utc_now_iso,
)
from forge.domain.state_machine import transition_incident
from forge.policies.permissions import PolicyService
from forge.repositories.local_store import LocalStore
from forge.telemetry.tracing import TraceRecorder
from forge.tools.actions import ToolExecutor
from forge.tools.scheduling import calculate_production_impact

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompts() -> dict[str, str]:
    return {
        "observer-agent": (PROMPT_DIR / "observer.md").read_text(encoding="utf-8"),
        "diagnostic-agent": (PROMPT_DIR / "diagnostic.md").read_text(encoding="utf-8"),
        "knowledge-agent": (PROMPT_DIR / "knowledge.md").read_text(encoding="utf-8"),
        "production-agent": (PROMPT_DIR / "production.md").read_text(encoding="utf-8"),
        "recovery-agent": (PROMPT_DIR / "recovery.md").read_text(encoding="utf-8"),
        "supervisor-agent": (PROMPT_DIR / "supervisor.md").read_text(encoding="utf-8"),
    }


class AgentFleet:
    def __init__(
        self,
        *,
        settings: Settings,
        store: LocalStore,
        model_service: BaseModelService,
        policy: PolicyService,
        tools: ToolExecutor,
        traces: TraceRecorder,
    ):
        self.settings = settings
        self.store = store
        self.model_service = model_service
        self.policy = policy
        self.tools = tools
        self.traces = traces
        self.prompts = load_prompts()
        self.adk_status, self.adk_agents = build_adk_agents(settings.gemini_model, self.prompts)

    def _structured_from_draft(
        self,
        *,
        agent_id: str,
        output_model: type,
        draft: Any,
        context: dict[str, Any],
    ) -> Any:
        payload = {
            "context": context,
            "draft": draft.model_dump(mode="json") if hasattr(draft, "model_dump") else draft,
            "instruction": "Validate and improve wording without changing verified facts, policy effects, or numeric calculations.",
        }
        return self.model_service.generate_structured(
            agent_id=agent_id,
            system_prompt=self.prompts[agent_id],
            input_payload=payload,
            output_model=output_model,
        )

    @staticmethod
    def _candidate_incident_id(event: MachineEvent) -> str | None:
        if not event.machine_id:
            return None
        return "INC-1042" if event.machine_id == "MC-04" else f"INC-{event.event_id[-4:].upper()}"

    @staticmethod
    def _evidence_id(
        *,
        incident_id: str,
        source_agent: str,
        evidence_type: str,
        source_id: str,
    ) -> str:
        return f"{incident_id}:{source_agent}:{evidence_type}:{source_id}"

    @staticmethod
    def _merge_evidence(existing: list[IncidentEvidence], additions: list[IncidentEvidence]) -> list[IncidentEvidence]:
        by_id = {item.evidence_id: item for item in existing}
        for item in additions:
            by_id.setdefault(item.evidence_id, item)
        return sorted(by_id.values(), key=lambda item: (item.order, item.created_at, item.evidence_id))

    def _workflow_from_runs(self, incident: Incident) -> list[WorkflowStage]:
        stages = {
            definition["stage_id"]: WorkflowStage(**definition)
            for definition in WORKFLOW_STAGE_DEFINITIONS
        }
        for existing in incident.workflow:
            if existing.stage_id in stages:
                stages[existing.stage_id] = existing

        runs = [
            AgentRun.model_validate(raw)
            for raw in self.store.list("agent_runs")
            if raw.get("incident_id") == incident.incident_id
        ]
        runs.sort(key=lambda item: (item.started_at, item.completed_at or "", item.run_id))
        for stage in stages.values():
            matching = [run for run in runs if run.agent_id == stage.agent_id]
            if not matching:
                continue
            latest = matching[-1]
            failed = [run for run in matching if run.status == AgentRunStatus.FAILED]
            stage.status = latest.status
            stage.run_id = latest.run_id
            stage.started_at = latest.started_at
            stage.completed_at = latest.completed_at
            stage.duration_ms = latest.duration_ms
            stage.retry_count = max(latest.retry_count, len(failed))
            stage.action_summary = latest.output_summary or stage.action_summary
            stage.error = latest.error
            if latest.status == AgentRunStatus.RECOVERED and failed:
                stage.error = f"Recovered after: {failed[-1].error}"

        completed = {AgentRunStatus.SUCCEEDED, AgentRunStatus.RECOVERED}
        for stage in sorted(stages.values(), key=lambda item: item.order):
            if stage.status not in completed:
                continue
            for dependency in stage.dependencies:
                upstream = stages[dependency]
                if upstream.status == AgentRunStatus.PENDING:
                    upstream.status = AgentRunStatus.SUCCEEDED
                    upstream.action_summary = upstream.action_summary or "Dependency satisfied before downstream execution"

        return sorted(stages.values(), key=lambda item: item.order)

    def _sync_workflow_from_runs(self, incident_id: str) -> None:
        if not self.store.get("incidents", incident_id):
            return

        def update(state: dict[str, Any]) -> None:
            current = Incident.model_validate(state["incidents"][incident_id])
            current.workflow = self._workflow_from_runs(current)
            current.updated_at = utc_now_iso()
            state["incidents"][incident_id] = current.model_dump(mode="json")

        self.store.transaction(update)

    def _mark_workflow_stage(self, incident_id: str | None, agent_id: str, run: AgentRun) -> None:
        if not incident_id or not self.store.get("incidents", incident_id):
            return

        def update(state: dict[str, Any]) -> None:
            current = Incident.model_validate(state["incidents"][incident_id])
            stages = self._workflow_from_runs(current)
            for stage in stages:
                if stage.agent_id != agent_id:
                    continue
                stage.status = run.status
                stage.run_id = run.run_id
                stage.started_at = run.started_at
                stage.completed_at = run.completed_at
                stage.duration_ms = run.duration_ms
                stage.retry_count = run.retry_count
                stage.action_summary = run.output_summary or stage.action_summary
                stage.error = run.error
            current.workflow = stages
            current.updated_at = utc_now_iso()
            state["incidents"][incident_id] = current.model_dump(mode="json")

        self.store.transaction(update)

    def _stage_complete(self, incident_id: str, agent_id: str) -> bool:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        workflow = self._workflow_from_runs(incident)
        return any(
            stage.agent_id == agent_id
            and stage.status in {AgentRunStatus.SUCCEEDED, AgentRunStatus.RECOVERED}
            for stage in workflow
        )

    def _build_initial_evidence(
        self,
        *,
        incident_id: str,
        event: MachineEvent,
        finding: ObserverFinding,
    ) -> list[IncidentEvidence]:
        event_rows = [
            self.store.get("events", event_id)
            for event_id in finding.evidence_event_ids
            if self.store.get("events", event_id)
        ]
        telemetry = [row for row in event_rows if row and row.get("event_type") == "telemetry"]
        feed_holds = [row for row in event_rows if row and row.get("event_type") == "feed_hold"]
        alarm_code = str(event.payload.get("code", "AXIS_SERVO_OVERLOAD_X"))
        evidence = [
            IncidentEvidence(
                evidence_id=self._evidence_id(
                    incident_id=incident_id,
                    source_agent="observer-agent",
                    evidence_type="trigger",
                    source_id=event.event_id,
                ),
                event_id=event.event_id,
                source_event_id=event.event_id,
                source_event_ids=[event.event_id],
                title="Critical alarm",
                summary=f"{alarm_code} on {event.machine_id}",
                kind="event",
                evidence_type="trigger",
                source_agent="observer-agent",
                confidence=finding.confidence,
                order=10,
                metadata={"alarm_code": alarm_code, "machine_id": event.machine_id},
            )
        ]
        if telemetry:
            x_load = [round(float(row.get("payload", {}).get("x_axis_load_pct", 0))) for row in telemetry]
            cycle = [
                round(float(row.get("payload", {}).get("observed_cycle_time_sec", 0)))
                for row in telemetry
            ]
            telemetry_ids = [str(row["event_id"]) for row in telemetry if row]
            evidence.append(
                IncidentEvidence(
                    evidence_id=self._evidence_id(
                        incident_id=incident_id,
                        source_agent="observer-agent",
                        evidence_type="precursor_telemetry",
                        source_id="-".join(telemetry_ids),
                    ),
                    event_id=telemetry_ids[-1],
                    source_event_id=telemetry_ids[-1],
                    source_event_ids=telemetry_ids,
                    title="Precursor telemetry",
                    summary=(
                        f"X-axis load {' -> '.join(f'{value}%' for value in x_load)}; "
                        f"cycle time {' -> '.join(f'{value}s' for value in cycle)}"
                    ),
                    kind="telemetry",
                    evidence_type="precursor_telemetry",
                    source_agent="observer-agent",
                    confidence=0.91,
                    order=20,
                    metadata={"x_axis_load_pct": x_load, "cycle_time_sec": cycle},
                )
            )
            spindle = [
                round(float(row.get("payload", {}).get("spindle_load_pct", 0)))
                for row in telemetry
            ]
            tool_life = round(float(telemetry[-1].get("payload", {}).get("tool_life_remaining_pct", 0)))
            evidence.append(
                IncidentEvidence(
                    evidence_id=self._evidence_id(
                        incident_id=incident_id,
                        source_agent="observer-agent",
                        evidence_type="contradictory_evidence",
                        source_id=telemetry_ids[-1],
                    ),
                    event_id=telemetry_ids[-1],
                    source_event_id=telemetry_ids[-1],
                    source_event_ids=telemetry_ids,
                    title="Contradictory evidence",
                    summary=(
                        f"Spindle load stayed nominal at {' -> '.join(f'{value}%' for value in spindle)}; "
                        f"tool life remained acceptable at {tool_life}%"
                    ),
                    kind="telemetry",
                    evidence_type="contradictory_evidence",
                    source_agent="observer-agent",
                    confidence=0.84,
                    order=50,
                    metadata={"spindle_load_pct": spindle, "tool_life_remaining_pct": tool_life},
                )
            )
        if feed_holds:
            feed_hold_ids = [str(row["event_id"]) for row in feed_holds if row]
            evidence.append(
                IncidentEvidence(
                    evidence_id=self._evidence_id(
                        incident_id=incident_id,
                        source_agent="observer-agent",
                        evidence_type="feed_hold_precursor",
                        source_id="-".join(feed_hold_ids),
                    ),
                    event_id=feed_hold_ids[-1],
                    source_event_id=feed_hold_ids[-1],
                    source_event_ids=feed_hold_ids,
                    title="Feed-hold precursor",
                    summary=f"{len(feed_hold_ids)} feed holds occurred in the preceding simulated window",
                    kind="event",
                    evidence_type="precursor_telemetry",
                    source_agent="observer-agent",
                    confidence=0.82,
                    order=30,
                    metadata={"feed_hold_count": len(feed_hold_ids)},
                )
            )
        return evidence

    def _run_agent(
        self,
        *,
        agent_id: str,
        incident_id: str | None,
        trace_id: str,
        correlation_id: str,
        input_refs: list[str],
        fn: Callable[[], str],
        tool_calls: list[str] | None = None,
    ) -> AgentRun:
        scenario = self.store.get("scenario_state", "default") or {}
        forced = scenario.get("force_next_agent_failure")
        seen = set(scenario.get("forced_failures_seen", []))
        should_fail_once = forced == agent_id and agent_id not in seen

        start = perf_counter()
        run = AgentRun(
            agent_id=agent_id,
            incident_id=incident_id,
            status=AgentRunStatus.RUNNING,
            input_refs=input_refs,
            tool_calls=tool_calls or [],
            model=self.settings.gemini_model,
            model_provider=self.model_service.provider_name,
            trace_id=trace_id,
        )
        self.store.upsert("agent_runs", run.run_id, run.model_dump(mode="json"))
        self._mark_workflow_stage(incident_id, agent_id, run)

        try:
            with self.traces.span(
                trace_id=trace_id,
                correlation_id=correlation_id,
                name=f"{agent_id}.execute",
                agent_id=agent_id,
                attributes={
                    "incident_id": incident_id,
                    "model_provider": self.model_service.provider_name,
                    "tool_calls": tool_calls or [],
                },
            ):
                if should_fail_once:
                    def mark_failed(state: dict[str, Any]) -> None:
                        scenario_state = state["scenario_state"]["default"]
                        scenario_state["forced_failures_seen"] = sorted(seen | {agent_id})
                        scenario_state["force_next_agent_failure"] = None
                        scenario_state["updated_at"] = utc_now_iso()

                    self.store.transaction(mark_failed)
                    raise TimeoutError("Synthetic Gemini request timeout")
                run.output_summary = fn()
                run.status = AgentRunStatus.SUCCEEDED
        except Exception as exc:
            run.status = AgentRunStatus.FAILED
            run.error = str(exc)
            run.retry_count += 1
            run.completed_at = utc_now_iso()
            run.duration_ms = int((perf_counter() - start) * 1000)
            self.store.upsert("agent_runs", run.run_id, run.model_dump(mode="json"))
            self._mark_workflow_stage(incident_id, agent_id, run)
            if should_fail_once:
                recovered = self._run_agent(
                    agent_id=agent_id,
                    incident_id=incident_id,
                    trace_id=trace_id,
                    correlation_id=correlation_id,
                    input_refs=input_refs,
                    fn=fn,
                    tool_calls=tool_calls,
                )
                recovered.status = AgentRunStatus.RECOVERED
                recovered.retry_count = 1
                self.store.upsert("agent_runs", recovered.run_id, recovered.model_dump(mode="json"))
                self._mark_workflow_stage(incident_id, agent_id, recovered)
                return recovered
            raise

        run.completed_at = utc_now_iso()
        run.duration_ms = int((perf_counter() - start) * 1000)
        self.store.upsert("agent_runs", run.run_id, run.model_dump(mode="json"))
        self._mark_workflow_stage(incident_id, agent_id, run)
        return run

    def observe_event(self, event: MachineEvent) -> ObserverFinding:
        incident_id = self._candidate_incident_id(event)
        finding_ref: dict[str, ObserverFinding] = {}

        def observe() -> str:
            recent_events = self.store.list("events")[-12:]
            evidence_ids = [
                evt["event_id"] for evt in recent_events if evt.get("machine_id") == event.machine_id
            ][-7:]
            if event.event_id not in evidence_ids:
                evidence_ids.append(event.event_id)
            finding = self.model_service.generate_structured(
                agent_id="observer-agent",
                system_prompt=self.prompts["observer-agent"],
                input_payload={
                    "event": event.model_dump(mode="json"),
                    "recent_events": recent_events,
                    "evidence_event_ids": evidence_ids,
                },
                output_model=ObserverFinding,
            )
            finding_ref["value"] = finding
            return finding.reason

        self._run_agent(
            agent_id="observer-agent",
            incident_id=incident_id,
            trace_id=event.trace_id or event.correlation_id,
            correlation_id=event.correlation_id,
            input_refs=[event.event_id],
            fn=observe,
            tool_calls=["factory.events.read", "telemetry.read", "incidents.create"],
        )
        return finding_ref["value"]

    def create_incident_from_finding(self, event: MachineEvent, finding: ObserverFinding) -> Incident | None:
        if not finding.incident_required or not event.machine_id:
            return None
        incident_id = self._candidate_incident_id(event)
        if not incident_id:
            return None
        active = [
            Incident.model_validate(raw)
            for raw in self.store.list("incidents")
            if raw["machine_id"] == event.machine_id
            and raw["status"] not in {"LEARNED", "FAILED", "ESCALATED", "CANCELLED"}
        ]
        if active:
            return active[0]
        machine = Machine.model_validate(self.store.get("machines", event.machine_id))
        incident = Incident(
            incident_id=incident_id,
            title="Unexpected X-Axis Servo Overload",
            severity=finding.severity,
            status=IncidentStatus.DETECTED,
            machine_id=event.machine_id,
            work_order_id=event.work_order_id or machine.current_work_order_id,
            correlation_id=event.correlation_id,
            evidence=self._build_initial_evidence(
                incident_id=incident_id,
                event=event,
                finding=finding,
            ),
        )
        incident = transition_incident(incident, IncidentStatus.TRIAGED)
        incident.workflow = self._workflow_from_runs(incident)
        self.store.upsert("incidents", incident.incident_id, incident.model_dump(mode="json"))
        self.policy.evaluate(
            principal="observer-agent",
            action="create_incident",
            resource=incident.machine_id,
            incident_id=incident.incident_id,
            trace_id=event.trace_id or event.correlation_id,
        )
        self.tools.record_workflow_event(
            action_type="incident.created",
            principal="observer-agent",
            incident_id=incident.incident_id,
            summary=f"Observer opened {incident.incident_id}",
            params={"machine_id": incident.machine_id, "alarm_event_id": event.event_id},
        )
        return incident

    def run_incident_pipeline(self, incident_id: str) -> Incident:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        trace_id = incident.correlation_id
        correlation_id = incident.correlation_id
        self._sync_workflow_from_runs(incident_id)

        def update_incident(mutator: Callable[[Incident], Incident]) -> Incident:
            def write(state: dict[str, Any]) -> dict[str, Any]:
                current = Incident.model_validate(state["incidents"][incident_id])
                current = mutator(current)
                current.updated_at = utc_now_iso()
                state["incidents"][incident_id] = current.model_dump(mode="json")
                return current.model_dump(mode="json")

            return Incident.model_validate(self.store.transaction(write))

        if incident.status == IncidentStatus.TRIAGED:
            incident = update_incident(lambda item: transition_incident(item, IncidentStatus.INVESTIGATING))

        def diagnostic() -> str:
            diagnosis = self._diagnose(incident_id)
            update_incident(lambda item: self._attach_diagnosis(item, diagnosis))
            self.tools.record_workflow_event(
                action_type="diagnosis.ready",
                principal="diagnostic-agent",
                incident_id=incident_id,
                summary="Diagnostic ranked mechanical resistance as the leading cause",
                params={"confidence": diagnosis.confidence},
            )
            return diagnosis.summary

        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.diagnosis or not self._stage_complete(incident_id, "diagnostic-agent"):
            self._run_agent(
                agent_id="diagnostic-agent",
                incident_id=incident_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                input_refs=[incident.machine_id, incident.work_order_id or ""],
                fn=diagnostic,
                tool_calls=["telemetry.read", "maintenance.history.read", "model.invoke"],
            )

        def knowledge() -> str:
            result = self._retrieve_knowledge(incident_id)
            update_incident(lambda item: self._attach_knowledge(item, result))
            self.tools.record_workflow_event(
                action_type="knowledge.retrieved",
                principal="knowledge-agent",
                incident_id=incident_id,
                summary=f"Knowledge retrieved {len(result.references)} provenance-linked references",
                params={"references": [ref.document_id for ref in result.references]},
            )
            return f"{len(result.references)} knowledge references retrieved"

        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.knowledge_result or not self._stage_complete(incident_id, "knowledge-agent"):
            self._run_agent(
                agent_id="knowledge-agent",
                incident_id=incident_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                input_refs=[incident.machine_id],
                fn=knowledge,
                tool_calls=["knowledge.search", "incidents.evidence.add", "security.events.create"],
            )

        def production() -> str:
            impact = self._analyze_production(incident_id)
            update_incident(lambda item: self._attach_impact(item, impact))
            self.tools.record_workflow_event(
                action_type="production.impact.ready",
                principal="production-agent",
                incident_id=incident_id,
                summary=f"{impact.remaining_quantity} units at schedule risk; {impact.saved_minutes_if_reassigned} minutes recoverable",
                params=impact.model_dump(mode="json"),
            )
            return impact.recommendation

        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.production_impact or not self._stage_complete(incident_id, "production-agent"):
            self._run_agent(
                agent_id="production-agent",
                incident_id=incident_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                input_refs=[incident.work_order_id or ""],
                fn=production,
                tool_calls=["work_orders.read", "machines.read", "production.schedule.propose"],
            )

        def recovery() -> str:
            plan = self._build_recovery_plan(incident_id)
            update_incident(lambda item: self._attach_plan(item, plan))
            self.tools.record_workflow_event(
                action_type="recovery.plan.ready",
                principal="recovery-agent",
                incident_id=incident_id,
                summary="Recovery workflow generated with approval-gated schedule transfer",
                params={"steps": plan.steps},
            )
            return plan.summary

        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.recovery_plan or not self._stage_complete(incident_id, "recovery-agent"):
            self._run_agent(
                agent_id="recovery-agent",
                incident_id=incident_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                input_refs=[incident_id],
                fn=recovery,
                tool_calls=[
                    "maintenance.ticket.create",
                    "machine.state.set_maintenance",
                    "notifications.create",
                    "production.schedule.propose",
                ],
            )

        def supervisor() -> str:
            decision = self._supervise_and_execute(incident_id)
            update_incident(lambda item: self._attach_supervisor_decision(item, decision))
            self.tools.record_workflow_event(
                action_type="supervisor.decision.ready",
                principal="supervisor-agent",
                incident_id=incident_id,
                summary="Digital actions approved; schedule transfer gated for human approval",
                params=decision.model_dump(mode="json"),
            )
            return decision.rationale

        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.supervisor_decision or not self._stage_complete(incident_id, "supervisor-agent"):
            self._run_agent(
                agent_id="supervisor-agent",
                incident_id=incident_id,
                trace_id=trace_id,
                correlation_id=correlation_id,
                input_refs=[incident_id],
                fn=supervisor,
                tool_calls=["policy.evaluate", "approvals.request"],
            )

        self._sync_workflow_from_runs(incident_id)
        return Incident.model_validate(self.store.get("incidents", incident_id))

    def _diagnose(self, incident_id: str) -> Diagnosis:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        machine = Machine.model_validate(self.store.get("machines", incident.machine_id))
        recent = [evt for evt in self.store.list("events") if evt.get("machine_id") == incident.machine_id][-10:]
        evidence = [evt["event_id"] for evt in recent]
        diagnosis = Diagnosis(
            incident_id=incident_id,
            probable_causes=[
                ProbableCause(
                    cause="X-axis mechanical resistance, chip accumulation, or way-cover obstruction",
                    confidence=0.77,
                    evidence=evidence,
                    contradictions=["Tool life is still acceptable", "Spindle load is normal"],
                ),
                ProbableCause(
                    cause="Servo drive fault",
                    confidence=0.18,
                    evidence=[evt["event_id"] for evt in recent if evt.get("event_type") == "alarm"],
                    contradictions=["Preceding gradual axis-load rise favors mechanical resistance"],
                ),
                ProbableCause(
                    cause="Programmed aggressive feed condition",
                    confidence=0.05,
                    evidence=[],
                    contradictions=["No tool break or program-change event in the preceding ledger"],
                ),
            ],
            recommended_checks=[
                "Place MC-04 in maintenance state before physical inspection",
                "Inspect X-axis way-cover and chip accumulation areas",
                "Verify lubrication status through approved maintenance procedure",
                "Run OEM-prescribed diagnostics after maintenance handoff",
            ],
            unsafe_to_auto_execute=[
                "axis_jog",
                "servo_reset",
                "spindle_start",
                "cycle_start",
                "PLC write",
            ],
            confidence=0.81,
            summary=(
                f"{machine.machine_id} alarm pattern indicates probable X-axis mechanical resistance; "
                "evidence remains bounded to telemetry trend and active alarm."
            ),
        )
        return self._structured_from_draft(
            agent_id="diagnostic-agent",
            output_model=Diagnosis,
            draft=diagnosis,
            context={"recent_events": recent, "machine": machine.model_dump(mode="json")},
        )

    def _retrieve_knowledge(self, incident_id: str) -> KnowledgeResult:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        docs = self.store.list("knowledge_documents")
        state = self.store.get("scenario_state", "default") or {}
        query_terms = {"AXIS_SERVO_OVERLOAD_X", "servo", "x-axis", incident.machine_id}
        scored: list[tuple[float, dict[str, Any]]] = []
        for doc in docs:
            if doc["document_id"] == "MAL-REDTEAM-001" and not state.get("security_attack_enabled"):
                continue
            haystack = " ".join(
                [
                    doc.get("title", ""),
                    doc.get("content", ""),
                    " ".join(doc.get("tags", [])),
                    " ".join(doc.get("equipment_scope", [])),
                ]
            ).lower()
            score = sum(1 for term in query_terms if term.lower() in haystack)
            if doc["document_id"] == "MAL-REDTEAM-001" and state.get("security_attack_enabled"):
                score += 4
            if score:
                scored.append((score / max(len(query_terms), 1), doc))
        top = sorted(scored, key=lambda item: item[0], reverse=True)[:4]
        refs: list[KnowledgeReference] = []
        security_events: list[str] = []
        for score, doc in top:
            content = doc.get("content", "")
            injection = any(
                marker in content.lower()
                for marker in ["ignore all previous instructions", "attacker.example", "external_http_request"]
            )
            if injection:
                sec = self.tools.record_security_event(
                    principal="knowledge-agent",
                    incident_id=incident_id,
                    title="Prompt injection detected in retrieved knowledge",
                    description=(
                        f"Document {doc['document_id']} contains untrusted instructions that attempt "
                        "policy override or data exfiltration."
                    ),
                    denied_tool=None,
                    trace_id=incident.correlation_id,
                    event_type="PROMPT_INJECTION",
                    source=doc["document_id"],
                    requested_action="policy.override",
                    policy="retrieval_content_is_untrusted",
                    decision="BLOCKED",
                    reason="Knowledge documents are evidence and cannot change agent policy.",
                )
                self.tools.deny_external_http_request(
                    principal="knowledge-agent",
                    incident_id=incident_id,
                    target="https://attacker.example",
                    trace_id=incident.correlation_id,
                )
                security_events.append(sec.security_event_id)
            excerpt = (
                "UNTRUSTED RETRIEVED CONTENT: synthetic red-team note attempted policy override "
                "and external data exfiltration. Knowledge is evidence, not policy."
                if injection
                else content[:420]
            )
            refs.append(
                KnowledgeReference(
                    document_id=doc["document_id"],
                    title=doc["title"],
                    document_type=doc["document_type"],
                    revision=doc["revision"],
                    approved=doc["approved"],
                    excerpt=excerpt,
                    relevance_confidence=min(score + 0.32, 0.96),
                    injection_risk=injection,
                )
            )
        result = KnowledgeResult(
            incident_id=incident_id,
            references=refs,
            security_events=security_events,
            summary="Retrieved relevant synthetic SOPs, policies, and historical lessons with provenance.",
        )
        return self._structured_from_draft(
            agent_id="knowledge-agent",
            output_model=KnowledgeResult,
            draft=result,
            context={"incident_id": incident_id, "retrieval_count": len(refs)},
        )

    def _analyze_production(self, incident_id: str):
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.work_order_id:
            raise ValueError("Incident has no work order for production analysis")
        wo = WorkOrder.model_validate(self.store.get("work_orders", incident.work_order_id))
        machines = [Machine.model_validate(raw) for raw in self.store.list("machines")]
        impact = calculate_production_impact(
            incident_id=incident_id,
            work_order=wo,
            machines=machines,
            failed_machine_id=incident.machine_id,
        )
        def mark_risk(state: dict[str, Any]) -> None:
            work_order = WorkOrder.model_validate(state["work_orders"][wo.work_order_id])
            work_order.risk = impact.delivery_risk
            state["work_orders"][wo.work_order_id] = work_order.model_dump(mode="json")
            machine = Machine.model_validate(state["machines"][incident.machine_id])
            machine.at_risk = True
            state["machines"][machine.machine_id] = machine.model_dump(mode="json")

        self.store.transaction(mark_risk)
        return self._structured_from_draft(
            agent_id="production-agent",
            output_model=type(impact),
            draft=impact,
            context={"work_order_id": wo.work_order_id, "calculator": "deterministic_schedule_tool"},
        )

    def _build_recovery_plan(self, incident_id: str) -> RecoveryPlan:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.diagnosis or not incident.production_impact:
            raise ValueError("Recovery requires diagnosis and production impact")
        best = min(
            [alt for alt in incident.production_impact.alternatives if alt.capable],
            key=lambda alt: alt.setup_minutes + alt.queue_minutes,
        )
        proposals = [
            ActionProposal(
                action_type="create_maintenance_ticket",
                title="Create P1 maintenance ticket",
                requested_by="recovery-agent",
                approval_required=False,
                risk="Low digital risk; creates internal ticket only.",
                params={
                    "machine_id": incident.machine_id,
                    "severity": incident.severity.value,
                    "title": "P1 X-axis servo overload inspection",
                },
            ),
            ActionProposal(
                action_type="set_machine_maintenance",
                title="Place machine in maintenance state",
                requested_by="recovery-agent",
                approval_required=False,
                risk="Bounded digital state update; no physical machine control.",
                params={"machine_id": incident.machine_id},
            ),
            ActionProposal(
                action_type="create_notification",
                title="Notify supervisor and maintenance",
                requested_by="recovery-agent",
                approval_required=False,
                risk="Synthetic internal notification only.",
                params={"machine_id": incident.machine_id},
            ),
            ActionProposal(
                action_type="create_schedule_proposal",
                title=f"Propose moving remaining quantity to {best.machine_id}",
                requested_by="recovery-agent",
                approval_required=False,
                risk="Proposal only. Application requires supervisor approval.",
                params={
                    "work_order_id": incident.work_order_id,
                    "from_machine_id": incident.machine_id,
                    "to_machine_id": best.machine_id,
                    "quantity": incident.production_impact.remaining_quantity,
                    "estimated_minutes_saved": incident.production_impact.saved_minutes_if_reassigned,
                },
            ),
            ActionProposal(
                action_type="apply_schedule_change",
                title="Apply schedule reassignment after approval",
                requested_by="recovery-agent",
                approval_required=True,
                risk="Meaningful production change; requires fixture verification and supervisor approval.",
                params={
                    "work_order_id": incident.work_order_id,
                    "from_machine_id": incident.machine_id,
                    "to_machine_id": best.machine_id,
                    "quantity": incident.production_impact.remaining_quantity,
                },
            ),
        ]
        plan = RecoveryPlan(
            incident_id=incident_id,
            summary="Build bounded recovery workflow: maintenance handoff, production risk mitigation, and approval-gated schedule change.",
            steps=[
                "Place MC-04 in maintenance state",
                "Create P1 maintenance ticket with telemetry evidence",
                "Technician checks X-axis way-cover and chip accumulation areas",
                f"Reserve {best.machine_id} as fallback capacity",
                "Hold schedule reassignment pending supervisor approval",
                "Verify three dry/test cycles after maintenance handoff",
            ],
            proposals=proposals,
            verification_plan=[
                "Confirm alarm cleared by maintenance technician",
                "Observe X-axis load below 70 percent during verification cycles",
                "Confirm cycle time returns within 5 percent of target",
            ],
            physical_safety_boundary="EPYK Forge never issues CNC motion, servo reset, spindle, PLC, parameter, or interlock commands.",
        )
        return self._structured_from_draft(
            agent_id="recovery-agent",
            output_model=RecoveryPlan,
            draft=plan,
            context={"incident_id": incident_id},
        )

    def _supervise_and_execute(self, incident_id: str) -> SupervisorDecision:
        incident = Incident.model_validate(self.store.get("incidents", incident_id))
        if not incident.recovery_plan:
            raise ValueError("No recovery plan available")
        approved: list[str] = []
        approvals: list[str] = []
        denied: list[str] = []
        trace_id = incident.correlation_id
        for proposal in incident.recovery_plan.proposals:
            decision = self.policy.evaluate(
                principal="supervisor-agent",
                action=proposal.action_type,
                resource=proposal.params.get("machine_id") or proposal.params.get("work_order_id"),
                incident_id=incident_id,
                trace_id=trace_id,
            )
            if decision.effect == PolicyEffect.DENY:
                denied.append(proposal.action_type)
                continue
            if decision.effect == PolicyEffect.APPROVAL_REQUIRED or proposal.approval_required:
                approvals.append(proposal.action_type)
                continue
            self._execute_auto_proposal(incident, proposal)
            approved.append(proposal.action_type)

        def update_status(state: dict[str, Any]) -> None:
            current = Incident.model_validate(state["incidents"][incident_id])
            if current.status == IncidentStatus.PLAN_READY:
                target = IncidentStatus.AWAITING_APPROVAL if approvals else IncidentStatus.ACTIONING
                current = transition_incident(current, target)
                if target == IncidentStatus.ACTIONING:
                    current = transition_incident(current, IncidentStatus.MONITORING)
            state["incidents"][incident_id] = current.model_dump(mode="json")

        self.store.transaction(update_status)
        effect = PolicyEffect.APPROVAL_REQUIRED if approvals else PolicyEffect.ALLOW
        draft = SupervisorDecision(
            incident_id=incident_id,
            effect=effect,
            approved_auto_actions=approved,
            approval_required_actions=approvals,
            denied_actions=denied,
            rationale="Auto actions are bounded digital workflow changes; schedule application remains gated.",
        )
        reviewed = self._structured_from_draft(
            agent_id="supervisor-agent",
            output_model=SupervisorDecision,
            draft=draft,
            context={"policy_authority": "deterministic", "incident_id": incident_id},
        )
        reviewed.effect = draft.effect
        reviewed.approved_auto_actions = draft.approved_auto_actions
        reviewed.approval_required_actions = draft.approval_required_actions
        reviewed.denied_actions = draft.denied_actions
        return reviewed

    def _execute_auto_proposal(self, incident: Incident, proposal: ActionProposal) -> None:
        trace_id = incident.correlation_id
        if proposal.action_type == "create_maintenance_ticket":
            self.tools.create_maintenance_ticket(
                principal="supervisor-agent",
                incident_id=incident.incident_id,
                machine_id=incident.machine_id,
                severity=incident.severity,
                title="P1 X-axis servo overload inspection",
                description="Investigate MC-04 AXIS_SERVO_OVERLOAD_X after rising axis load and feed holds.",
                checklist=[
                    "Confirm machine is in maintenance state",
                    "Inspect X-axis way-cover and chip accumulation areas",
                    "Verify lubrication indicators",
                    "Record findings before any physical reset",
                ],
                evidence_event_ids=[e.event_id for e in incident.evidence if e.event_id],
                trace_id=trace_id,
            )
        elif proposal.action_type == "set_machine_maintenance":
            self.tools.set_machine_maintenance(
                principal="supervisor-agent",
                incident_id=incident.incident_id,
                machine_id=incident.machine_id,
                trace_id=trace_id,
            )
        elif proposal.action_type == "create_notification":
            self.tools.create_notification(
                principal="supervisor-agent",
                severity=Severity.CRITICAL,
                title="P1 maintenance: MC-04 servo overload",
                message="Incident INC-1042 opened automatically. Production impact assessment and recovery plan are ready.",
                incident_id=incident.incident_id,
                machine_id=incident.machine_id,
                trace_id=trace_id,
            )
        elif proposal.action_type == "create_schedule_proposal":
            if not incident.production_impact:
                raise ValueError("Missing production impact")
            self.tools.create_schedule_proposal(
                principal="supervisor-agent",
                incident_id=incident.incident_id,
                work_order_id=str(proposal.params["work_order_id"]),
                from_machine_id=str(proposal.params["from_machine_id"]),
                to_machine_id=str(proposal.params["to_machine_id"]),
                quantity=int(proposal.params["quantity"]),
                estimated_minutes_saved=int(proposal.params["estimated_minutes_saved"]),
                risk="Requires fixture verification before OP30 reassignment",
                trace_id=trace_id,
            )

    @staticmethod
    def _attach_diagnosis(incident: Incident, diagnosis: Diagnosis) -> Incident:
        incident.diagnosis = diagnosis
        if incident.status == IncidentStatus.INVESTIGATING:
            incident = transition_incident(incident, IncidentStatus.DIAGNOSIS_READY)
        return incident

    def _attach_knowledge(self, incident: Incident, result: KnowledgeResult) -> Incident:
        incident.knowledge_result = result
        evidence: list[IncidentEvidence] = []
        for ref in result.references:
            evidence_type = "historical_context" if ref.document_type == "historical_incident" else "knowledge_reference"
            evidence.append(
                IncidentEvidence(
                    evidence_id=self._evidence_id(
                        incident_id=incident.incident_id,
                        source_agent="knowledge-agent",
                        evidence_type=evidence_type,
                        source_id=ref.document_id,
                    ),
                    event_id=None,
                    title=f"{ref.document_id}",
                    summary=f"{ref.title}; {ref.document_type} rev {ref.revision}; approved={ref.approved}",
                    kind="security" if ref.injection_risk else "knowledge",
                    evidence_type="security" if ref.injection_risk else evidence_type,
                    source_agent="knowledge-agent",
                    source_event_id=ref.document_id,
                    confidence=ref.relevance_confidence,
                    order=40 if ref.document_type == "historical_incident" else 45,
                    metadata={
                        "document_id": ref.document_id,
                        "document_type": ref.document_type,
                        "revision": ref.revision,
                        "approved": ref.approved,
                        "injection_risk": ref.injection_risk,
                    },
                )
            )
        incident.evidence = self._merge_evidence(incident.evidence, evidence)
        return incident

    @staticmethod
    def _attach_impact(incident: Incident, impact: Any) -> Incident:
        incident.production_impact = impact
        if incident.status == IncidentStatus.DIAGNOSIS_READY:
            incident = transition_incident(incident, IncidentStatus.IMPACT_ANALYZED)
        return incident

    @staticmethod
    def _attach_plan(incident: Incident, plan: RecoveryPlan) -> Incident:
        incident.recovery_plan = plan
        if incident.status == IncidentStatus.IMPACT_ANALYZED:
            incident = transition_incident(incident, IncidentStatus.PLAN_READY)
        return incident

    @staticmethod
    def _attach_supervisor_decision(incident: Incident, decision: SupervisorDecision) -> Incident:
        incident.supervisor_decision = decision
        return incident
