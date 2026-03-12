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
        download_concurrency=2,
        downloader_port=3002,
        ytdlp_cookies=None,
        ytdlp_cookies_file=None,
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


def test_api_token_rejects_wrong_value(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get(
            "/api/transcripts",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401


def test_api_token_accepts_correct_value(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get(
            "/api/transcripts",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert response.status_code == 200
        assert response.json() == {"count": 0, "items": []}


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


def test_read_transcript_auto_transcribes_when_not_found(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        response = client.get(
            "/api/transcripts/missing-video",
            headers={"Authorization": "Bearer secret-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auto_transcribe"] is True
        assert data["video_id"] == "missing-video"
        assert "transcription" in data
        assert data["transcription"]["status"] == "queued"


def test_read_transcript_route_paginates_text_and_json_with_warnings(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    db = Database(settings.database_path)
    repo = TranscriptsRepository(db)
    transcript_dir = tmp_path / "transcripts" / "youtube" / "demo" / "vid2"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "transcript.md").write_text("# Demo\nline 1\nline 2\nline 3\n", encoding="utf-8")
    (transcript_dir / "transcript.txt").write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    (transcript_dir / "transcript.json").write_text(
        '{"segments":[{"text":"one"},{"text":"two"},{"text":"three"}]}',
        encoding="utf-8",
    )
    repo.upsert(
        video_id="vid2",
        normalized_url="https://youtube.com/watch?v=vid2",
        url="https://youtube.com/watch?v=vid2",
        path=str(transcript_dir),
        transcript_text="line 1 line 2 line 3",
        title="Demo",
        channel="Channel",
        platform="youtube",
        duration=None,
        upload_date=None,
        description=None,
        thumbnail=None,
        view_count=None,
        speaker_count=2,
        word_count=3,
        confidence=0.61,
    )
    db.close()

    with TestClient(create_app(settings)) as client:
        text_response = client.get(
            "/api/transcripts/vid2?format=text&offset=1&limit=1",
            headers={"Authorization": "Bearer secret-token"},
        )
        json_response = client.get(
            "/api/transcripts/vid2?format=json&offset=1&limit=1",
            headers={"Authorization": "Bearer secret-token"},
        )

        assert text_response.status_code == 200
        assert text_response.json()["content"] == "line 2\n"
        assert text_response.json()["lines_returned"] == 1
        assert text_response.json()["total_lines"] == 3
        assert any("Speaker diarization detected 2 speakers" in warning for warning in text_response.json()["warnings"])
        assert any("Low confidence score (61%)" in warning for warning in text_response.json()["warnings"])

        assert json_response.status_code == 200
        assert json_response.json()["content"] == [{"text": "two"}]
        assert json_response.json()["segments_returned"] == 1
        assert json_response.json()["total_segments"] == 3


def test_youtube_route_errors_are_shaped(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as client:
        runtime = client.app.state.runtime

        def raise_search(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("search unavailable")

        def raise_metadata(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("metadata unavailable")

        def raise_comments(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("comments unavailable")

        runtime.youtube_info.search = raise_search
        runtime.youtube_info.get_metadata = raise_metadata
        runtime.youtube_info.get_comments = raise_comments

        search_response = client.get(
            "/api/youtube/search?query=test",
            headers={"Authorization": "Bearer secret-token"},
        )
        metadata_response = client.get(
            "/api/youtube/metadata?url=https://youtu.be/demo",
            headers={"Authorization": "Bearer secret-token"},
        )
        comments_response = client.get(
            "/api/youtube/comments?url=https://youtu.be/demo",
            headers={"Authorization": "Bearer secret-token"},
        )

        assert search_response.status_code == 200
        assert search_response.json() == {
            "error": "search_failed",
            "message": "search unavailable",
        }
        assert metadata_response.json() == {
            "error": "metadata_failed",
            "message": "metadata unavailable",
        }
        assert comments_response.json() == {
            "error": "comments_failed",
            "message": "comments unavailable",
        }
