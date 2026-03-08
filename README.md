# Cassandra YT MCP

`cassandra-yt-mcp` is the Cassandra-native rewrite of the old `yt-dlp-mcp`.

It is intentionally split into three ownership layers:

- `backend/` - private HTTP API for jobs, transcript storage, and yt-dlp/transcription runtime
- `worker/` - public Cloudflare Worker MCP + OAuth edge using the same WorkOS pattern as `fast-mcp-test`
- `infra/` - service-owned Terraform modules that `cassandra-infra` composes into environments

## Deployment Topology

```text
MCP client
  -> yt-mcp.<domain> (Cloudflare Worker)
  -> WorkOS OAuth / M2M token resolution
  -> yt-mcp-api.<domain> (Cloudflare Tunnel + Access)
  -> cassandra-yt-mcp backend in Kubernetes
  -> SQLite + PVC transcript store
```

## Repo Layout

```text
cassandra-yt-mcp/
├── backend/        # Private backend API, worker loop, tests, Docker image
├── worker/         # Public MCP/OAuth Cloudflare Worker
├── infra/          # Service-owned Terraform modules
└── .github/        # CI/CD for the standalone service repo
```

## Responsibilities

- `cassandra-yt-mcp` defines the service contract and Cloudflare module shape.
- `cassandra-infra` instantiates the Cloudflare modules per environment.
- `cassandra-k8s` deploys the backend and tunnel connector into the cluster.

## Image Publishing

The backend image is published to GHCR from the `Deploy` workflow as:

- `ghcr.io/digibugcat/cassandra-yt-mcp/backend:latest`
- `ghcr.io/digibugcat/cassandra-yt-mcp/backend:<git-sha>`

The backend Docker image installs Python packages into `/opt/venv` so it can build cleanly on Ubuntu-based CUDA images without tripping Debian's externally managed Python guardrails.

If the GHCR package remains private, set `image.pullSecrets` in the Helm values and create the matching Kubernetes registry secret in the `cassandra-yt-mcp` namespace.
