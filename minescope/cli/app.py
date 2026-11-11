"""Argument parsing, command dispatch and the interactive menu."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

from minescope.configuration.settings import Settings, load_config, write_example_config
from minescope.core import constants as c
from minescope.core.errors import (
    ConfigurationError, MineScopeError, ValidationError, describe_error)
from minescope.core.logging import configure_logging
from minescope.cli.ui import Renderer, make_renderer
from minescope.models.server import ServerTarget
from minescope.reporting.exporters import FORMATS, write_report
from minescope.services.analytics import parse_since
from minescope.services.facade import MineScopeService

DEFAULT_CONFIG_CANDIDATES = ("minescope.json", "servers.json")
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_OFFLINE = 0, 1, 2, 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minescope",
        description=f"{c.FULL_NAME} (v{c.VERSION}) by {c.ORGANIZATION}. "
                    "Only scan servers you own or are authorized to monitor.")
    parser.add_argument("--version", action="version", version=f"{c.APP_NAME} {c.VERSION}")
    parser.add_argument("-c", "--config", help="path to a JSON configuration file")
    parser.add_argument("--db", help="override the SQLite database path")
    parser.add_argument("--plain", action="store_true", help="disable rich terminal output")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING, ERROR or CRITICAL")
    sub = parser.add_subparsers(dest="command")

    def add_targets(p: argparse.ArgumentParser) -> None:
        p.add_argument("addresses", nargs="*", metavar="HOST[:PORT]",
                       help="servers to scan (default: servers from the config file)")
        p.add_argument("-e", "--edition", default="auto", choices=["auto", "java", "bedrock"],
                       help="edition for addresses given on the command line")
        p.add_argument("-t", "--timeout", type=float, help="network timeout in seconds")
        p.add_argument("-j", "--concurrency", type=int, help="maximum parallel scans")
        p.add_argument("--no-query", action="store_true", help="skip Java Query")

    scan = sub.add_parser("scan", help="scan one or more servers")
    add_targets(scan)
    scan.add_argument("--no-save", action="store_true", help="do not store results in the database")
    scan.add_argument("-r", "--report", action="append", choices=FORMATS, default=[],
                      help="also write a report (repeatable)")
    scan.add_argument("-o", "--output-dir", help="report directory")
    scan.add_argument("--fail-offline", action="store_true",
                      help=f"exit with code {EXIT_OFFLINE} if any server is offline")

    mon = sub.add_parser("monitor", help="continuously monitor servers")
    add_targets(mon)
    mon.add_argument("-i", "--interval", type=float, help="seconds between cycles")
    mon.add_argument("--cycles", type=int, help="stop after this many cycles")
    mon.add_argument("--no-save", action="store_true")

    for name, text in (("history", "show stored scan history"),
                       ("stats", "show uptime and latency statistics")):
        p = sub.add_parser(name, help=text)
        p.add_argument("address", metavar="HOST[:PORT]")
        p.add_argument("-e", "--edition", default="auto", choices=["auto", "java", "bedrock"])
        p.add_argument("--since", help="time window such as 24h, 7d or an ISO date")
        if name == "history":
            p.add_argument("-n", "--limit", type=int, default=20)

    rep = sub.add_parser("report", help="write a report from the latest stored results")
    rep.add_argument("format", choices=FORMATS)
    rep.add_argument("-o", "--output-dir")

    cfg = sub.add_parser("config", help="configuration helpers")
    cfg_sub = cfg.add_subparsers(dest="config_command", required=True)
    init = cfg_sub.add_parser("init", help="write an example configuration file")
    init.add_argument("path", nargs="?", default="minescope.json")
    init.add_argument("--force", action="store_true")
    cfg_sub.add_parser("show", help="show the effective configuration")

    sub.add_parser("about", help="show project information")
    sub.add_parser("menu", help="interactive menu (default when no command is given)")
    return parser


def resolve_settings(args: argparse.Namespace) -> Settings:
    """Load the config file and apply command line overrides."""
    path: Optional[str] = args.config
    if path is None:
        path = next((p for p in DEFAULT_CONFIG_CANDIDATES if Path(p).exists()), None)
    elif not Path(path).exists():
        raise ValidationError(f"Configuration file not found: {path}")
    settings = load_config(path)
    overrides = {}
    if getattr(args, "timeout", None) is not None:
        overrides["timeout"] = args.timeout
    if getattr(args, "concurrency", None) is not None:
        overrides["concurrency"] = args.concurrency
    if getattr(args, "interval", None) is not None:
        overrides["monitor_interval"] = args.interval
    if getattr(args, "no_query", False):
        overrides["try_query"] = False
    if args.db:
        overrides["database_path"] = args.db
    if getattr(args, "output_dir", None):
        overrides["report_dir"] = args.output_dir
    if args.log_level:
        overrides["log_level"] = args.log_level
    try:
        return replace(settings, **overrides).validate()
    except ConfigurationError as exc:
        # The file itself already validated, so this came from a command line flag.
        raise ValidationError(str(exc)) from None


def resolve_targets(args: argparse.Namespace, settings: Settings) -> list[ServerTarget]:
    if getattr(args, "addresses", None):
        return [MineScopeService.make_target(a, args.edition) for a in args.addresses]
    if not settings.servers:
        raise ValidationError("No servers given. Pass HOST[:PORT] or create a config with "
                              "'minescope config init'.")
    return list(settings.servers)


def cmd_scan(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    targets = resolve_targets(args, settings)
    with MineScopeService(settings, persist=not args.no_save) as service:
        ui.info(f"Scanning {len(targets)} server(s)...")
        results = service.scan(targets)
    ui.results(results)
    for result in results:
        ui.server_panel(result)
    for fmt in args.report:
        ui.success(f"Report written: {write_report(results, fmt, settings.report_dir)}")
    if args.fail_offline and any(not r.online for r in results):
        return EXIT_OFFLINE
    return EXIT_OK


def cmd_monitor(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    targets = resolve_targets(args, settings)
    with MineScopeService(settings, persist=not args.no_save) as service:
        def show(cycle: int, results: list) -> None:  # type: ignore[type-arg]
            ui.dashboard(cycle, results, settings.monitor_interval)

        monitor = service.monitor(targets, on_cycle=show)
        _install_sigterm(monitor.stop)
        finished = threading.Event()

        def worker() -> None:
            try:
                monitor.run(max_cycles=args.cycles)
            finally:
                finished.set()

        # An Event is used instead of Thread.join(): join() can return early when
        # interrupted by a signal, which would drop the in-flight cycle's results.
        threading.Thread(target=worker, name="minescope-monitor", daemon=True).start()
        try:
            while not finished.wait(0.2):
                pass
        except KeyboardInterrupt:
            ui.warning("Stopping after the current cycle... (press Ctrl+C again to force quit)")
            monitor.stop()
            try:
                while not finished.wait(0.2):
                    pass
            except KeyboardInterrupt:
                ui.warning("Forced exit; the current cycle was not saved.")
                return 130
        ui.success(f"Monitoring stopped after {monitor.cycles_completed} cycle(s).")
    return EXIT_OK


def _install_sigterm(callback) -> None:  # type: ignore[no-untyped-def]
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGTERM, lambda *_: callback())
        except (ValueError, OSError):
            pass


def _single_target(args: argparse.Namespace) -> ServerTarget:
    return MineScopeService.make_target(args.address, args.edition)


def cmd_history(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    target = _single_target(args)
    since = parse_since(args.since) if args.since else None
    with MineScopeService(settings) as service:
        records = service.history(target, limit=args.limit, since=since)
    if not records:
        ui.warning(f"No stored history for {target.address}.")
        return EXIT_OK
    ui.history(target.address, records)
    return EXIT_OK


def cmd_stats(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    target = _single_target(args)
    since = parse_since(args.since) if args.since else None
    with MineScopeService(settings) as service:
        stats = service.statistics(target, since)
    if stats.checks == 0:
        ui.warning(f"No stored history for {target.address}.")
        return EXIT_OK
    ui.statistics(target.address, stats)
    return EXIT_OK


def cmd_report(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    from minescope.models.server import ScanResult
    with MineScopeService(settings) as service:
        records = service.database.latest()
    if not records:
        ui.warning("No stored results. Run 'minescope scan' first.")
        return EXIT_OK
    results = [ScanResult(name=r.name or f"{r.host}:{r.port}", host=r.host, port=r.port,
                          edition=r.edition, online=r.online, latency_ms=r.latency_ms,
                          version=r.version, motd=r.motd, players_online=r.players_online,
                          players_max=r.players_max, player_names=r.player_names,
                          error=r.error, scanned_at=r.scanned_at) for r in records]
    ui.success(f"Report written: {write_report(results, args.format, settings.report_dir)}")
    return EXIT_OK


def cmd_config(args: argparse.Namespace, settings: Settings, ui: Renderer) -> int:
    if args.config_command == "init":
        path = write_example_config(args.path, overwrite=args.force)
        ui.success(f"Example configuration written to {path}. Replace the placeholder hosts.")
        return EXIT_OK
    from minescope.configuration.settings import to_document
    import json
    print(json.dumps(to_document(settings), indent=2))
    return EXIT_OK


MENU = [("1", "Scan a server"), ("2", "Scan servers from config"), ("3", "Live monitoring"),
        ("4", "History & statistics"), ("5", "Create report"), ("6", "About"), ("0", "Exit")]


def interactive(settings: Settings, ui: Renderer) -> int:
    """Interactive menu loop."""
    last: list = []  # type: ignore[type-arg]
    while True:
        ui.clear()
        ui.banner()
        ui.menu(MENU)
        choice = ui.prompt("Select", "0")
        try:
            if choice == "0":
                return EXIT_OK
            if choice == "1":
                edition = ui.prompt("Edition (auto/java/bedrock)", "auto")
                address = ui.prompt("Server HOST[:PORT]")
                target = MineScopeService.make_target(address, edition)
                with MineScopeService(settings) as service:
                    last = service.scan([target])
                ui.results(last)
                ui.server_panel(last[0])
            elif choice == "2":
                if not settings.servers:
                    raise ValidationError("No servers configured. Run: minescope config init")
                with MineScopeService(settings) as service:
                    last = service.scan(settings.servers)
                ui.results(last)
            elif choice == "3":
                ns = argparse.Namespace(addresses=[], edition="auto", cycles=None, no_save=False)
                cmd_monitor(ns, settings, ui)
            elif choice == "4":
                target = MineScopeService.make_target(
                    ui.prompt("Server HOST[:PORT]"), ui.prompt("Edition", "auto"))
                with MineScopeService(settings) as service:
                    records = service.history(target, limit=15)
                    stats = service.statistics(target)
                if records:
                    ui.history(target.address, records)
                    ui.statistics(target.address, stats)
                else:
                    ui.warning("No stored history for that server.")
            elif choice == "5":
                if not last:
                    raise ValidationError("Run a scan first.")
                fmt = ui.prompt("Format (json/csv/html)", "html")
                ui.success(f"Report written: {write_report(last, fmt, settings.report_dir)}")
            elif choice == "6":
                ui.about()
            else:
                ui.warning("Unknown option.")
        except KeyboardInterrupt:
            return EXIT_OK
        except MineScopeError as exc:
            ui.error(describe_error(exc))
        ui.prompt("\nPress Enter to continue")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    ui = make_renderer(args.plain)
    try:
        settings = resolve_settings(args)
        configure_logging(settings.log_level, settings.log_file, settings.structured_logs)
        command = args.command or "menu"
        if command == "about":
            ui.about()
            return EXIT_OK
        if command == "menu":
            return interactive(settings, ui)
        handlers = {"scan": cmd_scan, "monitor": cmd_monitor, "history": cmd_history,
                    "stats": cmd_stats, "report": cmd_report, "config": cmd_config}
        return handlers[command](args, settings, ui)
    except ValidationError as exc:
        ui.error(str(exc), "Run with --help for usage.")
        return EXIT_USAGE
    except MineScopeError as exc:
        ui.error(describe_error(exc))
        return EXIT_ERROR
    except BrokenPipeError:
        # Output consumer (e.g. ``| head``) went away; exit quietly.
        try:
            sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - keep interpreter exit clean
        except OSError:
            pass
        return EXIT_OK
    except KeyboardInterrupt:
        ui.warning("Interrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 - last-resort boundary
        logging.getLogger("minescope").exception("unexpected error")
        ui.error(f"Unexpected error: {exc.__class__.__name__}: {exc}",
                 "Re-run with --log-level DEBUG for details.")
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
