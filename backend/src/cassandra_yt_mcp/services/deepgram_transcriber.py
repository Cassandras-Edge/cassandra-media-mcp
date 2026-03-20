"""Deepgram pre-recorded transcription with diarization."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from cassandra_yt_mcp.types import TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.deepgram.com/v1/listen"


class DeepgramTranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        timeout_seconds: float = 600.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.last_transcriber_used: str = "deepgram"

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        content_type = _content_type(audio_path)
        params = {
            "model": self.model,
            "diarize": "true",
            "utterances": "true",
            "punctuate": "true",
            "smart_format": "true",
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            with audio_path.open("rb") as f:
                resp = client.post(
                    _BASE_URL,
                    params=params,
                    headers={
                        "Authorization": f"Token {self.api_key}",
                        "Content-Type": content_type,
                    },
                    content=f,
                )

        if resp.status_code >= 400:
            raise RuntimeError(f"Deepgram failed ({resp.status_code}): {resp.text[:400]}")

        data = resp.json()
        results = data.get("results", {})

        # Extract full transcript
        channels = results.get("channels", [])
        transcript = ""
        if channels:
            alts = channels[0].get("alternatives", [])
            if alts:
                transcript = alts[0].get("transcript", "")

        # Extract utterances with speaker labels
        utterances = results.get("utterances", [])
        segments = [
            TranscriptSegment(
                start=u["start"],
                end=u["end"],
                text=u["transcript"],
                speaker=f"SPEAKER_{u['speaker']:02d}" if "speaker" in u else None,
            )
            for u in utterances
            if u.get("transcript", "").strip()
        ]

        # Fallback: if no utterances, build segments from words
        if not segments and channels:
            alts = channels[0].get("alternatives", [])
            if alts:
                segments = _segments_from_words(alts[0].get("words", []))

        language = results.get("metadata", {}).get("language") or "en"

        return TranscriptResult(
            text=transcript,
            segments=segments,
            language=language,
        )


def _segments_from_words(words: list[dict]) -> list[TranscriptSegment]:
    """Group words by speaker into segments."""
    if not words:
        return []

    segments: list[TranscriptSegment] = []
    current_speaker = words[0].get("speaker", 0)
    current_words: list[str] = []
    seg_start = words[0].get("start", 0.0)
    seg_end = words[0].get("end", 0.0)

    for w in words:
        speaker = w.get("speaker", 0)
        if speaker != current_speaker:
            if current_words:
                segments.append(TranscriptSegment(
                    start=seg_start,
                    end=seg_end,
                    text=" ".join(current_words),
                    speaker=f"SPEAKER_{current_speaker:02d}",
                ))
            current_speaker = speaker
            current_words = []
            seg_start = w.get("start", 0.0)

        current_words.append(w.get("word", ""))
        seg_end = w.get("end", 0.0)

    if current_words:
        segments.append(TranscriptSegment(
            start=seg_start,
            end=seg_end,
            text=" ".join(current_words),
            speaker=f"SPEAKER_{current_speaker:02d}",
        ))

    return segments


def _content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
    }.get(ext, "audio/wav")
