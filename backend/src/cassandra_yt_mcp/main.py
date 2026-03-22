from __future__ import annotations

import logging

from cassandra_yt_mcp.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

logger = logging.getLogger(__name__)


def cli() -> None:
    settings = load_settings()
    logger.info("Starting Cassandra YT MCP on port %d", settings.port)

    from cassandra_yt_mcp.mcp_server import create_mcp_server  # noqa: PLC0415

    mcp_server = create_mcp_server(settings)
    mcp_server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    cli()
