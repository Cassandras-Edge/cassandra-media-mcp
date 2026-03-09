import { createMcpWorker } from "cassandra-mcp-auth";
import { registerMcpTools } from "./mcp-tools";

const { default: worker, McpAgentClass } = createMcpWorker<Env>({
  serviceId: "yt-mcp",
  name: "Cassandra YT MCP",
  version: "1.0.0",
  registerTools(server, env) {
    registerMcpTools(server, env);
  },
});

export { McpAgentClass as CassandraYtMCP };
export default worker;
