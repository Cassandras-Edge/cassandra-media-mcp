import { vi } from "vitest";

export function createMockKV(): KVNamespace & {
  _store: Map<string, string>;
} {
  const store = new Map<string, string>();

  return {
    _store: store,
    delete: vi.fn(async (key: string) => {
      store.delete(key);
    }),
    get: vi.fn(async (key: string, opts?: string | { type?: string }) => {
      const value = store.get(key);
      if (!value) {
        return null;
      }
      if (opts === "json" || (typeof opts !== "string" && opts?.type === "json")) {
        return JSON.parse(value);
      }
      return value;
    }),
    getWithMetadata: vi.fn(),
    list: vi.fn(async () => ({
      cacheStatus: null,
      keys: Array.from(store.keys()).map((name) => ({ name })),
      list_complete: true,
    })),
    put: vi.fn(async (key: string, value: string) => {
      store.set(key, value);
    }),
  } as unknown as KVNamespace & { _store: Map<string, string> };
}

export function createMockEnv(overrides: Partial<Env & { OAUTH_PROVIDER: unknown }> = {}): Env & {
  MCP_KEYS: KVNamespace & { _store: Map<string, string> };
  OAUTH_KV: KVNamespace & { _store: Map<string, string> };
  OAUTH_PROVIDER?: unknown;
} {
  return {
    BACKEND_API_TOKEN: "backend-token",
    BACKEND_BASE_URL: "https://backend.example.test",
    CF_ACCESS_CLIENT_ID: "cf-client-id",
    CF_ACCESS_CLIENT_SECRET: "cf-client-secret",
    COOKIE_ENCRYPTION_KEY: "cookie-secret",
    MCP_KEYS: createMockKV(),
    OAUTH_KV: createMockKV(),
    VM_PUSH_CLIENT_ID: "metrics-client-id",
    VM_PUSH_CLIENT_SECRET: "metrics-client-secret",
    VM_PUSH_URL: "https://metrics.example.test",
    WORKOS_CLIENT_ID: "workos-client-id",
    WORKOS_CLIENT_SECRET: "workos-client-secret",
    ...overrides,
  } as Env & {
    MCP_KEYS: KVNamespace & { _store: Map<string, string> };
    OAUTH_KV: KVNamespace & { _store: Map<string, string> };
  };
}

export async function json<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

export function createExecutionContext(): ExecutionContext {
  return {
    passThroughOnException: vi.fn(),
    props: {},
    waitUntil: vi.fn(),
  } as unknown as ExecutionContext;
}
