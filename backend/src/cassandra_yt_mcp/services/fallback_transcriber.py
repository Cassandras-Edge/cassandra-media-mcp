from __future__ import annotations

import logging
from pathlib import Path

from cassandra_yt_mcp.metrics import fallback_total
from cassandra_yt_mcp.services.transcriber import UnsupportedLanguageError
from cassandra_yt_mcp.types import TranscriptResult

logger = logging.getLogger(__name__)


class LocalTranscriptionUnavailableError(RuntimeError):
    """Raised when local GPU transcription is disabled or dependencies are missing."""


class FallbackTranscriber:
    def __init__(
        self,
        *,
        local: object | None,
        fallback: object | None = None,
        enable_local: bool = True,
    ) -> None:
        self.local = local if enable_local else None
        self.fallback = fallback
        self.last_transcriber_used: str = "unknown"

    def transcribe(self, audio_path: Path) -> TranscriptResult:
        if self.local is not None:
            try:
                result = self.local.transcribe(audio_path)
                self.last_transcriber_used = "local"
                return result
            except UnsupportedLanguageError as exc:
                if self.fallback is None:
                    raise RuntimeError(
                        f"Detected unsupported language '{exc.language}' "
                        "but no ASSEMBLYAI_API_KEY configured for fallback"
                    ) from exc
                logger.info("Falling back to AssemblyAI for language '%s'", exc.language)
                fallback_total.labels(reason="unsupported_language").inc()
                self.last_transcriber_used = "assemblyai"
                return self.fallback.transcribe(audio_path)
            except (ImportError, OSError) as exc:
                logger.warning(
                    "Local GPU transcription failed (missing deps or CUDA): %s. "
                    "Attempting AssemblyAI fallback.",
                    exc,
                )
                if self.fallback is None:
                    raise LocalTranscriptionUnavailableError(
                        f"Local GPU transcription unavailable ({exc}) "
                        "and no ASSEMBLYAI_API_KEY configured for fallback"
                    ) from exc
                fallback_total.labels(reason="gpu_error").inc()
                self.last_transcriber_used = "assemblyai"
                return self.fallback.transcribe(audio_path)

        if self.fallback is None:
            raise LocalTranscriptionUnavailableError(
                "Local transcription is disabled (ENABLE_LOCAL_TRANSCRIPTION=false) "
                "and no ASSEMBLYAI_API_KEY configured for fallback"
            )
        logger.info("Local transcription disabled; using AssemblyAI")
        self.last_transcriber_used = "assemblyai"
        return self.fallback.transcribe(audio_path)
