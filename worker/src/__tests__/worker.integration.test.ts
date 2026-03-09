import { describe, expect, it, vi } from "vitest";

const mockPushMetrics = vi.fn();
const mockCounter = vi.fn((name: string, value: number, labels: Record<string, string>) => ({
  name,
  value,
  labels,
}));

vi.mock("cassandra-observability", () => ({
  pushMetrics: mockPushMetrics,
  counter: mockCounter,
}));

vi.mock("@cloudflare/workers-oauth-provider", () => ({
  default: class MockOAuthProvider {
    options: any;
    fetch: ReturnType<typeof vi.fn>;
    constructor(options: any) {
      this.options = options;
      this.fetch = vi.fn(async () => new Response("ok", { status: 200 }));
    }
  },
}));

vi.mock("agents/mcp", () => ({
  McpAgent: class MockMcpAgent {
    static serve = vi.fn((path: string) => ({ type: "api-handler", path }));
    env: unknown;
    props: unknown;
  },
}));

vi.mock("@modelcontextprotocol/sdk/server/mcp.js", () => ({
  McpServer: class MockMcpServer {
    _registeredTools: Record<string, unknown> = {};
    constructor(public options: any) {}
    registerTool(name: string, def: unknown, handler: unknown) {
      this._registeredTools[name] = { def, handler };
    }
  },
}));

const { CassandraYtMCP, default: worker } = await import("../index");

describe("yt-mcp worker via createMcpWorker", () => {
  it("exports the McpAgent class with correct server name", () => {
    const agent = new CassandraYtMCP();
    expect(agent.server).toBeDefined();
    expect(agent.server.options).toEqual(
      expect.objectContaining({ name: "Cassandra YT MCP", version: "1.0.0" }),
    );
  });

  it("registers all 8 yt-mcp tools on init", async () => {
    const agent = new CassandraYtMCP();
    (agent as any).env = {
      BACKEND_BASE_URL: "https://backend.test",
      BACKEND_API_TOKEN: "test-token",
    };
    (agent as any).props = { userId: "test-user" };

    await agent.init();

    const tools = (agent.server as any)._registeredTools;
    expect(Object.keys(tools)).toEqual([
      "transcribe",
      "job_status",
      "search",
      "list_transcripts",
      "read_transcript",
      "yt_search",
      "get_metadata",
      "get_comments",
    ]);
  });

  it("records metrics on fetch", async () => {
    const waitUntil = vi.fn();
    const response = await worker.fetch(
      new Request("https://worker.example/mcp/sse"),
      {
        VM_PUSH_URL: "https://vm.example",
        VM_PUSH_CLIENT_ID: "id",
        VM_PUSH_CLIENT_SECRET: "secret",
      } as any,
      { waitUntil, passThroughOnException: vi.fn() } as any,
    );

    expect(response.status).toBe(200);
    expect(waitUntil).toHaveBeenCalledTimes(1);
    await waitUntil.mock.calls[0][0];

    expect(mockCounter).toHaveBeenCalledWith("mcp_requests_total", 1, {
      service: "yt-mcp",
      status: "200",
      path: "/mcp",
    });
  });
});
