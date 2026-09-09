# YouTube setup from the dashboard

## One-time setup

1. In Google Cloud, create a desktop OAuth client with access to the YouTube Data API.
2. Download the OAuth client JSON.
3. In **Files & media**, choose it as **YouTube OAuth client JSON**.
4. In **Release**, select **Install YouTube support** when shown.

The dependency installation runs as a visible background task. Failures appear under Diagnostics.

## Dry run

Upload or select a final master, complete metadata, leave **Execute real upload** unchecked, and select **Build plan or upload**. No YouTube credentials, approval, or network upload is required by the harness for the plan.

## Real upload

A real upload requires:

- Final master approval upstream;
- completed Release evidence;
- final thumbnail;
- Publication approval;
- OAuth client JSON;
- installed YouTube support;
- **Execute real upload** explicitly checked.

The first real upload opens Google’s local OAuth consent flow. The resulting token is saved under `secrets/youtube-token.json`.

The dashboard supports private, unlisted, and public uploads. Scheduling requires private privacy at upload time. The final thumbnail and available `captions-en-GB.srt` are uploaded after the video. Subscriber notification is off unless explicitly selected.
