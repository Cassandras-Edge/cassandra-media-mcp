import { createMcpWorker } from "cassandra-mcp-auth";
import { registerMcpTools } from "./mcp-tools";
import { syncWatchLaterForAllKeys } from "./watch-later-cron";

const { default: mcpWorker, McpAgentClass } = createMcpWorker<Env>({
  serviceId: "yt-mcp",
  name: "Cassandra YT MCP",
  version: "1.0.0",
  registerTools(server, env, auth) {
    registerMcpTools(server, env, auth);
  },
});

export { McpAgentClass as CassandraYtMCP };
export default {
  fetch: mcpWorker.fetch,
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(syncWatchLaterForAllKeys(env));
  },
};
