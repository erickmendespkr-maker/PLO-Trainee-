"""Export conservative review-only JSON for offline recorded sessions."""
import argparse
import json
import os
from pathlib import Path


def export_review_report(handoff, journal):
    if not isinstance(handoff, dict) or not isinstance(journal, dict):
        raise ValueError("invalid inputs")
    if handoff.get("source") != "offline_recorded_video" or journal.get("source") != "offline_recorded_video":
        raise ValueError("invalid source")
    if handoff.get("video_sha256") != journal.get("video_sha256"):
        raise ValueError("video mismatch")
    if handoff.get("equity_or_ev_computed") is not False or handoff.get("mp4_exported") is not False:
        raise ValueError("unsupported claims")
    tasks, entries = handoff.get("tasks"), journal.get("entries")
    if not isinstance(tasks, list) or not isinstance(entries, list):
        raise ValueError("invalid tasks")
    task_by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or task.get("review_status") != "PENDING" or task.get("strategic_commentary_allowed") is not False:
            raise ValueError("untrusted task")
        rid = task.get("review_id")
        if not isinstance(rid, str) or rid in task_by_id:
            raise ValueError("duplicate or invalid task")
        task_by_id[rid] = task
    if len(entries) != len(tasks):
        raise ValueError("entry count mismatch")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid entry")
        rid = entry.get("review_id")
        if rid not in task_by_id or rid in seen:
            raise ValueError("entry mismatch")
        seen.add(rid)
        if entry.get("evidence") != task_by_id[rid].get("evidence"):
            raise ValueError("evidence mismatch")
        if entry.get("strategic_commentary_allowed") is not False or entry.get("equity_or_ev_computed") is not False:
            raise ValueError("unsupported strategic claim")
        if not isinstance(entry.get("decision"), dict) or entry["decision"].get("status") not in ("PENDING", "NEEDS_CORRECTION", "REJECTED", "REVIEWED"):
            raise ValueError("invalid decision")
    return {
        "schema_version": 1, "source": "offline_recorded_video",
        "video_sha256": handoff["video_sha256"],
        "journal_sha256": journal.get("journal_sha256"),
        "review_count": len(entries),
        "reviewed_count": sum(e["decision"]["status"] == "REVIEWED" for e in entries),
        "hands_confirmed": 0, "equity_or_ev_computed": False,
        "mp4_exported": False, "strategic_commentary_allowed": False,
        "status": "REVIEW_ONLY_INSUFFICIENT_DATA", "entries": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export offline review-only report")
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.resolve() in (args.handoff.resolve(), args.journal.resolve()):
        parser.error("output must differ from inputs")
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    journal = json.loads(args.journal.read_text(encoding="utf-8"))
    report = export_review_report(handoff, journal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    try:
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, args.output)
    finally:
        temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
