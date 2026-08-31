from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class MachineState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    IDLE = "IDLE"
    SETUP = "SETUP"
    RUNNING = "RUNNING"
    FEED_HOLD = "FEED_HOLD"
    ALARM = "ALARM"
    MAINTENANCE = "MAINTENANCE"
    RECOVERY = "RECOVERY"


class EventType(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    SETUP = "setup"
    RUNNING = "running"
    CYCLE_START = "cycle_start"
    CYCLE_COMPLETE = "cycle_complete"
    FEED_HOLD = "feed_hold"
    ALARM = "alarm"
    MAINTENANCE = "maintenance"
    RECOVERY = "recovery"
    OPERATOR_NOTE = "operator_note"
    INSPECTION_RESULT = "inspection_result"
    TOOL_CHANGE = "tool_change"
    TOOL_LIFE_WARNING = "tool_life_warning"
    TELEMETRY = "telemetry"
    SCRAP_EVENT = "scrap_event"
    QUALITY_DEVIATION = "quality_deviation"
    SECURITY_TEST = "security_test"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSIS_READY = "DIAGNOSIS_READY"
    IMPACT_ANALYZED = "IMPACT_ANALYZED"
    PLAN_READY = "PLAN_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    ACTIONING = "ACTIONING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    LEARNED = "LEARNED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class AgentRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class ActionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class WorkOrderRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TelemetrySample(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    spindle_load_pct: float = 0
    x_axis_load_pct: float = 0
    y_axis_load_pct: float = 0
    z_axis_load_pct: float = 0
    observed_cycle_time_sec: float = 0
    target_cycle_time_sec: float = 0
    tool_life_remaining_pct: float = 100


class Machine(BaseModel):
    machine_id: str
    cell: str
    model: str
    machine_type: str
    capabilities: list[str]
    state: MachineState
    current_work_order_id: str | None = None
    current_operation: str | None = None
    active_alarm_codes: list[str] = Field(default_factory=list)
    telemetry: TelemetrySample
    telemetry_history: list[TelemetrySample] = Field(default_factory=list)
    health_score: int = Field(default=100, ge=0, le=100)
    at_risk: bool = False
    operator: str = "Synthetic Operator"


class WorkOrder(BaseModel):
    work_order_id: str
    part_number: str
    part_description: str
    operation: str
    required_quantity: int
    completed_quantity: int
    scrap_quantity: int = 0
    due_at: str
    assigned_machine_id: str
    target_cycle_time_sec: float
    observed_cycle_time_sec: float
    risk: WorkOrderRisk = WorkOrderRisk.LOW
    downstream_orders: list[str] = Field(default_factory=list)

    @property
    def remaining_quantity(self) -> int:
        return max(self.required_quantity - self.completed_quantity - self.scrap_quantity, 0)


class MachineEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    timestamp: str = Field(default_factory=utc_now_iso)
    event_type: EventType
    source: str
    machine_id: str | None = None
    work_order_id: str | None = None
    correlation_id: str = Field(default_factory=lambda: new_id("trc"))
    trace_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "1.0"


class IncidentEvidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("evd"))
    event_id: str | None = None
    title: str
    summary: str
    kind: Literal["event", "telemetry", "knowledge", "agent", "operator", "security"]
    evidence_type: str = "event"
    source_agent: str | None = None
    source_event_id: str | None = None
    source_event_ids: list[str] = Field(default_factory=list)
    order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    created_at: str = Field(default_factory=utc_now_iso)


class ObserverFinding(BaseModel):
    incident_required: bool
    severity: Severity
    machine_id: str | None
    reason: str
    evidence_event_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class ProbableCause(BaseModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class Diagnosis(BaseModel):
    incident_id: str
    probable_causes: list[ProbableCause]
    recommended_checks: list[str]
    unsafe_to_auto_execute: list[str]
    confidence: float = Field(ge=0, le=1)
    summary: str


class KnowledgeReference(BaseModel):
    document_id: str
    title: str
    document_type: str
    revision: str
    approved: bool
    excerpt: str
    relevance_confidence: float = Field(ge=0, le=1)
    injection_risk: bool = False


class KnowledgeResult(BaseModel):
    incident_id: str
    references: list[KnowledgeReference]
    security_events: list[str] = Field(default_factory=list)
    summary: str


class AlternativeMachine(BaseModel):
    machine_id: str
    capable: bool
    current_state: MachineState
    setup_minutes: int
    cycle_time_sec: float
    queue_minutes: int
    risk_notes: list[str] = Field(default_factory=list)


class ProductionImpact(BaseModel):
    incident_id: str
    work_order_id: str
    remaining_quantity: int
    estimated_downtime_minutes: int
    delivery_risk: WorkOrderRisk
    alternatives: list[AlternativeMachine]
    recommendation: str
    saved_minutes_if_reassigned: int


class ActionProposal(BaseModel):
    action_id: str = Field(default_factory=lambda: new_id("act"))
    action_type: str
    title: str
    params: dict[str, Any]
    requested_by: str
    approval_required: bool
    risk: str


class RecoveryPlan(BaseModel):
    incident_id: str
    summary: str
    steps: list[str]
    proposals: list[ActionProposal]
    verification_plan: list[str]
    physical_safety_boundary: str


class SupervisorDecision(BaseModel):
    incident_id: str
    effect: PolicyEffect
    approved_auto_actions: list[str] = Field(default_factory=list)
    approval_required_actions: list[str] = Field(default_factory=list)
    denied_actions: list[str] = Field(default_factory=list)
    rationale: str


class WorkflowStage(BaseModel):
    stage_id: str
    agent_id: str
    label: str
    status: AgentRunStatus = AgentRunStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    action_summary: str | None = None
    run_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    error: str | None = None
    parallel_group: str | None = None
    order: int


WORKFLOW_STAGE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "stage_id": "observer",
        "agent_id": "observer-agent",
        "label": "Observer",
        "dependencies": [],
        "parallel_group": None,
        "order": 10,
    },
    {
        "stage_id": "diagnostic",
        "agent_id": "diagnostic-agent",
        "label": "Diagnostic",
        "dependencies": ["observer"],
        "parallel_group": "analysis",
        "order": 20,
    },
    {
        "stage_id": "knowledge",
        "agent_id": "knowledge-agent",
        "label": "Knowledge",
        "dependencies": ["observer"],
        "parallel_group": "analysis",
        "order": 30,
    },
    {
        "stage_id": "production",
        "agent_id": "production-agent",
        "label": "Production",
        "dependencies": ["diagnostic", "knowledge"],
        "parallel_group": None,
        "order": 40,
    },
    {
        "stage_id": "recovery",
        "agent_id": "recovery-agent",
        "label": "Recovery",
        "dependencies": ["production"],
        "parallel_group": None,
        "order": 50,
    },
    {
        "stage_id": "supervisor",
        "agent_id": "supervisor-agent",
        "label": "Supervisor",
        "dependencies": ["recovery"],
        "parallel_group": None,
        "order": 60,
    },
]


def default_workflow_stages() -> list[WorkflowStage]:
    return [WorkflowStage(**definition) for definition in WORKFLOW_STAGE_DEFINITIONS]


class Incident(BaseModel):
    incident_id: str
    title: str
    severity: Severity
    status: IncidentStatus
    machine_id: str
    work_order_id: str | None
    correlation_id: str
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    evidence: list[IncidentEvidence] = Field(default_factory=list)
    workflow: list[WorkflowStage] = Field(default_factory=default_workflow_stages)
    diagnosis: Diagnosis | None = None
    knowledge_result: KnowledgeResult | None = None
    production_impact: ProductionImpact | None = None
    recovery_plan: RecoveryPlan | None = None
    supervisor_decision: SupervisorDecision | None = None
    resolution_summary: str | None = None
    learned_at: str | None = None


class MaintenanceTicket(BaseModel):
    ticket_id: str
    incident_id: str
    machine_id: str
    severity: Severity
    title: str
    description: str
    checklist: list[str]
    evidence_event_ids: list[str]
    status: str = "OPEN"
    created_at: str = Field(default_factory=utc_now_iso)


class ScheduleProposal(BaseModel):
    proposal_id: str
    incident_id: str
    work_order_id: str
    from_machine_id: str
    to_machine_id: str
    quantity: int
    estimated_minutes_saved: int
    risk: str
    status: ActionStatus = ActionStatus.PROPOSED
    created_at: str = Field(default_factory=utc_now_iso)
    approved_at: str | None = None
    approved_by: str | None = None


class Notification(BaseModel):
    notification_id: str
    severity: Severity
    title: str
    message: str
    incident_id: str | None = None
    machine_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    acknowledged: bool = False


class AgentManifest(BaseModel):
    agent_id: str
    name: str
    version: str
    owner: str
    role: str
    purpose: str
    status: str
    deployment: str
    runtime: str
    model: str
    identity: str
    allowed_tools: list[str]
    denied_tools: list[str]
    policy_scope: list[str]
    instructions_summary: str
    last_updated: str


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    agent_id: str
    incident_id: str | None = None
    status: AgentRunStatus
    started_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    output_summary: str | None = None
    tool_calls: list[str] = Field(default_factory=list)
    model: str | None = None
    model_provider: str | None = None
    trace_id: str | None = None
    error: str | None = None
    retry_count: int = 0
    duration_ms: int | None = None


class PolicyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("pol"))
    timestamp: str = Field(default_factory=utc_now_iso)
    principal: str
    action: str
    resource: str | None = None
    effect: PolicyEffect
    reason: str
    trace_id: str | None = None
    incident_id: str | None = None


class SecurityEvent(BaseModel):
    security_event_id: str = Field(default_factory=lambda: new_id("sec"))
    timestamp: str = Field(default_factory=utc_now_iso)
    severity: Severity
    category: str
    event_type: str = "POLICY_VIOLATION"
    title: str
    description: str
    principal: str | None = None
    agent: str | None = None
    source: str | None = None
    requested_action: str | None = None
    policy: str | None = None
    decision: str | None = None
    reason: str | None = None
    denied_tool: str | None = None
    trace_id: str | None = None
    incident_id: str | None = None


class OperationalMemory(BaseModel):
    memory_id: str = Field(default_factory=lambda: new_id("mem"))
    timestamp: str = Field(default_factory=utc_now_iso)
    incident_id: str
    machine_id: str
    memory_type: Literal["fact", "historical_outcome", "inferred_preference", "unverified_hypothesis"]
    content: str
    confidence: float = Field(ge=0, le=1)
    source: str


class TraceSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: new_id("span"))
    trace_id: str
    correlation_id: str
    name: str
    parent_span_id: str | None = None
    agent_id: str | None = None
    status: str = "OK"
    started_at: str = Field(default_factory=utc_now_iso)
    ended_at: str | None = None
    duration_ms: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Approval(BaseModel):
    approval_id: str = Field(default_factory=lambda: new_id("apv"))
    incident_id: str
    proposal_id: str
    action_type: str
    status: ActionStatus = ActionStatus.PROPOSED
    requested_at: str = Field(default_factory=utc_now_iso)
    decided_at: str | None = None
    decided_by: str | None = None
    decision_note: str | None = None

    @field_validator("action_type")
    @classmethod
    def forbid_physical_actions(cls, value: str) -> str:
        if value.startswith("machine.control") or value in {"cycle_start", "axis_jog", "spindle_start"}:
            raise ValueError("Physical CNC actuation is outside EPYK Forge boundaries")
        return value
