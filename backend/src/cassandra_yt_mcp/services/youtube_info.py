from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class YouTubeInfoService:
    def __init__(self, *, cookies_file: Path | None = None) -> None:
        self.cookies_file = cookies_file

    _METADATA_KEYS = [
        "id",
        "title",
        "description",
        "channel",
        "channel_id",
        "channel_url",
        "uploader",
        "upload_date",
        "duration",
        "view_count",
        "like_count",
        "comment_count",
        "age_limit",
        "categories",
        "tags",
        "thumbnail",
        "webpage_url",
        "original_url",
        "language",
        "subtitles",
    ]

    def _run_ytdlp(self, cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if self.cookies_file:
            cmd = [*cmd, "--cookies", str(self.cookies_file)]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"yt-dlp timed out after {timeout} seconds") from exc
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "yt-dlp failed")
        return completed

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        completed = self._run_ytdlp(
            [
                "yt-dlp",
                f"ytsearch{limit}:{query}",
                "--print",
                "%(id)s\t%(title)s\t%(uploader)s\t%(duration)s\t%(view_count)s",
                "--no-download",
                "--no-warnings",
                "--quiet",
            ]
        )
        results: list[dict[str, Any]] = []
        for line in completed.stdout.strip().splitlines():
            parts = line.split("\t", 4)
            if len(parts) < 5:
                continue
            video_id, title, channel, duration, view_count = parts
            results.append(
                {
                    "video_id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "channel": channel,
                    "duration": _safe_int(duration),
                    "view_count": _safe_int(view_count),
                }
            )
        return results

    def get_metadata(self, url: str) -> dict[str, Any]:
        completed = self._run_ytdlp(
            ["yt-dlp", "--dump-json", "--no-warnings", "--no-download", "--no-playlist", url]
        )
        raw = json.loads(completed.stdout)
        return {key: raw[key] for key in self._METADATA_KEYS if key in raw}

    def get_comments(self, url: str, limit: int = 20, sort: str = "top") -> list[dict[str, Any]]:
        completed = self._run_ytdlp(
            [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--skip-download",
                "--no-playlist",
                "--write-comments",
                "--extractor-args",
                f"youtube:comment_sort={sort};max_comments={limit},all,all",
                url,
            ],
            timeout=120,
        )
        data = json.loads(completed.stdout)
        comments: list[dict[str, Any]] = []
        for item in data.get("comments") or []:
            comments.append(
                {
                    "id": item.get("id"),
                    "text": item.get("text"),
                    "author": item.get("author"),
                    "author_id": item.get("author_id"),
                    "like_count": item.get("like_count", 0),
                    "is_pinned": item.get("is_pinned", False),
                    "is_favorited": item.get("is_favorited", False),
                    "parent": item.get("parent", "root"),
                    "timestamp": item.get("timestamp"),
                }
            )
        return comments


def _safe_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
