# Cycle 53 — Visual confirmation of offline table regions

`activity_clip_region_preview.py` extracts **one approximate frame** from an existing local MP4/WebM recording using FFmpeg. It SHA-256-checks the recording before and after extraction, limits the JPEG to 2 MiB, and returns a provenance-tagged base64 payload. The renderer in `activity_clip_selection_editor.py` validates the JPEG digest and video SHA binding, embeds the JPEG directly in a standalone HTML page, and draws dynamic region overlays when coordinates change.

Generate a self-contained editor (the video is read locally and never uploaded):

```sh
python video_analyzer/activity_clip_selection_editor.py \
  unapproved_selection_template.json region_editor.html \
  --video session.mp4 --timestamp 30
```

The selection template must be generated from the matching review queue/draft and video SHA-256. Open `region_editor.html` in a browser. Change each rectangle's x/y/width/height in **source-video pixels** while watching the overlays; check the manual-confirmation box only after inspecting the video; select reviewed decisions and export JSON. Feed the JSON into the existing Python validator and FFmpeg clip exporter, which enforce non-overlap, bounds, identity and human approval. No automatic approval, OCR accuracy claim, equity, EV or mistake classification is implied.

**Limitations:** FFmpeg fast seek can return a nearby decoded frame rather than the exact requested PTS. A single screenshot cannot validate that regions remain fixed throughout the recording or show all hands. The HTML includes an embedded full-frame JPEG which may expose player names or other private content if shared. It has no external scripts or network calls, but treat it as sensitive local material. Keep the original video and the JSON queue/draft private. An image hash verifies bytes, not poker facts.

Synthetic tests use four table regions in a generated 160×120 MP4. They test JPEG extraction, recording hash mismatch, schema tampering, timestamps, and browser interaction; they do not measure performance on real poker footage.
