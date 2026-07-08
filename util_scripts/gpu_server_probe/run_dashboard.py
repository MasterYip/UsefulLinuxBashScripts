#!/usr/bin/env python3
"""
GPU Server Resource Dashboard
==============================

Monitor GPU, CPU, and RAM usage across multiple servers via SSH.
Supports both a web dashboard (browser) and a terminal TUI.

Usage:
  # Web dashboard (open http://localhost:8080)
  ./run_dashboard.py web

  # Web dashboard on a custom port
  ./run_dashboard.py web --port 9090

  # Terminal TUI
  ./run_dashboard.py tui

  # Custom config, interval, and timeout
  ./run_dashboard.py web --config servers_rp.yaml --interval 5 --ssh-timeout 8
  ./run_dashboard.py tui --config servers_rp.yaml --interval 5 --ssh-timeout 8
"""

from __future__ import annotations

import argparse
import logging
import sys


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared arguments to a (sub)parser."""
    parser.add_argument(
        "--config",
        default=None,
        help="Path to servers.yaml (default: servers.yaml next to this script)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Probe interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--ssh-timeout",
        type=int,
        default=5,
        help="SSH timeout per server in seconds (default: 5)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GPU Server Resource Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subs = parser.add_subparsers(dest="mode", help="Dashboard mode")

    # -- web --
    web_parser = subs.add_parser("web", help="Start web dashboard (browser)")
    web_parser.add_argument(
        "--port", type=int, default=8080, help="HTTP port (default: 8080)"
    )
    web_parser.add_argument(
        "--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    _add_common_args(web_parser)

    # -- tui --
    tui_parser = subs.add_parser("tui", help="Start terminal dashboard")
    _add_common_args(tui_parser)

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve config path
    import os
    from pathlib import Path

    if args.config:
        config_path = args.config
    else:
        config_path = str(
            Path(__file__).resolve().parent / "servers.yaml"
        )
    config_path = os.path.expanduser(config_path)

    if args.mode == "web":
        import uvicorn
        from dashboard.web import create_app

        app = create_app(
            config_path=config_path,
            interval=args.interval,
            ssh_timeout=args.ssh_timeout,
        )
        # Print the actual browsable URL (0.0.0.0 isn't a valid browser address)
        display_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
        print(f"\n  Dashboard: http://{display_host}:{args.port}\n")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")

    elif args.mode == "tui":
        import asyncio
        from dashboard.tui import run_tui

        try:
            asyncio.run(
                run_tui(
                    config_path=config_path,
                    interval=args.interval,
                    ssh_timeout=args.ssh_timeout,
                )
            )
        except KeyboardInterrupt:
            print("\nExited.")


if __name__ == "__main__":
    main()
