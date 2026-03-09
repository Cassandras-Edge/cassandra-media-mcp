import { afterEach, describe, expect, it, vi } from "vitest";
import { backendGet, backendPost, jsonToolResponse } from "../backend";
import { createMockEnv } from "./test-helpers";

describe("backend helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("adds auth headers and query parameters for GET requests", async () => {
    const env = createMockEnv();
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const payload = await backendGet(env, "/api/transcripts", {
      channel: "demo",
      ignored: undefined,
      limit: 5,
    });

    expect(payload).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call as unknown as [string, RequestInit];
    expect(url).toBe("https://backend.example.test/api/transcripts?channel=demo&limit=5");
    expect(init.method).toBe("GET");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer backend-token");
    expect(headers.get("CF-Access-Client-Id")).toBe("cf-client-id");
    expect(headers.get("CF-Access-Client-Secret")).toBe("cf-client-secret");
  });

  it("serializes JSON POST bodies and omits optional headers when absent", async () => {
    const env = createMockEnv({
      BACKEND_API_TOKEN: undefined,
      CF_ACCESS_CLIENT_ID: undefined,
      CF_ACCESS_CLIENT_SECRET: undefined,
    });
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ job_id: "job-1" }), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const payload = await backendPost(env, "/api/jobs/transcribe", { url: "https://youtu.be/demo" });

    expect(payload).toEqual({ job_id: "job-1" });
    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const [, init] = call as unknown as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("CF-Access-Client-Id")).toBeNull();
    expect(headers.get("CF-Access-Client-Secret")).toBeNull();
    expect(init.body).toBe(JSON.stringify({ url: "https://youtu.be/demo" }));
  });

  it("surfaces backend detail messages when available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "backend denied request" }), {
          headers: { "Content-Type": "application/json" },
          status: 403,
        }),
      ),
    );

    await expect(backendGet(createMockEnv(), "/api/transcripts")).rejects.toThrow(
      "backend denied request",
    );
  });

  it("falls back to status-based errors for non-JSON responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("upstream exploded", { status: 502 })),
    );

    await expect(backendGet(createMockEnv(), "/api/transcripts")).rejects.toThrow(
      "Backend request failed (502)",
    );
  });
});

describe("jsonToolResponse", () => {
  it("preserves the current MCP JSON text response shape", () => {
    expect(jsonToolResponse({ ok: true })).toEqual({
      content: [{ text: JSON.stringify({ ok: true }), type: "text" }],
    });
  });
});
