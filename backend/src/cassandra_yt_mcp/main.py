from __future__ import annotations

import logging

import uvicorn

from cassandra_yt_mcp.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

logger = logging.getLogger(__name__)


def app():
    from cassandra_yt_mcp.api.app import create_app  # noqa: PLC0415

    return create_app(load_settings())


def worker_app():
    from cassandra_yt_mcp.worker_server import create_worker_app  # noqa: PLC0415

    return create_worker_app(load_settings())


def downloader_app():
    from cassandra_yt_mcp.downloader_server import create_downloader_app  # noqa: PLC0415

    return create_downloader_app(load_settings())


def mcp_app():
    from cassandra_yt_mcp.mcp_server import create_mcp_server  # noqa: PLC0415

    return create_mcp_server(load_settings())


def cli() -> None:
    settings = load_settings()

    if settings.role == "mcp":
        logger.info("Starting in MCP mode on port %d", settings.mcp_port)
        mcp_server = mcp_app()
        mcp_server.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.mcp_port,
        )
    elif settings.role == "worker":
        logger.info("Starting in WORKER mode on port %d", settings.worker_port)
        uvicorn.run(
            "cassandra_yt_mcp.main:worker_app",
            host=settings.host,
            port=settings.worker_port,
            factory=True,
            reload=False,
        )
    elif settings.role == "downloader":
        logger.info("Starting in DOWNLOADER mode on port %d", settings.downloader_port)
        uvicorn.run(
            "cassandra_yt_mcp.main:downloader_app",
            host=settings.host,
            port=settings.downloader_port,
            factory=True,
            reload=False,
        )
    else:
        logger.info("Starting in %s mode on port %d", settings.role.upper(), settings.port)
        uvicorn.run(
            "cassandra_yt_mcp.main:app",
            host=settings.host,
            port=settings.port,
            factory=True,
            reload=False,
        )


if __name__ == "__main__":
    cli()
