"""Terminal presentation. Two renderers share one interface:

* :class:`RichRenderer` uses the optional ``rich`` package (dark theme).
* :class:`PlainRenderer` uses only the standard library.
"""

from __future__ import annotations

import sys
from typing import Optional, Sequence

from minescope.core import constants as c
from minescope.database.repository import ScanRecord
from minescope.models.server import ScanResult
from minescope.services.analytics import ServerStatistics

try:  # pragma: no cover - exercised only when rich is installed
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False

BANNER = [
    r" __  __ _            ____                         ",
    r"|  \/  (_)_ __   ___/ ___|  ___ ___  _ __   ___   ",
    r"| |\/| | | '_ \ / _ \___ \ / __/ _ \| '_ \ / _ \  ",
    r"| |  | | | | | |  __/___) | (_| (_) | |_) |  __/  ",
    r"|_|  |_|_|_| |_|\___|____/ \___\___/| .__/ \___|  ",
    r"                                     |_|           ",
]
TAGLINE = "Minecraft Server Intelligence Platform"


def _players(r: ScanResult) -> str:
    if r.players_online is not None and r.players_max is not None:
        return f"{r.players_online}/{r.players_max}"
    return "-"


def _latency(value: Optional[float]) -> str:
    return f"{value:.1f} ms" if value is not None else "-"


def _fmt(value: object) -> str:
    return "-" if value is None else str(value)


class Renderer:
    """Interface for terminal output."""

    def banner(self) -> None: raise NotImplementedError
    def info(self, message: str) -> None: raise NotImplementedError
    def success(self, message: str) -> None: raise NotImplementedError
    def warning(self, message: str) -> None: raise NotImplementedError
    def error(self, message: str, hint: str = "") -> None: raise NotImplementedError
    def results(self, results: Sequence[ScanResult], title: str = "Scan results") -> None: raise NotImplementedError
    def server_panel(self, result: ScanResult) -> None: raise NotImplementedError
    def dashboard(self, cycle: int, results: Sequence[ScanResult], interval: float) -> None: raise NotImplementedError
    def statistics(self, label: str, stats: ServerStatistics) -> None: raise NotImplementedError
    def history(self, label: str, records: Sequence[ScanRecord]) -> None: raise NotImplementedError
    def about(self) -> None: raise NotImplementedError
    def menu(self, options: Sequence[tuple[str, str]]) -> None: raise NotImplementedError
    def prompt(self, question: str, default: str = "") -> str: raise NotImplementedError
    def clear(self) -> None: raise NotImplementedError


def _server_lines(r: ScanResult) -> list[tuple[str, str]]:
    lines = [("Name", r.name), ("Address", r.address), ("Edition", r.edition),
             ("Status", "ONLINE" if r.online else "OFFLINE")]
    if r.online:
        lines += [("Latency", _latency(r.latency_ms)), ("Version", _fmt(r.version)),
                  ("Protocol", _fmt(r.protocol)), ("MOTD", _fmt(r.motd)),
                  ("Players", _players(r))]
        if r.player_names:
            lines.append(("Player names", ", ".join(r.player_names)))
        elif r.edition == "bedrock":
            lines.append(("Player names", "not provided by the Bedrock status protocol"))
        elif r.edition == "java":
            lines.append(("Player names", "not exposed (no status sample / Query disabled)"))
        if r.gamemode:
            lines.append(("Game mode", r.gamemode))
        if r.map_name:
            lines.append(("World", r.map_name))
        if r.software:
            lines.append(("Software", r.software))
        if r.plugins:
            lines.append(("Plugins", ", ".join(r.plugins)))
        lines.append(("Query", "available" if r.query_available else "not available"))
    else:
        lines.append(("Error", _fmt(r.error)))
    lines.append(("Scanned at", r.scanned_at))
    return lines


def _stat_lines(s: ServerStatistics) -> list[tuple[str, str]]:
    uptime = f"{s.uptime_percent}%" if s.uptime_percent is not None else "-"
    return [("Checks", f"{s.checks} ({s.online_checks} online)"), ("Uptime", uptime),
            ("Latency avg", _latency(s.latency_avg_ms)), ("Latency min", _latency(s.latency_min_ms)),
            ("Latency max", _latency(s.latency_max_ms)), ("Players avg", _fmt(s.players_avg)),
            ("Players peak", _fmt(s.players_peak)), ("Outages", str(s.outages)),
            ("Longest outage", f"{s.longest_outage_checks} checks"),
            ("First seen", _fmt(s.first_seen)), ("Last seen", _fmt(s.last_seen)),
            ("Last online", _fmt(s.last_online))]


ABOUT = [("Product", c.FULL_NAME), ("Version", c.VERSION), ("Organization", c.ORGANIZATION),
         ("Project owner", c.OWNER), ("Lead developer", c.LEAD_DEVELOPER),
         ("GitHub", c.GITHUB_URL), ("License", "MIT"),
         ("Editions", "Java (Server List Ping, Query), Bedrock (RakNet Unconnected Ping)")]


class PlainRenderer(Renderer):
    """Standard-library renderer (no colors, works everywhere)."""

    def __init__(self, stream=None) -> None:  # type: ignore[no-untyped-def]
        self.out = stream or sys.stdout

    def _p(self, text: str = "") -> None:
        print(text, file=self.out)

    def clear(self) -> None:
        pass

    def banner(self) -> None:
        for line in BANNER:
            self._p(line)
        self._p(f"{TAGLINE}  v{c.VERSION}  |  {c.ORGANIZATION}")
        self._p("-" * 60)

    def info(self, message: str) -> None: self._p(f"[i] {message}")
    def success(self, message: str) -> None: self._p(f"[+] {message}")
    def warning(self, message: str) -> None: self._p(f"[!] {message}")

    def error(self, message: str, hint: str = "") -> None:
        self._p(f"[x] Error: {message}")
        if hint:
            self._p(f"    Hint: {hint}")

    def _table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
                  for i, h in enumerate(headers)]
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        self._p(fmt.format(*headers))
        self._p(fmt.format(*("-" * w for w in widths)))
        for row in rows:
            self._p(fmt.format(*row))

    def results(self, results: Sequence[ScanResult], title: str = "Scan results") -> None:
        self._p(title)
        rows = [[r.name, r.edition, "ONLINE" if r.online else "OFFLINE", _players(r),
                 _fmt(r.version), _latency(r.latency_ms)] for r in results]
        self._table(["Server", "Edition", "Status", "Players", "Version", "Latency"], rows)

    def server_panel(self, result: ScanResult) -> None:
        self._p()
        for key, value in _server_lines(result):
            self._p(f"  {key:<14}{value}")

    def dashboard(self, cycle: int, results: Sequence[ScanResult], interval: float) -> None:
        online = sum(1 for r in results if r.online)
        self._p(f"-- cycle {cycle}: {online}/{len(results)} online (every {interval:g}s, Ctrl+C to stop)")
        self.results(results, "Monitoring")

    def statistics(self, label: str, stats: ServerStatistics) -> None:
        self._p(f"Statistics for {label}")
        for key, value in _stat_lines(stats):
            self._p(f"  {key:<16}{value}")

    def history(self, label: str, records: Sequence[ScanRecord]) -> None:
        self._p(f"History for {label} ({len(records)} checks)")
        rows = [[r.scanned_at, "ONLINE" if r.online else "OFFLINE", _latency(r.latency_ms),
                 f"{r.players_online}/{r.players_max}" if r.players_online is not None else "-",
                 _fmt(r.version)] for r in records]
        self._table(["Time (UTC)", "Status", "Latency", "Players", "Version"], rows)

    def about(self) -> None:
        self.banner()
        for key, value in ABOUT:
            self._p(f"  {key:<16}{value}")

    def menu(self, options: Sequence[tuple[str, str]]) -> None:
        for key, label in options:
            self._p(f"  [{key}] {label}")

    def prompt(self, question: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        try:
            answer = input(f"{question}{suffix}: ").strip()
        except EOFError:
            return default
        return answer or default


class RichRenderer(PlainRenderer):  # pragma: no cover - requires rich
    """Dark-themed renderer built on ``rich``."""

    def __init__(self) -> None:
        super().__init__()
        self.console = Console()

    def clear(self) -> None:
        self.console.clear()

    def banner(self) -> None:
        art = Text("\n".join(BANNER), style="bold cyan")
        self.console.print(Panel(art, border_style="cyan", box=box.ROUNDED,
                                 subtitle=f"[dim]{TAGLINE} · v{c.VERSION} · {c.ORGANIZATION}[/dim]"))

    def info(self, message: str) -> None: self.console.print(f"[cyan]ℹ[/cyan] {message}")
    def success(self, message: str) -> None: self.console.print(f"[green]✔[/green] {message}")
    def warning(self, message: str) -> None: self.console.print(f"[yellow]![/yellow] {message}")

    def error(self, message: str, hint: str = "") -> None:
        body = Text(message, style="red")
        if hint:
            body.append(f"\nHint: {hint}", style="dim")
        self.console.print(Panel(body, title="Error", border_style="red", box=box.ROUNDED))

    def _status(self, online: bool) -> Text:
        return Text("● ONLINE", style="bold green") if online else Text("● OFFLINE", style="bold red")

    def results(self, results: Sequence[ScanResult], title: str = "Scan results") -> None:
        table = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold cyan")
        for column in ("Server", "Edition", "Status", "Players", "Version", "Latency"):
            table.add_column(column)
        for r in results:
            table.add_row(r.name, r.edition, self._status(r.online), _players(r),
                          _fmt(r.version), _latency(r.latency_ms))
        self.console.print(table)

    def _kv_panel(self, title: str, lines: Sequence[tuple[str, str]], style: str = "cyan") -> None:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()
        for key, value in lines:
            table.add_row(key, Text(value))
        self.console.print(Panel(table, title=title, border_style=style, box=box.ROUNDED))

    def server_panel(self, result: ScanResult) -> None:
        self._kv_panel(result.name, _server_lines(result), "green" if result.online else "red")

    def dashboard(self, cycle: int, results: Sequence[ScanResult], interval: float) -> None:
        self.console.clear()
        self.banner()
        online = sum(1 for r in results if r.online)
        self.console.print(f"[bold]Monitoring[/bold] · cycle {cycle} · "
                           f"[green]{online}[/green]/{len(results)} online · "
                           f"every {interval:g}s · [dim]Ctrl+C to stop[/dim]")
        self.results(results, "Live status")

    def statistics(self, label: str, stats: ServerStatistics) -> None:
        self._kv_panel(f"Statistics — {label}", _stat_lines(stats))

    def history(self, label: str, records: Sequence[ScanRecord]) -> None:
        table = Table(title=f"History — {label}", box=box.SIMPLE_HEAVY, header_style="bold cyan")
        for column in ("Time (UTC)", "Status", "Latency", "Players", "Version"):
            table.add_column(column)
        for r in records:
            players = f"{r.players_online}/{r.players_max}" if r.players_online is not None else "-"
            table.add_row(r.scanned_at, self._status(r.online), _latency(r.latency_ms),
                          players, _fmt(r.version))
        self.console.print(table)

    def about(self) -> None:
        self.banner()
        self._kv_panel("About MineScope", ABOUT)

    def menu(self, options: Sequence[tuple[str, str]]) -> None:
        for key, label in options:
            self.console.print(f"  [bold cyan]{key}[/bold cyan]  {label}")

    def prompt(self, question: str, default: str = "") -> str:
        return PlainRenderer.prompt(self, question, default)


def make_renderer(plain: bool = False) -> Renderer:
    """Return a rich renderer when available and allowed, else the plain one."""
    if HAS_RICH and not plain and sys.stdout.isatty():
        return RichRenderer()
    return PlainRenderer()
