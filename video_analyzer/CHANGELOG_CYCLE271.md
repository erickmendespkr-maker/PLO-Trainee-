# Cycle 271 — reviewed subtitled batch MP4 export

Scope: offline recordings only. Export reviewer-selected intervals as MP4 with visible subtitles, hashes, SRT and JSON sidecar; no automatic poker decisions.

Local synthetic verification (2026-11-01): 12 unittest cases passed using FFmpeg 7.1.5 and FFprobe, including four-table clips, duplicate IDs, input hash mismatch, unsafe subtitle characters, time basis, failure rollback, and create-only output. A 1-second clip from a synthetic four-table video was generated and visually inspected with the subtitle rendered in the video. No poker accuracy is implied.

Input manifest uses `time_basis: playback_seconds`, not absolute source PTS. Reviewer approval is self-attested; equity/EV is not validated. A 3–5-minute authorized annotated PLO recording is still needed. No 40–60-minute performance test or Windows test was performed.

Next: integrate the reviewed clip manifest with verified hand boundaries, add full pipeline smoke tests with the original FFmpeg/Tesseract sampler, and benchmark long recordings.
