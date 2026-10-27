"""Build a conservative offline human-review queue from existing PLO reports.

Consumes *reports*, never poker clients or live data. Priority is a deterministic
triage heuristic, NOT a probability of error, equity, EV or evidence of a bad play.
Neither crop hashes nor an optional temporal audit certify cards or actions.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_JSON = 2 * 1024 * 1024
MAX_HTML = 2 * 1024 * 1024
MAX_HANDS = 200
SHA = re.compile(r"[0-9a-f]{64}\Z")
STREETS = {"preflop", "flop", "turn", "river"}
TAIL_STATUS = "terminal_sequence_diagnostic_only"
CLEAN_TAIL = "no_anomaly_detected_in_compared_tail"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def strict_object_pairs(pairs):
    data = {}
    for k, v in pairs:
        require(k not in data, "Duplicate JSON key")
        data[k] = v
    return data


def invalid_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def safe_name(name: str) -> str:
    require(type(name) is str and 1 <= len(name) <= 180 and
            name not in (".", "..") and name == Path(name).name and
            not any(c in name for c in ("/", "\\", "\x00")) and
            name.lower().endswith(".json"), "Unsafe report filename")
    return name


def read_report(root: Path, name: str) -> tuple[dict, str]:
    path = root / safe_name(name)
    require(path.is_file() and not path.is_symlink(), "Unsafe report file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_JSON,
                "Invalid report size/type")
        raw = stream.read(MAX_JSON + 1)
        after = os.fstat(stream.fileno())
        require(0 < len(raw) <= MAX_JSON and
                (before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino),
                "Report changed while reading")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object_pairs,
                      parse_constant=invalid_constant)
    require(type(data) is dict, "Report must be a JSON object")
    return data, hashlib.sha256(raw).hexdigest()


def digest(value, name):
    require(type(value) is str and SHA.fullmatch(value) is not None, f"Invalid {name}")
    return value


def finite_unit(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
            f"Invalid {name}")
    return float(value)


def pts(value, name):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400,
            f"Invalid {name}")
    return float(value)


def analyze_hand(ledger: dict, evidence: dict, tail: dict | None = None) -> dict:
    """Validate a single hand's *claimed* metadata and return a review-only summary."""
    require(type(ledger) is dict and
            ledger.get("status") == "conditional_observation_ledger_not_video_verified" and
            type(ledger.get("schema_version")) is int and ledger["schema_version"] == 1 and
            ledger.get("variant") in ("PLO5", "PLO6") and
            type(ledger.get("table_id")) is int and 1 <= ledger["table_id"] <= 4 and
            type(ledger.get("hand_label")) is str and 0 < len(ledger["hand_label"]) <= 64 and
            ledger.get("video_evidence_verified") is False and
            ledger.get("ready_for_equity_or_ev") is False and
            ledger.get("automatic_clip_selection_authorized") is False and
            type(ledger.get("events")) is list and len(ledger["events"]) <= 500 and
            type(ledger.get("review_flags")) is list,
            "Unsupported or overclaiming ledger")
    digest(ledger.get("input_canonical_sha256"), "ledger canonical digest")
    require(type(evidence) is dict and evidence.get("schema_version") == 1 and
            evidence.get("status") == "crop_hashes_verified_recording_and_visual_truth_unverified" and
            evidence.get("variant") == ledger["variant"] and
            evidence.get("table_id") == ledger["table_id"] and
            evidence.get("hand_label") == ledger["hand_label"] and
            evidence.get("ledger_input_canonical_sha256") == ledger["input_canonical_sha256"] and
            evidence.get("video_evidence_verified") is False and
            evidence.get("ocr_accuracy_verified") is False and
            evidence.get("ready_for_equity_or_ev") is False and
            evidence.get("automatic_clip_selection_authorized") is False and
            type(evidence.get("linked_observations")) is list and
            type(evidence.get("unlinked_event_indices")) is list,
            "Evidence/ledger mismatch or unsupported verification claim")
    source_sha = digest(evidence.get("source_recording_sha256_claim_unverified"),
                        "claimed source SHA")
    duration = pts(evidence.get("source_duration_seconds_claim_unverified"), "claimed duration")
    require(duration > 0, "Invalid claimed source duration")
    rows = ledger["events"]
    require(type(evidence.get("ledger_event_count")) is int and
            evidence["ledger_event_count"] == len(rows), "Event count mismatch")
    require(type(evidence.get("linked_count")) is int and
            evidence["linked_count"] == len(evidence["linked_observations"]),
            "Linked count mismatch")
    # Validate ledger rows before cross-report equality checks, so malformed
    # confidence/PTS cannot masquerade as a mere disagreement with crop metadata.
    for i, event in enumerate(rows):
        require(type(event) is dict and type(event.get("event_index")) is int and
                event["event_index"] == i, "Invalid ledger event index")
        finite_unit(event.get("confidence"), "event confidence")
        require(pts(event.get("source_pts_seconds"), "event PTS") <= duration,
                "Ledger event after source duration")
    seen = set()
    linked = {}
    for obs in evidence["linked_observations"]:
        require(type(obs) is dict and type(obs.get("event_index")) is int and
                0 <= obs["event_index"] < len(rows) and
                obs["event_index"] not in seen and
                obs.get("crop_bytes_hash_verified") is True and
                obs.get("source_recording_frame_verified") is False,
                "Invalid/overclaiming linked observation")
        i = obs["event_index"]
        seen.add(i)
        digest(obs.get("crop_sha256"), "crop SHA")
        finite_unit(obs.get("recognition_confidence"), "recognition confidence")
        finite_unit(obs.get("ledger_event_confidence"), "linked ledger confidence")
        require(obs.get("street") == rows[i].get("street") and
                obs.get("actor") == rows[i].get("actor") and
                obs.get("kind") == rows[i].get("kind") and
                obs["ledger_event_confidence"] == rows[i].get("confidence") and
                pts(obs.get("event_pts_seconds"), "linked event PTS") ==
                pts(rows[i].get("source_pts_seconds"), "ledger PTS") and
                pts(obs.get("frame_pts_seconds"), "frame PTS") <= duration and
                abs(obs["frame_pts_seconds"] - obs["event_pts_seconds"]) <= 1.5,
                "Linked observation disagrees with ledger")
        linked[i] = obs
    missing = evidence["unlinked_event_indices"]
    require(all(type(i) is int and 0 <= i < len(rows) for i in missing) and
            missing == sorted(set(missing)) and
            set(missing) == set(range(len(rows))) - seen,
            "Unlinked event indices inconsistent")
    require(all(type(flag) is str and 0 < len(flag) <= 120 for flag in ledger["review_flags"]),
            "Invalid hand review flags")
    result_rows = []
    total_score = 0
    for i, event in enumerate(rows):
        require(type(event) is dict and event.get("event_index") == i and
                event.get("street") in STREETS and
                type(event.get("actor")) is str and 0 < len(event["actor"]) <= 64 and
                event.get("kind") in ("post_blind", "fold", "check", "call", "bet", "raise") and
                type(event.get("review_flags")) is list and
                all(type(x) is str and 0 < len(x) <= 120 for x in event["review_flags"]),
                "Invalid ledger event")
        event_conf = finite_unit(event.get("confidence"), "event confidence")
        require(pts(event.get("source_pts_seconds"), "event PTS") <= duration,
                "Ledger event after source duration")
        crop = linked.get(i)
        flags = list(event["review_flags"])
        score = 0
        if crop is None:
            flags.append("no_linked_frame_crop")
            score += 4
        else:
            rec_conf = finite_unit(crop["recognition_confidence"], "recognition confidence")
            if rec_conf < 0.8:
                flags.append("low_uncalibrated_recognition_confidence")
                score += 2
        if event_conf < 0.8:
            flags.append("low_uncalibrated_event_confidence")
            score += 2
        if event["review_flags"]:
            score += 3
        total_score += score
        result_rows.append({
            "event_index": i, "street": event["street"],
            "actor": event["actor"], "kind": event["kind"],
            "source_pts_seconds_claim": float(event["source_pts_seconds"]),
            "ledger_confidence_uncalibrated": event_conf,
            "recognition_confidence_uncalibrated": None if crop is None else float(crop["recognition_confidence"]),
            "crop_sha256_if_linked": None if crop is None else crop["crop_sha256"],
            "review_reasons": sorted(set(flags)),
            "review_priority_points_not_probability": score,
        })
    tail_class = None
    if tail is not None:
        require(type(tail) is dict and tail.get("schema_version") == 1 and
                tail.get("status") == TAIL_STATUS and
                tail.get("source_sha256") == source_sha and
                type(tail.get("classification")) is str and
                tail.get("visual_provenance_verified") is False and
                tail.get("ocr_verified") is False and
                tail.get("equity_ev_authorized") is False and
                type(tail.get("possible_added_terminal_duplicate")) is bool and
                type(tail.get("possible_missing_terminal_frames")) is bool,
                "Temporal audit source/status mismatch or overclaim")
        digest(tail.get("clip_sha256"), "clip SHA")
        tail_class = tail["classification"]
        require(tail_class in {
            CLEAN_TAIL, "possible_added_terminal_duplicate",
            "possible_missing_terminal_frames", "multiple_possible_terminal_anomalies",
            "indeterminate_static_or_insufficient_source_motion",
            "indeterminate_terminal_difference"}, "Unknown temporal classification")
        if tail_class == "possible_added_terminal_duplicate":
            require(tail["possible_added_terminal_duplicate"], "Contradictory tail flag")
        if tail_class == "possible_missing_terminal_frames":
            require(tail["possible_missing_terminal_frames"], "Contradictory tail flag")
        if tail_class != CLEAN_TAIL:
            total_score += 3
    if ledger["review_flags"]:
        total_score += 2
    # A clean-looking hand still requires review, not automatic promotion.
    return {
        "variant": ledger["variant"], "table_id": ledger["table_id"],
        "hand_label": ledger["hand_label"],
        "source_recording_sha256_claim_unverified": source_sha,
        "ledger_canonical_sha256": ledger["input_canonical_sha256"],
        "event_count": len(rows), "unlinked_event_count": len(missing),
        "hand_review_flags": sorted(set(ledger["review_flags"])),
        "temporal_audit_classification": tail_class,
        "temporal_audit_bytes_rechecked": False,
        "events": result_rows,
        "review_priority_points_not_probability": total_score,
        "manual_review_required": True,
        "video_evidence_verified": False, "ocr_accuracy_verified": False,
        "equity_ev_authorized": False, "automatic_clip_selection_authorized": False,
    }


def build_queue(manifest: dict, reports: dict[str, dict]) -> dict:
    require(type(manifest) is dict and set(manifest) == {
        "schema_version", "session_label", "source_recording_sha256_claim", "hands"},
        "Invalid queue manifest")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            type(manifest["session_label"]) is str and 0 < len(manifest["session_label"]) <= 120 and
            type(manifest["hands"]) is list and 1 <= len(manifest["hands"]) <= MAX_HANDS,
            "Invalid session metadata")
    source = digest(manifest["source_recording_sha256_claim"], "manifest source SHA")
    hands = []
    keys = set()
    for entry in manifest["hands"]:
        require(type(entry) is dict and set(entry) == {"ledger", "evidence", "temporal_audit"},
                "Invalid hand entry")
        ledger_name, evidence_name = safe_name(entry["ledger"]), safe_name(entry["evidence"])
        tail_name = entry["temporal_audit"]
        require(tail_name is None or type(tail_name) is str, "Invalid temporal report")
        if tail_name is not None:
            tail_name = safe_name(tail_name)
        require(len({n for n in (ledger_name, evidence_name, tail_name) if n is not None}) ==
                (3 if tail_name else 2), "Same report reused within hand")
        for name in (ledger_name, evidence_name, tail_name):
            if name is not None:
                require(name in reports, "Missing named report")
        hand = analyze_hand(reports[ledger_name], reports[evidence_name],
                            None if tail_name is None else reports[tail_name])
        require(hand["source_recording_sha256_claim_unverified"] == source,
                "Different source recording claims")
        key = (hand["table_id"], hand["hand_label"])
        require(key not in keys, "Duplicate table/hand identity")
        keys.add(key)
        hands.append(hand)
    hands.sort(key=lambda h: (-h["review_priority_points_not_probability"],
                              h["table_id"], h["hand_label"]))
    return {
        "schema_version": 1,
        "status": "offline_human_review_priority_not_strategy_or_video_verification",
        "session_label": manifest["session_label"],
        "source_recording_sha256_claim_unverified": source,
        "hands": hands, "hand_count": len(hands),
        "review_priority_method": "deterministic_missing_evidence_and_diagnostic_flags_not_calibrated",
        "all_hands_require_manual_review": True,
        "video_evidence_verified": False, "ocr_accuracy_verified": False,
        "equity_ev_authorized": False, "automatic_clip_selection_authorized": False,
        "limitations": [
            "SHA-256 source is a claim from reports, not rechecked against the recording.",
            "Linked crop hashes were checked upstream, not rechecked by this queue.",
            "Temporal reports and clips are not rehashed by this queue.",
            "Confidence values are uncalibrated and must not be multiplied into a probability.",
            "Priority points rank human review effort, not strategic importance or poker mistakes.",
            "Missing observations, hidden cards, side pots, and unknown ranges remain unresolved.",
        ],
    }


def render_html(queue: dict) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    sections = []
    for hand in queue["hands"]:
        events = []
        for event in hand["events"]:
            reasons = ", ".join(event["review_reasons"]) or "Sem alertas locais; revisão obrigatória"
            events.append(f"<tr><td>{event['event_index']}</td><td>{esc(event['street'])}</td>"
                          f"<td>{esc(event['actor'])}</td><td>{esc(event['kind'])}</td>"
                          f"<td>{event['source_pts_seconds_claim']:.3f}</td>"
                          f"<td>{esc(reasons)}</td></tr>")
        sections.append(f"<section><h2>Mesa {hand['table_id']} · {esc(hand['hand_label'])} · "
                        f"{esc(hand['variant'])}</h2><p>Pontos de triagem: "
                        f"{hand['review_priority_points_not_probability']} (não probabilidade). "
                        f"Eventos sem recorte: {hand['unlinked_event_count']}. "
                        f"Auditoria temporal: {esc(hand['temporal_audit_classification'] or 'não fornecida')}.</p>"
                        f"<table><thead><tr><th>#</th><th>Rodada</th><th>Jogador</th><th>Ação</th>"
                        f"<th>PTS alegado</th><th>Revisar</th></tr></thead><tbody>{''.join(events)}"
                        f"</tbody></table></section>")
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
            "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>PLO Trainee · Fila de revisão offline</title><style>"
            ":root{color-scheme:dark}body{background:#101827;color:#eef4fc;max-width:1100px;"
            "margin:auto;padding:1.5rem;font:15px/1.5 system-ui}section,header,aside{"
            "background:#1b293d;border:1px solid #40536d;border-radius:12px;"
            "padding:1rem;margin:1rem 0}aside{background:#49331c}table{width:100%;"
            "border-collapse:collapse;display:block;overflow-x:auto}th,td{border:1px solid #40536d;"
            "padding:.5rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}"
            "</style></head><body><header><h1>PLO Trainee · Fila de revisão humana</h1>"
            f"<p>{esc(queue['session_label'])} · {queue['hand_count']} mãos · offline</p></header>"
            "<aside>Prioridade é heurística de conferência humana, não probabilidade de erro, "
            "equity, EV, nem prova de ação. Nenhuma seleção automática de cortes autorizada. "
            "Vídeo original, crops e clipes NÃO foram revalidados por esta fila.</aside>"
            + "".join(sections) + "</body></html>")


def export(manifest_path: str | Path, json_output: str | Path, html_output: str | Path) -> dict:
    manifest_path, json_output, html_output = map(Path, (manifest_path, json_output, html_output))
    root = manifest_path.parent
    require(root.is_dir() and not root.is_symlink(), "Unsafe manifest folder")
    require(json_output.parent.resolve() == root.resolve() and
            html_output.parent.resolve() == root.resolve() and
            json_output.suffix.lower() == ".json" and html_output.suffix.lower() == ".html" and
            json_output != html_output and
            not json_output.exists() and not json_output.is_symlink() and
            not html_output.exists() and not html_output.is_symlink(),
            "Outputs must be new files beside manifest")
    manifest, manifest_sha = read_report(root, manifest_path.name)
    require(type(manifest.get("hands")) is list and len(manifest["hands"]) <= MAX_HANDS,
            "Invalid manifest hand list")
    names = set()
    for entry in manifest["hands"]:
        require(type(entry) is dict, "Invalid hand entry")
        for key in ("ledger", "evidence", "temporal_audit"):
            name = entry.get(key)
            if name is not None:
                names.add(safe_name(name))
    require(json_output.name not in names and html_output.name not in names and
            manifest_path.name not in names, "Output/input collision")
    loaded = {name: read_report(root, name) for name in sorted(names)}
    queue = build_queue(manifest, {name: value[0] for name, value in loaded.items()})
    json_bytes = (json.dumps(queue, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    html_bytes = render_html(queue).encode("utf-8")
    require(len(json_bytes) <= MAX_JSON and len(html_bytes) <= MAX_HTML,
            "Generated report exceeds limit")
    require(read_report(root, manifest_path.name)[1] == manifest_sha and
            all(read_report(root, name)[1] == value[1] for name, value in loaded.items()),
            "Input changed during export")
    written = []
    try:
        for path, payload in ((json_output, json_bytes), (html_output, html_bytes)):
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            written.append(path)
            with os.fdopen(fd, "wb") as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output type")
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"status": queue["status"], "hands": queue["hand_count"],
            "manual_review_required": True, "equity_ev_authorized": False,
            "json": str(json_output), "html": str(html_output)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_manifest_json")
    parser.add_argument("new_queue_json")
    parser.add_argument("new_queue_html")
    args = parser.parse_args(argv)
    print(json.dumps(export(args.session_manifest_json, args.new_queue_json,
                            args.new_queue_html), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
