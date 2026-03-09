# Cassandra YT MCP Worker

Public OAuth and MCP edge for `cassandra-yt-mcp`.

The Worker owns:

- OAuth 2.1 and DCR endpoints
- WorkOS login flow
- machine-to-machine JWT resolution
- MCP tools that proxy to the private backend API

## Required Secrets

- `WORKOS_CLIENT_ID`
- `WORKOS_CLIENT_SECRET`
- `COOKIE_ENCRYPTION_KEY`
- `BACKEND_BASE_URL`
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`
- optional `BACKEND_API_TOKEN`

## Commands

```bash
npm install
npm run type-check
npm test
npm run test:unit
npm run test:integration
npm run test:coverage
npm run deploy
```
