"""SiriusXM stream resolution.

Authenticates with the SXM API and resolves episode/channel URLs
into downloadable m3u8 streams with AES decryption keys.

Auth model:
  A single `sxm_refresh_token` JWT lives on the cassandra-auth service
  as a service-level credential. The backend trades it for a short-lived
  access token via POST /session/v1/sessions/refresh. The refresh
  endpoint rotates the refresh JWT on every call (Set-Cookie in the
  response), giving a rolling 90-day window — as long as the backend
  calls refresh at least once per 90 days, the window never expires.
  The backend writes the rotated refresh token back to the auth service
  so the next call picks up the latest.

Auth priority in _get_token:
  1. SXM_COOKIES_B64 env var — base64 Netscape cookie jar. Debug-only
     override that skips the live refresh flow (for local test/dev).
  2. Refresh token via cassandra-auth → POST /session/v1/sessions/refresh
     → access token. Production path.

To seed the refresh token (initial setup or when the 90-day window
actually lapses):
  1. Log into SXM in Firefox
  2. Extract the `sxm-refresh-token` cookie (DevTools → Storage, or
     `yt-dlp --cookies-from-browser firefox --cookies /tmp/sxm.txt ...`
     then `awk -F'\\t' '$6=="sxm-refresh-token"{print $7}' /tmp/sxm.txt`)
  3. curl -X POST $AUTH_URL/service-credentials/sxm \\
       -H "X-Auth-Secret: $AUTH_SECRET" \\
       -H "Content-Type: application/json" \\
       -d '{"sxm_refresh_token":"<jwt>"}'
"""

from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.edge-gateway.siriusxm.com"
_COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json; charset=utf-8",
    "Origin": "https://www.siriusxm.com",
    "Referer": "https://www.siriusxm.com/",
}

# Module-level token cache — one shared account, one shared session.
_cached_token: str | None = None
_token_expiry: float = 0.0
_TOKEN_TTL_SECONDS = 1800  # 30 min


@dataclass(slots=True)
class SxmStream:
    """Resolved SXM stream ready for yt-dlp."""

    m3u8_url: str
    hls_key_hex: str | None
    metadata: dict[str, object]


def is_sxm_url(url: str) -> bool:
    """Check if a URL is a SiriusXM player URL."""
    parsed = urlparse(url.strip())
    return parsed.netloc.lower().replace("www.", "") == "siriusxm.com"


def parse_sxm_url(url: str) -> tuple[str, str]:
    """Extract (entity_type, entity_id) from an SXM player URL.

    Supports:
      /player/episode-audio/entity/{uuid}
      /player/artist-station/{id}
      /channels/{slug}
    """
    parsed = urlparse(url.strip())
    parts = [p for p in parsed.path.strip("/").split("/") if p]

    # /player/<type>/entity/<id>
    if len(parts) >= 4 and parts[0] == "player" and parts[2] == "entity":
        return parts[1], parts[3]
    # /player/<type>/<id>
    if len(parts) >= 3 and parts[0] == "player":
        return parts[1], parts[2]
    # /channels/<slug>
    if len(parts) >= 2 and parts[0] == "channels":
        return "channel", parts[1]

    raise ValueError(f"Cannot parse SXM URL: {url}")


def _extract_token_from_cookies(cookies_b64: str) -> str | None:
    """Extract SXM access token from base64-encoded Netscape cookies.

    The AUTH_TOKEN cookie value is URL-encoded JSON containing
    {"session": {"accessToken": "..."}}.
    """
    try:
        raw = base64.b64decode(cookies_b64).decode("utf-8", errors="replace")
    except Exception:
        return None

    # Find AUTH_TOKEN value in Netscape cookie format (tab-separated)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "AUTH_TOKEN":
            try:
                decoded = unquote(parts[6])
                data = _json.loads(decoded)
                return data["session"]["accessToken"]
            except (KeyError, _json.JSONDecodeError, TypeError):
                continue
    return None


def _auth_service_endpoint() -> tuple[str, str]:
    """Return (auth_url, auth_secret) or raise if unconfigured."""
    auth_url = os.environ.get("AUTH_URL", "").strip()
    auth_secret = os.environ.get("AUTH_SECRET", "").strip()
    if not auth_url or not auth_secret:
        raise RuntimeError(
            "AUTH_URL and AUTH_SECRET must be set so the backend can "
            "reach the cassandra-auth service for SXM refresh tokens."
        )
    return auth_url.rstrip("/"), auth_secret


def _fetch_refresh_token_from_auth() -> str:
    """Read sxm_refresh_token from cassandra-auth's service credentials."""
    auth_url, auth_secret = _auth_service_endpoint()
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{auth_url}/service-credentials/sxm",
                headers={"X-Auth-Secret": auth_secret},
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"SXM refresh-token fetch from auth service failed: {exc}") from exc

    creds = (resp.json() or {}).get("credentials") or {}
    token = creds.get("sxm_refresh_token") if isinstance(creds, dict) else None
    token = (token or "").strip()
    if not token:
        raise RuntimeError(
            "sxm_refresh_token missing on auth service. Seed it with:\n"
            "  POST $AUTH_URL/service-credentials/sxm "
            "-H 'X-Auth-Secret: $AUTH_SECRET' "
            '-d \'{"sxm_refresh_token":"<jwt>"}\''
        )
    return token


def _store_refresh_token_to_auth(token: str) -> None:
    """Persist a rotated sxm_refresh_token back to cassandra-auth.

    Failures are logged but non-fatal — we still have a live access token
    for this process; the stale stored refresh is a next-call problem.
    """
    auth_url, auth_secret = _auth_service_endpoint()
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{auth_url}/service-credentials/sxm",
                headers={"X-Auth-Secret": auth_secret, "Content-Type": "application/json"},
                json={"sxm_refresh_token": token},
            )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to persist rotated SXM refresh token: %s", exc)


def _parse_set_cookie_refresh(set_cookie_header: str | None) -> str | None:
    """Pluck sxm-refresh-token=<value> out of a Set-Cookie header."""
    if not set_cookie_header:
        return None
    # httpx joins multiple Set-Cookie headers with comma-space. The token value
    # is a JWT (base64url + dots) so it won't contain commas or semicolons.
    for candidate in set_cookie_header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("sxm-refresh-token="):
            return candidate.split("=", 1)[1].split(";", 1)[0].strip()
    return None


def _refresh_access_token() -> str:
    """Exchange the stored refresh token for a fresh access token.

    Also captures the rotated refresh token from the response Set-Cookie
    header and writes it back to the auth service.
    """
    refresh_token = _fetch_refresh_token_from_auth()

    with httpx.Client(follow_redirects=False, timeout=30) as client:
        resp = client.post(
            f"{_API_BASE}/session/v1/sessions/refresh",
            headers={
                **_COMMON_HEADERS,
                "x-sxm-clock": "[0,1]",
                "Content-Type": "application/json",
                "Cookie": f"sxm-refresh-token={refresh_token}",
            },
            json={},
        )
    resp.raise_for_status()
    body = resp.json()
    access_token = body.get("accessToken")
    if not access_token:
        raise RuntimeError("SXM refresh response missing accessToken")

    # Capture rotated refresh token (rolling 90-day window)
    new_refresh = _parse_set_cookie_refresh(resp.headers.get("set-cookie"))
    if new_refresh and new_refresh != refresh_token:
        _store_refresh_token_to_auth(new_refresh)

    logger.info("SXM auth via refresh token")
    return access_token


def _get_token() -> str:
    """Get an SXM access token.

    Tries SXM_COOKIES_B64 env var first (debug override), falls through
    to the refresh-token flow against cassandra-auth. Caches the result
    for _TOKEN_TTL_SECONDS.
    """
    global _cached_token, _token_expiry  # noqa: PLW0603

    if _cached_token and time.monotonic() < _token_expiry:
        return _cached_token

    cookies_b64 = os.environ.get("SXM_COOKIES_B64", "").strip()
    if cookies_b64:
        token = _extract_token_from_cookies(cookies_b64)
        if token:
            logger.info("SXM auth via SXM_COOKIES_B64 (debug override)")
            _cached_token = token
            _token_expiry = time.monotonic() + _TOKEN_TTL_SECONDS
            return token
        logger.warning("SXM_COOKIES_B64 set but AUTH_TOKEN not found; falling through to refresh flow")

    token = _refresh_access_token()
    _cached_token = token
    _token_expiry = time.monotonic() + _TOKEN_TTL_SECONDS
    return token


def resolve(url: str) -> SxmStream:
    """Resolve an SXM URL into a downloadable stream.

    Returns the m3u8 URL, AES decryption key, and episode metadata
    suitable for feeding into yt-dlp.
    """
    entity_type, entity_id = parse_sxm_url(url)

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        token = _get_token()
        auth_headers = {
            **_COMMON_HEADERS,
            "Authorization": f"Bearer {token}",
            "x-sxm-clock": "[0,10]",
        }

        # Resolve stream
        r = client.post(f"{_API_BASE}/playback/play/v1/tuneSource",
                        json={"id": entity_id, "type": entity_type},
                        headers=auth_headers)
        r.raise_for_status()
        tune = r.json()

        stream = tune["streams"][0]
        primary = stream["urls"][0]
        m3u8_url = primary["url"]
        key_id = primary.get("encryptionKeyId")

        # Get decryption key
        hls_key_hex = None
        if key_id:
            auth_headers["x-sxm-clock"] = "[0,11]"
            r = client.get(f"{_API_BASE}/playback/key/v1/{key_id}",
                           headers=auth_headers)
            r.raise_for_status()
            key_b64 = r.json()["key"]
            hls_key_hex = base64.b64decode(key_b64).hex()

        # Extract metadata into yt-dlp-compatible shape
        aod = stream.get("metadata", {}).get("aod", {})
        episode = aod.get("episode", {})
        channel_name = aod.get("channelName", "")
        channel_num = aod.get("channelNumber")
        items = aod.get("items", [])

        metadata: dict[str, object] = {
            "id": entity_id,
            "title": episode.get("name") or entity_id,
            "description": episode.get("description"),
            "duration": (episode.get("duration") or 0) / 1000 if episode.get("duration") else None,
            "upload_date": _format_date(episode.get("startTimestamp")),
            "channel": f"{channel_name} ({channel_num})" if channel_num else channel_name,
            "uploader": episode.get("showName"),
            "extractor_key": "SiriusXM",
            "extractor": "SiriusXM",
            "webpage_url": url,
            "thumbnail": None,
        }

        return SxmStream(
            m3u8_url=m3u8_url,
            hls_key_hex=hls_key_hex,
            metadata=metadata,
        )


def _format_date(iso_str: str | None) -> str | None:
    """Convert ISO timestamp to YYYYMMDD format (yt-dlp convention)."""
    if not iso_str:
        return None
    try:
        return iso_str[:10].replace("-", "")
    except (TypeError, IndexError):
        return None
