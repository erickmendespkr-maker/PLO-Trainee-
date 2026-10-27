"""Static offline HTML review page for declared PLO5/PLO6 decision timestamps.

Re-audits each pipeline directory; never trusts an old timeline index or
claims to verify video content. No JavaScript, tracking or live poker access.
"""
from __future__ import annotations

import argparse
import html
import os
from pathlib import Path
import stat
from urllib.parse import quote

from offline_reviewed_decision_timeline import build_index, NAME, require

MAX_HTML = 2 * 1024 * 1024


def esc(value):
    return html.escape(str(value), quote=True)


def render(index):
    cards = []
    for row in index["hands"]:
        heading = f"Mesa {row['table_id']} · {esc(row['hand_label'])} · {esc(row['variant'])}"
        if row["clip_sha256"] is None:
            detail = ("<p>Bloqueada: sem cálculo e sem corte autorizado.</p>"
                      "<p>Motivos: " + esc(", ".join(row["blocked_reasons"])) + "</p>")
        else:
            media = "./" + quote(row["result_directory"], safe="") + "/clip.mp4"
            detail = (f'<p>Decisão anotada: {row["decision_seconds_human"]:.3f} s; '
                      f'corte {row["clip_start_seconds_human"]:.3f}–'
                      f'{row["clip_end_seconds_human"]:.3f} s.</p>'
                      f'<video controls preload="none" playsinline src="{esc(media)}">'
                      'Abra o MP4 localmente.</video>'
                      f'<p>Equity Monte Carlo: {100*row["equity_monte_carlo"]:.2f}%; '
                      f'EV condicional do call: {row["ev_call_chips_conditional"]:+.2f} fichas.</p>'
                      f'<p>SHA-256 do MP4: <code>{esc(row["clip_sha256"])}</code>.</p>')
        cards.append(f'<article><h2>{heading}</h2>{detail}</article>')
    overlaps = index["same_table_clip_window_overlaps_review_only"]
    overlap_html = ("<p>Janelas sobrepostas na mesma mesa: " +
                    "; ".join(esc(a) + " / " + esc(b) for a, b in overlaps) +
                    ". Conferir manualmente.</p>") if overlaps else "<p>Nenhuma sobreposição detectada.</p>"
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Decisões revisadas offline</title><style>
:root{{color-scheme:dark}}body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:auto;padding:1.2rem;background:#101827;color:#f0f4fb}}
header,article,aside,footer{{border:1px solid #455873;border-radius:12px;padding:1rem;margin:1rem 0;background:#1d2b40}}
aside{{border-color:#e4a45b;background:#48321e}}video{{width:100%;max-height:360px;background:#000}}
code{{overflow-wrap:anywhere}}h2{{font-size:1.15rem}}
</style></head><body><header><h1>PLO Trainee · Revisão offline</h1>
<p>{index['hand_count']} mãos declaradas · {index['exported_clip_count']} cortes existentes · {index['blocked_count']} bloqueadas.</p>
<p>Fonte SHA-256 declarada: <code>{esc(index['source_recording_sha256_claim_unverified'])}</code>.</p></header>
<aside><strong>Atenção:</strong> timestamps, cartas, ranges e revisão são declarados por humanos.
Os hashes confirmam identidade dos arquivos, não reconhecimento de vídeo. O EV é condicionado às hipóteses;
nenhum erro estratégico foi comprovado. Não há seleção automática de cortes.</aside>
<section><h2>Possíveis sobreposições de cortes</h2>{overlap_html}</section>
{''.join(cards)}<footer><p>Visualização estática local, sem JavaScript e sem acesso a mesas de pôquer.
Quadros e PTS da gravação não foram revalidados nesta página.</p></footer></body></html>'''


def export(directories, new_html):
    output = Path(new_html)
    require(output.suffix == ".html" and NAME.fullmatch(output.stem) and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(Path(p).parent.resolve() == output.parent.resolve() for p in directories),
            "Output must be a new HTML file beside pipeline directories")
    index = build_index(directories)
    payload = render(index).encode("utf-8")
    require(len(payload) <= MAX_HTML, "HTML exceeds size limit")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe HTML output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {"status": "offline_static_review_page_not_video_verified",
            "hands": index["hand_count"], "clips": index["exported_clip_count"],
            "automatic_selection_authorized": False, "output": str(output)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_html")
    parser.add_argument("pipeline_directories", nargs="+")
    args = parser.parse_args(argv)
    import json
    print(json.dumps(export(args.pipeline_directories, args.new_html)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
