import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cassandra_yt_mcp.services.sxm import (
    SxmStream,
    _extract_token_from_cookies,
    is_sxm_url,
    parse_sxm_url,
)


def test_is_sxm_url() -> None:
    assert is_sxm_url("https://www.siriusxm.com/player/episode-audio/entity/abc") is True
    assert is_sxm_url("https://siriusxm.com/channels/hits1") is True
    assert is_sxm_url("https://youtube.com/watch?v=abc") is False
    assert is_sxm_url("https://example.com") is False


def test_parse_sxm_episode_url() -> None:
    url = "https://www.siriusxm.com/player/episode-audio/entity/0ab84830-b93d-8bbd"
    entity_type, entity_id = parse_sxm_url(url)
    assert entity_type == "episode-audio"
    assert entity_id == "0ab84830-b93d-8bbd"


def test_parse_sxm_artist_station() -> None:
    url = "https://www.siriusxm.com/player/artist-station/coldplay123"
    entity_type, entity_id = parse_sxm_url(url)
    assert entity_type == "artist-station"
    assert entity_id == "coldplay123"


def test_parse_sxm_channel() -> None:
    url = "https://www.siriusxm.com/channels/hits1"
    entity_type, entity_id = parse_sxm_url(url)
    assert entity_type == "channel"
    assert entity_id == "hits1"


def test_parse_sxm_invalid_url() -> None:
    with pytest.raises(ValueError, match="Cannot parse SXM URL"):
        parse_sxm_url("https://www.siriusxm.com/")


def test_extract_token_from_cookies() -> None:
    """Extract bearer token from Netscape cookie file containing AUTH_TOKEN."""
    from urllib.parse import quote
    auth_data = json.dumps({"session": {"accessToken": "test-bearer-token-123"}})
    cookie_line = f".siriusxm.com\tTRUE\t/\tTRUE\t0\tAUTH_TOKEN\t{quote(auth_data)}"
    cookies_content = f"# Netscape HTTP Cookie File\n{cookie_line}\n"
    cookies_b64 = base64.b64encode(cookies_content.encode()).decode()

    token = _extract_token_from_cookies(cookies_b64)
    assert token == "test-bearer-token-123"


def test_extract_token_from_cookies_missing() -> None:
    """Return None when AUTH_TOKEN cookie is not present."""
    cookies_content = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tother\tvalue\n"
    cookies_b64 = base64.b64encode(cookies_content.encode()).decode()

    token = _extract_token_from_cookies(cookies_b64)
    assert token is None


def test_extract_token_from_cookies_invalid_b64() -> None:
    """Return None for garbage input."""
    assert _extract_token_from_cookies("not-valid-base64!!!") is None


def test_downloader_routes_sxm_url(tmp_path: Path) -> None:
    """SXM URLs should go through _download_sxm, not _download_ytdlp."""
    from cassandra_yt_mcp.services.downloader import Downloader

    downloader = Downloader(tmp_path)

    fake_stream = SxmStream(
        m3u8_url="https://aod.streaming.siriusxm.com/test.m3u8",
        hls_key_hex="abcdef0123456789",
        metadata={
            "id": "test-episode-id",
            "title": "Test Episode",
            "extractor_key": "SiriusXM",
            "channel": "Test Channel",
        },
    )

    # Create a fake audio file that yt-dlp would produce
    job_dir = tmp_path / "test-job"
    job_dir.mkdir()
    fake_audio = job_dir / "test-episode-id.m4a"
    fake_audio.write_bytes(b"\x00" * 100)

    fake_ytdlp_json = json.dumps({"id": "test-episode-id", "title": "Test Episode"})

    with (
        patch("cassandra_yt_mcp.services.downloader.resolve_sxm", return_value=fake_stream) as mock_resolve,
        patch.object(Downloader, "_run_with_progress", return_value=(fake_ytdlp_json, "", 0)) as mock_run,
        patch("cassandra_yt_mcp.services.downloader.subprocess.run") as mock_ffmpeg,
    ):
        mock_ffmpeg.return_value.returncode = 0
        mock_ffmpeg.return_value.stderr = b""

        result = downloader.download(
            url="https://www.siriusxm.com/player/episode-audio/entity/test-episode-id",
            job_id="test-job",
        )

    mock_resolve.assert_called_once()
    ytdlp_call_args = mock_run.call_args_list[0][0][0]
    assert "https://aod.streaming.siriusxm.com/test.m3u8" in ytdlp_call_args
    assert "--extractor-args" in ytdlp_call_args
    assert "generic:hls_key=abcdef0123456789" in ytdlp_call_args
    assert result.metadata["extractor_key"] == "SiriusXM"


def test_downloader_does_not_route_youtube_to_sxm(tmp_path: Path) -> None:
    """YouTube URLs should NOT go through the SXM path."""
    from cassandra_yt_mcp.services.downloader import Downloader

    downloader = Downloader(tmp_path)

    job_dir = tmp_path / "yt-job"
    job_dir.mkdir()
    fake_audio = job_dir / "abc123.m4a"
    fake_audio.write_bytes(b"\x00" * 100)

    fake_ytdlp_json = json.dumps({"id": "abc123", "title": "YT Video"})

    with (
        patch("cassandra_yt_mcp.services.downloader.resolve_sxm") as mock_resolve,
        patch.object(Downloader, "_run_with_progress", return_value=(fake_ytdlp_json, "", 0)),
        patch("cassandra_yt_mcp.services.downloader.subprocess.run") as mock_ffmpeg,
    ):
        mock_ffmpeg.return_value.returncode = 0
        mock_ffmpeg.return_value.stderr = b""

        downloader.download(
            url="https://youtube.com/watch?v=abc123",
            job_id="yt-job",
        )

    mock_resolve.assert_not_called()
