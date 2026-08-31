import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const machine = {
  machine_id: "MC-04",
  cell: "5-AXIS CELL",
  model: "FX-5X",
  machine_type: "Five-Axis Machining Center",
  capabilities: ["5-axis", "vertical_mill"],
  state: "RUNNING",
  current_work_order_id: "MO-4821",
  current_operation: "OP30",
  active_alarm_codes: [],
  telemetry: {
    timestamp: "2026-08-25T10:00:00+00:00",
    spindle_load_pct: 55,
    x_axis_load_pct: 63,
    y_axis_load_pct: 42,
    z_axis_load_pct: 39,
    observed_cycle_time_sec: 184,
    target_cycle_time_sec: 184,
    tool_life_remaining_pct: 62,
  },
  telemetry_history: [
    {
      timestamp: "2026-08-25T10:00:00+00:00",
      spindle_load_pct: 55,
      x_axis_load_pct: 63,
      y_axis_load_pct: 42,
      z_axis_load_pct: 39,
      observed_cycle_time_sec: 184,
      target_cycle_time_sec: 184,
      tool_life_remaining_pct: 62,
    },
  ],
  health_score: 100,
  at_risk: false,
  operator: "Synthetic Operator 04",
};

const workOrder = {
  work_order_id: "MO-4821",
  part_number: "NP-4172",
  part_description: "Synthetic actuator housing",
  operation: "OP30",
  required_quantity: 120,
  completed_quantity: 78,
  scrap_quantity: 0,
  due_at: "2026-08-25T18:00:00+00:00",
  assigned_machine_id: "MC-04",
  target_cycle_time_sec: 184,
  observed_cycle_time_sec: 184,
  risk: "LOW",
  downstream_orders: [],
};

const agent = {
  agent_id: "observer-agent",
  name: "Observer Agent",
  version: "1.0.0",
  owner: "Northstar Operations AI",
  role: "Autonomous anomaly detection",
  purpose: "Consumes normalized factory events, correlates telemetry, and opens incidents.",
  status: "ACTIVE",
  deployment: "application-level ADK orchestration",
  runtime: "Google ADK LlmAgent manifest with local orchestrator fallback",
  model: "gemini-3.5-flash",
  identity: "forge://agents/observer-agent",
  allowed_tools: ["factory.events.read", "incidents.create"],
  denied_tools: ["machine.control", "plc.write", "servo.reset"],
  policy_scope: ["incident_detection"],
  instructions_summary: "Detect anomalies and cite evidence.",
  last_updated: "2026-08-25T10:00:00+00:00",
  latest_status: "SUCCEEDED",
  successful_executions: 1,
  failures: 0,
  latency_ms: 12,
  health: "HEALTHY",
  current_task: "INC-1042",
  last_execution: "2026-08-25T10:00:05+00:00",
};

const incident = {
  incident_id: "INC-1042",
  title: "Unexpected X-Axis Servo Overload",
  severity: "critical",
  status: "AWAITING_APPROVAL",
  machine_id: "MC-04",
  work_order_id: "MO-4821",
  correlation_id: "trc_servo_overload_cascade",
  created_at: "2026-08-25T10:00:00+00:00",
  updated_at: "2026-08-25T10:00:10+00:00",
  evidence: [
    {
      evidence_id: "INC-1042:observer-agent:trigger:evt_mc04_alarm_servo_x",
      event_id: "evt_mc04_alarm_servo_x",
      title: "Critical alarm",
      summary: "AXIS_SERVO_OVERLOAD_X on MC-04",
      kind: "event",
      evidence_type: "trigger",
      source_agent: "observer-agent",
      source_event_id: "evt_mc04_alarm_servo_x",
      source_event_ids: ["evt_mc04_alarm_servo_x"],
      order: 10,
      metadata: {},
      confidence: 0.94,
      created_at: "2026-08-25T10:00:01+00:00",
    },
  ],
  workflow: [
    { stage_id: "observer", agent_id: "observer-agent", label: "Observer", status: "SUCCEEDED", dependencies: [], action_summary: "Detected abnormal servo-load pattern", run_id: "run_1", started_at: "2026-08-25T10:00:01+00:00", completed_at: "2026-08-25T10:00:02+00:00", duration_ms: 800, retry_count: 0, order: 10 },
    { stage_id: "diagnostic", agent_id: "diagnostic-agent", label: "Diagnostic", status: "SUCCEEDED", dependencies: ["observer"], action_summary: "Mechanical resistance ranked most likely", run_id: "run_2", started_at: "2026-08-25T10:00:02+00:00", completed_at: "2026-08-25T10:00:04+00:00", duration_ms: 2100, retry_count: 0, order: 20 },
    { stage_id: "knowledge", agent_id: "knowledge-agent", label: "Knowledge", status: "SUCCEEDED", dependencies: ["observer"], action_summary: "3 relevant procedures retrieved", run_id: "run_3", started_at: "2026-08-25T10:00:02+00:00", completed_at: "2026-08-25T10:00:03+00:00", duration_ms: 900, retry_count: 0, order: 30 },
    { stage_id: "production", agent_id: "production-agent", label: "Production", status: "SUCCEEDED", dependencies: ["diagnostic", "knowledge"], action_summary: "42 units identified at schedule risk", run_id: "run_4", started_at: "2026-08-25T10:00:04+00:00", completed_at: "2026-08-25T10:00:05+00:00", duration_ms: 1400, retry_count: 0, order: 40 },
    { stage_id: "recovery", agent_id: "recovery-agent", label: "Recovery", status: "SUCCEEDED", dependencies: ["production"], action_summary: "Recovery workflow generated", run_id: "run_5", started_at: "2026-08-25T10:00:05+00:00", completed_at: "2026-08-25T10:00:06+00:00", duration_ms: 1200, retry_count: 0, order: 50 },
    { stage_id: "supervisor", agent_id: "supervisor-agent", label: "Supervisor", status: "SUCCEEDED", dependencies: ["recovery"], action_summary: "Digital actions approved; schedule transfer gated", run_id: "run_6", started_at: "2026-08-25T10:00:06+00:00", completed_at: "2026-08-25T10:00:07+00:00", duration_ms: 700, retry_count: 0, order: 60 },
  ],
  diagnosis: {
    summary: "MC-04 alarm pattern indicates probable X-axis mechanical resistance.",
    confidence: 0.81,
    probable_causes: [
      { cause: "X-axis mechanical resistance", confidence: 0.77, evidence: ["evt_mc04_alarm_servo_x"], contradictions: ["Spindle load is normal"] },
    ],
    recommended_checks: [],
    unsafe_to_auto_execute: [],
  },
  knowledge_result: {
    references: [],
    security_events: [],
    summary: "Retrieved references.",
  },
  production_impact: {
    remaining_quantity: 42,
    estimated_downtime_minutes: 95,
    delivery_risk: "HIGH",
    recommendation: "Reserve MC-02.",
    saved_minutes_if_reassigned: 72,
    alternatives: [
      { machine_id: "MC-02", capable: true, current_state: "IDLE", setup_minutes: 36, cycle_time_sec: 192, queue_minutes: 18, risk_notes: [] },
    ],
  },
  recovery_plan: {
    summary: "Build bounded recovery workflow.",
    steps: ["Place MC-04 in maintenance state"],
    verification_plan: [],
    physical_safety_boundary: "EPYK Forge never issues CNC motion.",
    proposals: [],
  },
  supervisor_decision: {
    effect: "APPROVAL_REQUIRED",
    approved_auto_actions: [],
    approval_required_actions: ["apply_schedule_change"],
    denied_actions: [],
    rationale: "Schedule application remains gated.",
  },
  approvals: [{ approval_id: "APV-1042", incident_id: "INC-1042", proposal_id: "SCH-1042", action_type: "apply_schedule_change", status: "PROPOSED", requested_at: "2026-08-25T10:00:07+00:00" }],
  schedule_proposals: [{ proposal_id: "SCH-1042", incident_id: "INC-1042", work_order_id: "MO-4821", from_machine_id: "MC-04", to_machine_id: "MC-02", quantity: 42, estimated_minutes_saved: 72, risk: "Fixture verification required", status: "PROPOSED", created_at: "2026-08-25T10:00:07+00:00" }],
  action_log: [],
  agent_runs: [],
  trace_spans: [],
};

let mockIncidents: unknown[] = [];
let mockActiveIncident: unknown | undefined;
let mockSecurity: unknown[] = [];

vi.mock("./api", () => ({
  api: {
    target: () => ({ baseUrl: "http://localhost:8080", configured: true, source: "local-default" }),
    connectivity: () => Promise.resolve({
      state: "connected",
      apiUrl: "http://localhost:8080",
      health: "ok",
      ready: "ready",
      message: "Forge API connected.",
    }),
    facility: () => Promise.resolve({
      facility_name: "Northstar Precision Works",
      synthetic: true,
      health_score: 92,
      machines_total: 1,
      machines_running: 1,
      machines_idle: 0,
      machines_alarmed: 0,
      machines_maintenance: 0,
      active_incidents: mockIncidents.length,
      at_risk_orders: mockIncidents.length ? 1 : 0,
      agent_fleet_status: "ACTIVE",
      model_provider: "TEST_STUB",
    }),
    machines: () => Promise.resolve([machine]),
    workOrders: () => Promise.resolve([workOrder]),
    incidents: () => Promise.resolve(mockIncidents),
    incident: () => Promise.resolve(mockActiveIncident),
    agents: () => Promise.resolve([agent]),
    registry: () => Promise.resolve([agent]),
    security: () => Promise.resolve(mockSecurity),
    traces: () => Promise.resolve([]),
    approvals: () => Promise.resolve(mockActiveIncident ? incident.approvals : []),
    system: () => Promise.resolve({
      product: "EPYK Forge",
      synthetic_facility: "Northstar Precision Works",
      environment: "local",
      service: "forge-api",
      model: "gemini-3.5-flash",
      model_provider: "TEST_STUB",
      agent_framework: "Google ADK",
      adk_status: "loaded",
      event_bus: "in-process event bus",
      state_store: "local JSON store",
      managed_agent_platform: {},
      cloud_claim_active: false,
    }),
    demoSeedStatus: () => Promise.resolve({
      demo_data_enabled: true,
      seed_profile: "northstar-precision-works-complete-demo",
      scenario_status: mockIncidents.length ? "AWAITING_APPROVAL" : "READY",
      collections: {
        machines: 10,
        work_orders: 3,
        knowledge_documents: 31,
        events: 0,
        incidents: mockIncidents.length,
        agent_registry: 6,
      },
    }),
  },
}));

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockIncidents = [];
    mockActiveIncident = undefined;
    mockSecurity = [];
  });

  it("renders useful nominal empty states", async () => {
    render(<App />);
    expect(await screen.findByText("Operations Center")).toBeInTheDocument();
    expect(screen.getByText("NO ACTIVE INCIDENT")).toBeInTheDocument();
    expect(screen.getByText(/Synthetic Hackathon Facility/)).toBeInTheDocument();
  });

  it("renders workflow-backed incident approval state", async () => {
    mockIncidents = [incident];
    mockActiveIncident = incident;
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^Incident$/ }));
    expect(await screen.findByText("INC-1042")).toBeInTheDocument();
    expect(screen.getByText("Detected abnormal servo-load pattern")).toBeInTheDocument();
    expect(screen.getByText("Supervisor Decision Required")).toBeInTheDocument();
    expect(screen.getByText("Remaining: 42 parts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve Transfer/ })).toBeInTheDocument();
  });

  it("renders structured blocked security events", async () => {
    mockSecurity = [
      {
        security_event_id: "SEC-INC-1042-UNAUTHORIZED-TOOL",
        timestamp: "2026-08-25T10:00:08+00:00",
        severity: "high",
        category: "UNAUTHORIZED_TOOL",
        event_type: "UNAUTHORIZED_TOOL",
        title: "Unauthorized tool request blocked",
        description: "Retrieved knowledge requested an external HTTP action.",
        principal: "knowledge-agent",
        agent: "knowledge-agent",
        source: "KB-MAL-001",
        requested_action: "external_http_request",
        policy: "least_privilege_tool_authorization",
        decision: "DENY",
        reason: "Principal lacks required permission external.http.request",
        denied_tool: "external_http_request",
        trace_id: "trc_servo_overload_cascade",
        incident_id: "INC-1042",
      },
    ];
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /^Security$/ }));
    expect(await screen.findByText("Unauthorized tool request blocked")).toBeInTheDocument();
    expect(screen.getByText("external_http_request")).toBeInTheDocument();
    expect(screen.getByText("least_privilege_tool_authorization")).toBeInTheDocument();
  });
});
