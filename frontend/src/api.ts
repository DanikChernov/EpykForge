import type {
  AgentManifest,
  AdminSeedPreview,
  AdminSetupStatus,
  Approval,
  DemoSeedStatus,
  Facility,
  Incident,
  Machine,
  SecurityEvent,
  SystemInfo,
  TraceSpan,
  WorkOrder,
} from "./types";

const DEFAULT_LOCAL_API_URL = "http://localhost:8080";
const DEFAULT_REQUEST_TIMEOUT_MS = 15000;
const BODY_PREVIEW_LIMIT = 500;

export interface ForgeApiEnv {
  DEV?: boolean;
  PROD?: boolean;
  MODE?: string;
  VITE_FORGE_API_URL?: string;
  VITE_API_BASE_URL?: string;
  VITE_DEMO_SUPERVISOR_TOKEN?: string;
}

export interface ApiTarget {
  baseUrl: string | null;
  configured: boolean;
  source: "vite" | "legacy-vite" | "local-default" | "missing";
  message?: string;
  detail?: string;
}

export type ApiConnectivityState = "checking" | "connected" | "unreachable" | "misconfigured";

export interface ApiConnectivityStatus {
  state: ApiConnectivityState;
  apiUrl: string | null;
  health?: string;
  ready?: string;
  httpStatus?: number;
  contentType?: string | null;
  message?: string;
  detail?: string;
}

export interface HealthStatus {
  status: string;
}

export interface ReadyStatus {
  status: string;
  store_backend?: string;
  model_provider?: string;
  adk_available?: boolean;
}

type ApiErrorKind = "configuration" | "network" | "timeout" | "http" | "content-type" | "json";

interface ForgeApiErrorOptions {
  kind: ApiErrorKind;
  url?: string;
  status?: number;
  contentType?: string | null;
  bodyPreview?: string;
  detail?: string;
}

export class ForgeApiError extends Error {
  kind: ApiErrorKind;
  url?: string;
  status?: number;
  contentType?: string | null;
  bodyPreview?: string;
  detail?: string;

  constructor(message: string, options: ForgeApiErrorOptions) {
    super(message);
    this.name = "ForgeApiError";
    this.kind = options.kind;
    this.url = options.url;
    this.status = options.status;
    this.contentType = options.contentType;
    this.bodyPreview = options.bodyPreview;
    this.detail = options.detail;
  }
}

interface ApiRequestOptions {
  env?: ForgeApiEnv;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

function envValue(value: string | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function isAbsoluteHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function getApiTarget(env: ForgeApiEnv = import.meta.env): ApiTarget {
  const forgeUrl = envValue(env.VITE_FORGE_API_URL);
  const legacyUrl = envValue(env.VITE_API_BASE_URL);
  const rawBaseUrl = forgeUrl || legacyUrl;
  const source = forgeUrl ? "vite" : legacyUrl ? "legacy-vite" : "missing";

  if (!rawBaseUrl) {
    if (env.DEV) {
      return {
        baseUrl: DEFAULT_LOCAL_API_URL,
        configured: true,
        source: "local-default",
      };
    }
    return {
      baseUrl: null,
      configured: false,
      source,
      message: "Backend configuration is incomplete.",
      detail: "Set VITE_FORGE_API_URL to the deployed forge-api URL before building the production frontend.",
    };
  }

  const baseUrl = trimTrailingSlash(rawBaseUrl);
  if (!isAbsoluteHttpUrl(baseUrl)) {
    return {
      baseUrl: null,
      configured: false,
      source,
      message: "Backend configuration is incomplete.",
      detail: "VITE_FORGE_API_URL must be an absolute http(s) URL. Relative /api URLs are not valid for the separate Cloud Run API service.",
    };
  }

  return {
    baseUrl,
    configured: true,
    source,
  };
}

function buildUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function previewBody(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, BODY_PREVIEW_LIMIT);
}

async function safeReadText(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}

function parseErrorDetail(contentType: string, body: string): string | undefined {
  if (!contentType.toLowerCase().includes("application/json") || !body) return undefined;
  try {
    const parsed = JSON.parse(body) as unknown;
    if (typeof parsed === "object" && parsed !== null && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function requestHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

function timeoutSignal(timeoutMs: number): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  return {
    signal: controller.signal,
    cancel: () => window.clearTimeout(timer),
  };
}

export async function request<T>(path: string, init?: RequestInit, options: ApiRequestOptions = {}): Promise<T> {
  const target = getApiTarget(options.env);
  if (!target.configured || !target.baseUrl) {
    throw new ForgeApiError(target.message ?? "Backend configuration is incomplete.", {
      kind: "configuration",
      detail: target.detail,
    });
  }

  const url = buildUrl(target.baseUrl, path);
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeout = timeoutSignal(options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS);
  let response: Response;

  try {
    response = await fetchImpl(url, {
      ...init,
      headers: requestHeaders(init),
      signal: init?.signal ?? timeout.signal,
    });
  } catch (caught) {
    const detail = caught instanceof Error ? caught.message : String(caught);
    if (caught instanceof DOMException && caught.name === "AbortError") {
      throw new ForgeApiError("Forge API request timed out.", {
        kind: "timeout",
        url,
        detail,
      });
    }
    throw new ForgeApiError("Unable to reach Forge API.", {
      kind: "network",
      url,
      detail,
    });
  } finally {
    timeout.cancel();
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (!response.ok) {
    const body = await safeReadText(response);
    const detail = parseErrorDetail(contentType, body);
    throw new ForgeApiError(
      detail ? `Forge API returned HTTP ${response.status}: ${detail}` : `Forge API returned HTTP ${response.status}.`,
      {
        kind: "http",
        url,
        status: response.status,
        contentType,
        bodyPreview: previewBody(body),
        detail,
      },
    );
  }

  if (!contentType.toLowerCase().includes("application/json")) {
    const body = await safeReadText(response);
    throw new ForgeApiError(`Forge API returned ${contentType || "unknown content type"} instead of JSON.`, {
      kind: "content-type",
      url,
      status: response.status,
      contentType,
      bodyPreview: previewBody(body),
    });
  }

  try {
    return (await response.json()) as T;
  } catch (caught) {
    throw new ForgeApiError("Forge API returned malformed JSON.", {
      kind: "json",
      url,
      status: response.status,
      contentType,
      detail: caught instanceof Error ? caught.message : String(caught),
    });
  }
}

export async function checkApiConnectivity(options: ApiRequestOptions = {}): Promise<ApiConnectivityStatus> {
  const target = getApiTarget(options.env);
  if (!target.configured) {
    return {
      state: "misconfigured",
      apiUrl: target.baseUrl,
      message: target.message,
      detail: target.detail,
    };
  }

  try {
    const health = await request<HealthStatus>("/health", undefined, options);
    const ready = await request<ReadyStatus>("/ready", undefined, options);
    return {
      state: "connected",
      apiUrl: target.baseUrl,
      health: health.status,
      ready: ready.status,
      message: "Forge API connected.",
    };
  } catch (caught) {
    if (caught instanceof ForgeApiError) {
      return {
        state: caught.kind === "configuration" ? "misconfigured" : "unreachable",
        apiUrl: target.baseUrl,
        httpStatus: caught.status,
        contentType: caught.contentType,
        message: caught.message,
        detail: caught.bodyPreview || caught.detail,
      };
    }
    return {
      state: "unreachable",
      apiUrl: target.baseUrl,
      message: "Unable to reach Forge API.",
      detail: caught instanceof Error ? caught.message : String(caught),
    };
  }
}

function demoSupervisorToken(env: ForgeApiEnv = import.meta.env): string {
  return envValue(env.VITE_DEMO_SUPERVISOR_TOKEN) || "demo-supervisor-token";
}

export const api = {
  target: () => getApiTarget(),
  connectivity: () => checkApiConnectivity(),
  health: () => request<HealthStatus>("/health"),
  ready: () => request<ReadyStatus>("/ready"),
  facility: () => request<Facility>("/api/facility"),
  machines: () => request<Machine[]>("/api/machines"),
  workOrders: () => request<WorkOrder[]>("/api/work-orders"),
  incidents: () => request<Incident[]>("/api/incidents"),
  incident: (incidentId: string) => request<Incident>(`/api/incidents/${incidentId}`),
  agents: () => request<AgentManifest[]>("/api/agents"),
  registry: () => request<AgentManifest[]>("/api/registry"),
  security: () => request<SecurityEvent[]>("/api/security/events"),
  traces: () => request<TraceSpan[]>("/api/traces"),
  approvals: () => request<Approval[]>("/api/approvals"),
  system: () => request<SystemInfo>("/api/system/info"),
  demoSeedStatus: () => request<DemoSeedStatus>("/api/demo/seed/status"),
  importDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/import", { method: "POST" }),
  enableDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/enable", { method: "POST" }),
  disableDemoSeed: () => request<DemoSeedStatus & { status: string }>("/api/demo/seed/disable", { method: "POST" }),
  adminSetupStatus: (pin: string) => request<AdminSetupStatus>("/api/admin/setup/status", { headers: { "x-admin-pin": pin } }),
  adminSeedPreview: (pin: string) => request<AdminSeedPreview>("/api/admin/seed/preview", { headers: { "x-admin-pin": pin } }),
  adminImportSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/import", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminEnableSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/enable", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminDisableSeed: (pin: string) => request<DemoSeedStatus & { status: string }>("/api/admin/seed/disable", { method: "POST", headers: { "x-admin-pin": pin } }),
  adminGeminiSmoke: (pin: string) => request<Record<string, unknown>>("/api/admin/gemini/smoke", { method: "POST", headers: { "x-admin-pin": pin } }),
  resetDemo: () => request<{ status: string }>("/api/demo/reset", { method: "POST" }),
  startDemo: () => request<{ status: string; incident_id?: string }>("/api/demo/start", { method: "POST", body: JSON.stringify({ sync: false }) }),
  startDemoSync: () => request<{ status: string; incident_id?: string }>("/api/demo/start", { method: "POST", body: JSON.stringify({ sync: true, speed: 99 }) }),
  inject: (name: string) => request<Record<string, unknown>>(`/api/demo/inject/${name}`, { method: "POST" }),
  approve: (incidentId: string, approvalId?: string) =>
    request<Record<string, unknown>>(`/api/incidents/${incidentId}/approve`, {
      method: "POST",
      headers: { "x-demo-token": demoSupervisorToken() },
      body: JSON.stringify({ approval_id: approvalId, decision_note: "Approved in synthetic demo console" }),
    }),
  reject: (incidentId: string, approvalId?: string) =>
    request<Record<string, unknown>>(`/api/incidents/${incidentId}/reject`, {
      method: "POST",
      headers: { "x-demo-token": demoSupervisorToken() },
      body: JSON.stringify({ approval_id: approvalId, decision_note: "Rejected in synthetic demo console" }),
    }),
};
