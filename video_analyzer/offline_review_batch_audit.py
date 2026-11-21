"""Offline batch audit of exported MP4 review clips; never infer poker decisions."""
import argparse
import json
from pathlib import Path
from .offline_review_export_audit import audit_review_export

def audit_directory(directory, *, source=None):
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("invalid audit directory")
    results = []
    for clip in sorted(root.glob("*.mp4")):
        try:
            audit = audit_review_export(clip, source=source)
            results.append({"clip": clip.name, "ok": True,
                            "integrity_verified": audit["integrity_verified"],
                            "source_checked": audit["source_checked"]})
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            results.append({"clip": clip.name, "ok": False,
                            "error_type": type(exc).__name__})
    return {"schema_version": 1, "total": len(results),
            "passed": sum(item["ok"] for item in results),
            "failed": sum(not item["ok"] for item in results),
            "results": results}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit_directory(args.directory, source=args.source)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["total"] and not report["failed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
