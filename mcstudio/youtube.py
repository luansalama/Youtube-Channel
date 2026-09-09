from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .core import StudioError

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def build_request(metadata: dict[str, Any], privacy: str, publish_at: str | None = None) -> dict[str, Any]:
    if privacy not in {"private", "unlisted", "public"}:
        raise StudioError("privacy must be private, unlisted, or public")
    snippet = {
        "title": metadata["title"],
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "categoryId": str(metadata.get("category_id", "20")),
        "defaultLanguage": metadata.get("default_language", "en-GB"),
    }
    status: dict[str, Any] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False)),
        "containsSyntheticMedia": bool(metadata.get("contains_synthetic_media", False)),
    }
    if publish_at:
        if privacy != "private":
            raise StudioError("Scheduled publish_at requires privacy=private.")
        status["publishAt"] = publish_at
    return {"snippet": snippet, "status": status}


def upload(
    video_file: Path,
    metadata_file: Path,
    client_secrets: Path,
    token_file: Path,
    privacy: str,
    publish_at: str | None,
    execute: bool,
    thumbnail_file: Path | None = None,
    captions_file: Path | None = None,
    notify_subscribers: bool = False,
) -> dict[str, Any]:
    if not video_file.is_file():
        raise StudioError(f"Video file not found: {video_file}")
    if not metadata_file.is_file():
        raise StudioError(f"Metadata file not found: {metadata_file}")
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    request_body = build_request(metadata, privacy, publish_at)
    plan = {
        "video_file": str(video_file.resolve()),
        "metadata_file": str(metadata_file.resolve()),
        "request_body": request_body,
        "execute": execute,
        "thumbnail_file": str(thumbnail_file.resolve()) if thumbnail_file and thumbnail_file.is_file() else "",
        "captions_file": str(captions_file.resolve()) if captions_file and captions_file.is_file() else "",
        "notify_subscribers": bool(notify_subscribers),
    }
    if not execute:
        return plan
    if not client_secrets.is_file():
        raise StudioError(f"OAuth client secrets file not found: {client_secrets}")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise StudioError("Install the optional YouTube dependencies: pip install -e '.[youtube]'") from exc

    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
            credentials = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    service = build("youtube", "v3", credentials=credentials)
    media = MediaFileUpload(str(video_file), chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=request_body, media_body=media, notifySubscribers=bool(notify_subscribers))
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    plan["response"] = response
    video_id = response.get("id") if isinstance(response, dict) else None
    post_upload: dict[str, Any] = {}
    if video_id and thumbnail_file and thumbnail_file.is_file():
        thumb_media = MediaFileUpload(str(thumbnail_file), resumable=False)
        post_upload["thumbnail"] = service.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
    if video_id and captions_file and captions_file.is_file():
        caption_media = MediaFileUpload(str(captions_file), mimetype="application/octet-stream", resumable=False)
        caption_body = {"snippet": {"videoId": video_id, "language": "en-GB", "name": "English (UK)", "isDraft": False}}
        post_upload["captions"] = service.captions().insert(part="snippet", body=caption_body, media_body=caption_media).execute()
    if post_upload:
        plan["post_upload"] = post_upload
    return plan


def standalone_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe YouTube uploader. Dry-run unless --execute is supplied.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--client-secrets", type=Path, default=Path(os.environ.get("YOUTUBE_CLIENT_SECRETS", "secrets/client_secrets.json")))
    parser.add_argument("--token", type=Path, default=Path(os.environ.get("YOUTUBE_TOKEN_FILE", "secrets/youtube-token.json")))
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--publish-at", help="RFC3339 timestamp; requires --privacy private")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--thumbnail", type=Path)
    parser.add_argument("--captions", type=Path)
    parser.add_argument("--notify-subscribers", action="store_true")
    args = parser.parse_args(argv)
    result = upload(args.video, args.metadata, args.client_secrets, args.token, args.privacy, args.publish_at, args.execute, args.thumbnail, args.captions, args.notify_subscribers)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0
