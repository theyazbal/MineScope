"""Report renderers and safe file writing."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Sequence

from minescope.core.constants import APP_NAME, ORGANIZATION, VERSION
from minescope.core.errors import ReportError
from minescope.models.server import ScanResult

CSV_FIELDS = ["name", "address", "edition", "online", "latency_ms", "version", "protocol",
              "motd", "players_online", "players_max", "player_names", "gamemode",
              "map_name", "software", "plugins", "query_available", "error", "scanned_at"]
FORMATS = ("json", "csv", "html")


def render_json(results: Sequence[ScanResult]) -> str:
    """Render results as an indented JSON document with metadata."""
    document = {
        "generator": f"{APP_NAME} {VERSION}",
        "organization": ORGANIZATION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _csv_safe(value: object) -> object:
    """Neutralize spreadsheet formula injection in text cells."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def render_csv(results: Sequence[ScanResult]) -> str:
    """Render results as CSV (lists joined with ``;``)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for result in results:
        row = result.to_dict()
        row["player_names"] = ";".join(row["player_names"])
        row["plugins"] = ";".join(row["plugins"])
        writer.writerow({k: _csv_safe(row.get(k)) for k in CSV_FIELDS})
    return buffer.getvalue()


_CSS = """
body{background:#0d1117;color:#c9d1d9;font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:2rem}
h1{color:#58a6ff;margin-bottom:0}.sub{color:#8b949e;margin-top:.25rem}
table{border-collapse:collapse;width:100%;margin-top:1.5rem}
th,td{border:1px solid #30363d;padding:.5rem .75rem;text-align:left;vertical-align:top}
th{background:#161b22;color:#58a6ff}.on{color:#3fb950;font-weight:600}.off{color:#f85149;font-weight:600}
footer{margin-top:2rem;color:#8b949e;font-size:.85rem}
"""


def render_html(results: Sequence[ScanResult], title: str = "MineScope Report") -> str:
    """Render a standalone, dependency-free HTML report. All values are escaped."""
    online = sum(1 for r in results if r.online)
    rows = []
    for r in results:
        status = '<span class="on">ONLINE</span>' if r.online else '<span class="off">OFFLINE</span>'
        players = (f"{r.players_online}/{r.players_max}"
                   if r.players_online is not None and r.players_max is not None else "-")
        names = ", ".join(r.player_names) if r.player_names else "-"
        latency = f"{r.latency_ms} ms" if r.latency_ms is not None else "-"
        detail = r.motd or r.error or "-"
        cells = [escape(r.name), escape(r.address), escape(r.edition), status, latency,
                 escape(r.version or "-"), players, escape(names), escape(detail),
                 escape(r.scanned_at)]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    head = ["Name", "Address", "Edition", "Status", "Latency", "Version", "Players",
            "Player names", "MOTD / Error", "Scanned at (UTC)"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{escape(title)}</h1>"
        f"<p class=\"sub\">{online} of {len(results)} servers online</p>"
        "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
        f"<footer>Generated {generated} by {APP_NAME} {VERSION} — {ORGANIZATION}</footer>"
        "</body></html>\n"
    )


_RENDERERS = {"json": render_json, "csv": render_csv, "html": render_html}


def write_report(results: Sequence[ScanResult], fmt: str, directory: str | os.PathLike[str],
                 stem: str | None = None) -> Path:
    """Write a report and return its path. The file name is generated, never user supplied."""
    fmt = fmt.lower()
    if fmt not in _RENDERERS:
        raise ReportError(f"Unknown report format: {fmt!r} (use {', '.join(FORMATS)})")
    folder = Path(directory)
    stamp = stem or datetime.now().strftime("minescope_%Y%m%d_%H%M%S")
    safe = "".join(ch for ch in stamp if ch.isalnum() or ch in "-_")
    if not safe:
        raise ReportError("Invalid report name")
    target = folder / f"{safe}.{fmt}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(_RENDERERS[fmt](results))
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ReportError(f"Cannot write report {target}: {exc.strerror}") from None
    return target
