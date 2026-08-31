export type MachineState =
  | "CONNECTED"
  | "DISCONNECTED"
  | "IDLE"
  | "SETUP"
  | "RUNNING"
  | "FEED_HOLD"
  | "ALARM"
  | "MAINTENANCE"
  | "RECOVERY";

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface TelemetrySample {
  timestamp: string;
  spindle_load_pct: number;
  x_axis_load_pct: number;
  y_axis_load_pct: number;
  z_axis_load_pct: number;
  observed_cycle_time_sec: number;
  target_cycle_time_sec: number;
  tool_life_remaining_pct: number;
}

export interface Machine {
  machine_id: string;
  cell: string;
  model: string;
  machine_type: string;
  capabilities: string[];
  state: MachineState;
  current_work_order_id?: string | null;
  current_operation?: string | null;
  active_alarm_codes: string[];
  telemetry: TelemetrySample;
  telemetry_history: TelemetrySample[];
  health_score: number;
  at_risk: boolean;
  operator: string;
}

export interface Facility {
  facility_name: string;
  synthetic: boolean;
  health_score: number;
  machines_total: number;
  machines_running: number;
  machines_idle: number;
  machines_alarmed: number;
  machines_maintenance: number;
  active_incidents: number;
  at_risk_orders: number;
  agent_fleet_status: string;
  model_provider: string;
}

export interface WorkOrder {
  work_order_id: string;
  part_number: string;
  part_description: string;
  operation: string;
  required_quantity: number;
  completed_quantity: number;
  scrap_quantity: number;
  due_at: string;
  assigned_machine_id: string;
  target_cycle_time_sec: number;
  observed_cycle_time_sec: number;
  risk: string;
  downstream_orders: string[];
}

export interface AgentRun {
  run_id: string;
  agent_id: string;
  incident_id?: string | null;
  status: string;
  started_at: string;
  completed_at?: string | null;
  input_refs: string[];
  output_summary?: string | null;
  tool_calls: string[];
  model?: string | null;
  model_provider?: string | null;
  trace_id?: string | null;
  error?: string | null;
  retry_count: number;
  duration_ms?: number | null;
}

export interface AgentManifest {
  agent_id: string;
  name: string;
  version: string;
  owner: string;
  role: string;
  purpose: string;
  status: string;
  deployment: string;
  runtime: string;
  model: string;
  identity: string;
  allowed_tools: string[];
  denied_tools: string[];
  policy_scope: string[];
  instructions_summary: string;
  latest_status?: string;
  successful_executions?: number;
  failures?: number;
  latency_ms?: number | null;
  health?: string;
  current_task?: string | null;
  last_execution?: string | null;
  provider_status?: string | null;
  fallback_used?: boolean;
  fallback_reason?: string | null;
}

export interface KnowledgeReference {
  document_id: string;
  title: string;
  document_type: string;
  revision: string;
  approved: boolean;
  excerpt: string;
  relevance_confidence: number;
  injection_risk: boolean;
  provenance?: string | null;
  trust_classification?: string | null;
}

export interface IncidentEvidence {
  evidence_id: string;
  event_id?: string | null;
  title: string;
  summary: string;
  kind: string;
  evidence_type: string;
  source_agent?: string | null;
  source_event_id?: string | null;
  source_event_ids: string[];
  order: number;
  metadata: Record<string, unknown>;
  confidence: number;
  created_at: string;
}

export interface WorkflowStage {
  stage_id: string;
  agent_id: string;
  label: string;
  status: string;
  dependencies: string[];
  action_summary?: string | null;
  run_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  retry_count: number;
  error?: string | null;
  provider_status?: string | null;
  fallback_used?: boolean;
  fallback_reason?: string | null;
  parallel_group?: string | null;
  order: number;
}

export interface ScheduleProposal {
  proposal_id: string;
  incident_id: string;
  work_order_id: string;
  from_machine_id: string;
  to_machine_id: string;
  quantity: number;
  estimated_minutes_saved: number;
  risk: string;
  status: string;
  created_at: string;
  approved_at?: string | null;
  approved_by?: string | null;
}

export interface Incident {
  incident_id: string;
  title: string;
  severity: Severity;
  status: string;
  machine_id: string;
  work_order_id?: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
  evidence: IncidentEvidence[];
  workflow: WorkflowStage[];
  diagnosis?: {
    summary: string;
    confidence: number;
    probable_causes: Array<{ cause: string; confidence: number; evidence: string[]; contradictions: string[] }>;
    recommended_checks: string[];
    unsafe_to_auto_execute: string[];
  } | null;
  knowledge_result?: {
    references: KnowledgeReference[];
    security_events: string[];
    summary: string;
  } | null;
  production_impact?: {
    remaining_quantity: number;
    estimated_downtime_minutes: number;
    delivery_risk: string;
    recommendation: string;
    saved_minutes_if_reassigned: number;
    alternatives: Array<{
      machine_id: string;
      capable: boolean;
      current_state: MachineState;
      setup_minutes: number;
      cycle_time_sec: number;
      queue_minutes: number;
      risk_notes: string[];
    }>;
  } | null;
  recovery_plan?: {
    summary: string;
    steps: string[];
    verification_plan: string[];
    physical_safety_boundary: string;
    proposals: Array<{ action_type: string; title: string; approval_required: boolean; risk: string }>;
  } | null;
  supervisor_decision?: {
    effect: string;
    approved_auto_actions: string[];
    approval_required_actions: string[];
    denied_actions: string[];
    rationale: string;
  } | null;
  approvals?: Approval[];
  schedule_proposals?: ScheduleProposal[];
  action_log?: ActionExecution[];
  agent_runs?: AgentRun[];
  trace_spans?: TraceSpan[];
  resolution_summary?: string | null;
  learned_at?: string | null;
}

export interface Approval {
  approval_id: string;
  incident_id: string;
  proposal_id: string;
  action_type: string;
  status: string;
  requested_at: string;
  decided_at?: string | null;
}

export interface ActionExecution {
  execution_id: string;
  action_type: string;
  principal: string;
  status: string;
  incident_id?: string | null;
  summary: string;
  timestamp: string;
}

export interface SecurityEvent {
  security_event_id: string;
  timestamp: string;
  severity: Severity;
  category: string;
  event_type: string;
  title: string;
  description: string;
  principal?: string | null;
  agent?: string | null;
  source?: string | null;
  requested_action?: string | null;
  policy?: string | null;
  decision?: string | null;
  reason?: string | null;
  denied_tool?: string | null;
  trace_id?: string | null;
  incident_id?: string | null;
}

export interface TraceSpan {
  span_id: string;
  trace_id: string;
  correlation_id: string;
  name: string;
  parent_span_id?: string | null;
  agent_id?: string | null;
  status: string;
  duration_ms?: number | null;
  attributes: Record<string, unknown>;
  started_at: string;
  ended_at?: string | null;
}

export interface SystemInfo {
  product: string;
  synthetic_facility: string;
  environment: string;
  service: string;
  region?: string | null;
  google_cloud_location?: string | null;
  revision?: string | null;
  web_origin?: string | null;
  model: string;
  model_provider: string;
  agent_framework: string;
  adk_status: string;
  event_bus: string;
  state_store: string;
  managed_agent_platform: Record<string, boolean>;
  cloud_claim_active: boolean;
}

export interface DemoControlState {
  enabled: boolean;
  reason: string;
}

export interface DemoSeedStatus {
  demo_data_enabled: boolean;
  seed_profile: string;
  seed_schema_version?: string | null;
  seed_batch_id?: string | null;
  seeded_at?: string | null;
  scenario_id?: string | null;
  scenario_status: string;
  scenario_message?: string;
  run_id?: string | null;
  provider_fallbacks?: Array<{
    agent_id: string;
    provider: string;
    reason: string;
    trace_id?: string | null;
    timestamp: string;
  }>;
  collections: Record<string, number>;
  controls?: Record<string, DemoControlState>;
}

export interface SnapshotResponse {
  facility: Facility;
  machines: Machine[];
  workOrders: WorkOrder[];
  incidents: Incident[];
  activeIncident?: Incident | null;
  agents: AgentManifest[];
  registry: AgentManifest[];
  security: SecurityEvent[];
  traces: TraceSpan[];
  approvals: Approval[];
  system: SystemInfo;
  demoSeed: DemoSeedStatus;
}

export interface AdminSetupStatus {
  admin: {
    authenticated: boolean;
    pin_configured: boolean;
  };
  runtime: {
    environment: string;
    service: string;
    store_backend: string;
    event_bus: string;
    running_on_google_cloud: boolean;
  };
  gemini: {
    model_provider: string;
    model: string;
    real_gemini_enabled: boolean;
    google_cloud_project?: string | null;
    google_cloud_project_configured: boolean;
    google_cloud_location: string;
    google_genai_use_enterprise: boolean;
    adk_available: boolean;
    adk_status: string;
    google_adk_importable: boolean;
    google_genai_importable: boolean;
    gcloud_on_path: boolean;
    smoke_test_required: boolean;
  };
  seed: DemoSeedStatus;
  actions: Record<string, string>;
}

export interface AdminSeedPreview {
  status: DemoSeedStatus;
  machines: Machine[];
  work_orders: Array<{
    work_order_id: string;
    part_number: string;
    part_description: string;
    operation: string;
    required_quantity: number;
    completed_quantity: number;
    assigned_machine_id: string;
    due_at: string;
  }>;
  knowledge_documents: Array<{
    document_id: string;
    title: string;
    document_type: string;
    revision: string;
    approved: boolean;
    equipment_scope: string[];
    tags: string[];
    content: string;
  }>;
  agent_registry: AgentManifest[];
  scenario_state: Array<Record<string, unknown>>;
}
