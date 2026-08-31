import { describe, expect, it, vi } from "vitest";
import { ForgeApiError, getApiTarget, request } from "./api";

const productionEnv = {
  DEV: false,
  PROD: true,
  MODE: "production",
  VITE_FORGE_API_URL: "https://forge-api.example.run.app/",
};

function jsonResponse(value: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
}

function fetchReturning(response: Response): typeof fetch {
  return vi.fn(async () => response) as unknown as typeof fetch;
}

describe("Forge API configuration", () => {
  it("uses the local backend during Vite development when no API URL is configured", () => {
    expect(getApiTarget({ DEV: true }).baseUrl).toBe("http://localhost:8080");
  });

  it("uses the production API URL supplied to Vite", () => {
    expect(getApiTarget(productionEnv)).toMatchObject({
      baseUrl: "https://forge-api.example.run.app",
      configured: true,
      source: "vite",
    });
  });

  it("fails visibly when production is missing an API URL", async () => {
    const target = getApiTarget({ DEV: false, PROD: true, MODE: "production" });
    expect(target.configured).toBe(false);
    await expect(request("/health", undefined, { env: { DEV: false, PROD: true, MODE: "production" } })).rejects.toThrow(
      "Backend configuration is incomplete.",
    );
  });

  it("rejects relative production API URLs", () => {
    const target = getApiTarget({ DEV: false, PROD: true, MODE: "production", VITE_FORGE_API_URL: "/api" });
    expect(target.configured).toBe(false);
    expect(target.detail).toContain("absolute http(s) URL");
  });
});

describe("Forge API request handling", () => {
  it("parses JSON success responses", async () => {
    const result = await request<{ status: string }>("/health", undefined, {
      env: productionEnv,
      fetchImpl: fetchReturning(jsonResponse({ status: "ok" })),
    });
    expect(result).toEqual({ status: "ok" });
  });

  it("turns JSON HTTP errors into useful messages", async () => {
    await expect(
      request("/api/admin/setup/status", undefined, {
        env: productionEnv,
        fetchImpl: fetchReturning(jsonResponse({ detail: "Missing or invalid admin PIN" }, { status: 401 })),
      }),
    ).rejects.toMatchObject({
      name: "ForgeApiError",
      message: "Forge API returned HTTP 401: Missing or invalid admin PIN",
      status: 401,
    });
  });

  it("reports HTML responses before JSON parsing", async () => {
    await expect(
      request("/api/system/info", undefined, {
        env: productionEnv,
        fetchImpl: fetchReturning(new Response("<!doctype html><html></html>", { headers: { "content-type": "text/html" } })),
      }),
    ).rejects.toMatchObject({
      name: "ForgeApiError",
      kind: "content-type",
      message: "Forge API returned text/html instead of JSON.",
      bodyPreview: "<!doctype html><html></html>",
    });
  });

  it("reports non-JSON content types", async () => {
    await expect(
      request("/health", undefined, {
        env: productionEnv,
        fetchImpl: fetchReturning(new Response("ok", { headers: { "content-type": "text/plain" } })),
      }),
    ).rejects.toThrow("Forge API returned text/plain instead of JSON.");
  });

  it("reports connection failures", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;

    await expect(request("/health", undefined, { env: productionEnv, fetchImpl })).rejects.toBeInstanceOf(ForgeApiError);
    await expect(request("/health", undefined, { env: productionEnv, fetchImpl })).rejects.toThrow("Unable to reach Forge API.");
  });
});
