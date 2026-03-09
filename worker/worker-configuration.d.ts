import type { McpAuthEnv } from "cassandra-mcp-auth";

declare namespace Cloudflare {
  interface Env extends McpAuthEnv {
    BACKEND_BASE_URL: string;
    BACKEND_API_TOKEN?: string;
    CF_ACCESS_CLIENT_ID?: string;
    CF_ACCESS_CLIENT_SECRET?: string;
  }
}

interface Env extends Cloudflare.Env {}
