# Cycle 210 — offline session workspace and navigation

## Scope
Adds `offline_session_workspace.py` to open a previously exported, verified session ZIP into a **new local workspace**, with a static landing page linking to the verified clip gallery and the existing visual review interface. This is a navigation/packaging bridge, **not** automatic card/action recognition or strategic grading.

## Usage
From `video_analyzer/` (with `offline_visual_review_ui.html` in the same directory):

```bash
python offline_session_workspace.py open /path/to/session.zip /path/to/NEW_workspace
python offline_session_workspace.py verify /path/to/NEW_workspace
```

Open `NEW_workspace/index.html` manually in a browser. The source video is never included in the bundle or workspace. The HTML uses only local relative links; no web server is started.

## Safeguards
- Reuses the Cycle 209 verified ZIP opener before any extraction.
- Creates a private staging directory and checks its contents before publishing the new workspace directory.
- Rejects existing destinations, symlinked source HTML and modified/untracked session files.
- Records SHA-256 for review HTML, landing HTML and session manifest, then checks all session file hashes and regenerates the gallery to compare with its HTML.
- Explicitly retains `action_graded=false`, `source_video_included=false` and conditional-analysis counts.
- File hashes are integrity checks, not cryptographic signatures and not proof that poker observations or mathematical assumptions are correct.

## Evidence
- 15 new synthetic unit tests and 51 selected regression tests: **66/66 passed** on Linux using Python 3.13.
- Independently opened and verified the existing Cycle 208 synthetic demo ZIP: 1 clip, 1 conditional-analysis attachment, no original source video.
- The checked-in review HTML had the same Git blob SHA (`50219421738f18833ea55b8e4cd4c8ed8dc8a487`) as the local test copy.
- No GitHub Actions, credentials, production, main branch or spending changes.

## Not verified / blocker
- Browser playback via Windows `file://` and real PLO5/PLO6 video recognition are untested.
- Real hand reconstruction, OCR precision, 1080p/30 FPS and 40–60-minute sessions remain unvalidated.
- Need an authorized, annotated 3–5-minute sample to measure visual accuracy.
