from pathlib import Path

from fastapi.testclient import TestClient

from cassandra_yt_mcp.api.app import create_app
from cassandra_yt_mcp.config import Settings
from cassandra_yt_mcp.db.database import Database
from cassandra_yt_mcp.db.transcripts import TranscriptsRepository


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=3000,
        poll_interval_seconds=5,
        data_dir=tmp_path,
        database_path=tmp_path / "test.sqlite3",
        assemblyai_api_key=None,
        huggingface_token=None,
        max_workers=1,
        backend_api_token="secret-token",
        enable_local_transcription=False,
        role="standalone",
        gpu_workers=[],
        worker_port=3001,
    )


def test_health_route(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["ok"] is True


def test_api_token_required(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get("/api/transcripts")
        assert response.status_code == 401


def test_read_transcript_route(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    db = Database(settings.database_path)
    repo = TranscriptsRepository(db)
    transcript_dir = tmp_path / "transcripts" / "youtube" / "demo" / "vid1"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "transcript.md").write_text("# Demo\n", encoding="utf-8")
    (transcript_dir / "transcript.txt").write_text("Demo\n", encoding="utf-8")
    (transcript_dir / "transcript.json").write_text('{"segments":[{"text":"Demo"}]}', encoding="utf-8")
    repo.upsert(
        video_id="vid1",
        normalized_url="https://youtube.com/watch?v=vid1",
        url="https://youtube.com/watch?v=vid1",
        path=str(transcript_dir),
        transcript_text="Demo",
        title="Demo",
        channel="Channel",
        platform="youtube",
        duration=None,
        upload_date=None,
        description=None,
        thumbnail=None,
        view_count=None,
        speaker_count=None,
        word_count=1,
        confidence=None,
    )
    db.close()

    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/transcripts/vid1",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 200
        assert response.json()["video_id"] == "vid1"
