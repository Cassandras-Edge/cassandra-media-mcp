import { backendPost } from "./backend";

/**
 * Cron handler: iterate MCP_KEYS, find yt-mcp keys with youtube_cookies,
 * and trigger a watch-later sync for each.
 */
export async function syncWatchLaterForAllKeys(env: Env): Promise<void> {
  const keys = await env.MCP_KEYS.list();

  for (const key of keys.keys) {
    if (!key.name.startsWith("mcp_")) continue;

    const raw = await env.MCP_KEYS.get(key.name);
    if (!raw) continue;

    let meta: Record<string, unknown>;
    try {
      meta = JSON.parse(raw);
    } catch {
      continue;
    }

    if (meta.service !== "yt-mcp") continue;

    const credentials = meta.credentials as Record<string, string> | undefined;
    const cookies = credentials?.youtube_cookies;
    if (!cookies) continue;

    const userId = (meta.created_by as string) || key.name;

    try {
      await backendPost(env, "/api/watch-later/sync", {
        user_id: userId,
        cookies_b64: cookies,
      });
      console.log(`Watch later sync completed for ${userId}`);
    } catch (err) {
      console.error(`Watch later sync failed for ${userId}:`, err);
    }
  }
}
