"""Rich-based terminal dashboard for GPU server monitoring."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from .config import load_servers
from .models import ServerConfig, ServerMetrics
from .probe import probe_all_servers

logger = logging.getLogger(__name__)


def _bar_color(pct: float) -> str:
    if pct < 60:
        return "green"
    if pct < 85:
        return "yellow"
    return "red"


def _status_dot(metrics: ServerMetrics) -> str:
    if metrics.error:
        return "[red]⬤[/red]"
    age = time.time() - metrics.timestamp
    if age > 60:
        return "[red]⬤[/red]"
    if age > 30:
        return "[yellow]⬤[/yellow]"
    return "[green]⬤[/green]"


def _age_str(ts: float) -> str:
    s = max(0, int(time.time() - ts))
    if s < 10:
        return "just now"
    if s < 60:
        return f"{s}s ago"
    return f"{s // 60}m ago"


def _make_progress(pct: float, width: int = 12) -> str:
    """Return a text-based progress bar string."""
    filled = int(round(pct / 100 * width))
    empty = width - filled
    color = _bar_color(pct)
    bar = f"[{color}]" + "█" * filled + "[dim]" + "░" * empty + "[/dim]"
    return bar


def build_layout(
    servers: list[ServerConfig],
    metrics_cache: dict[str, ServerMetrics],
) -> Layout:
    """Build a Rich Layout with all server panels."""
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
    )

    # Header
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    online = sum(1 for m in metrics_cache.values() if not m.error)
    errored = sum(1 for m in metrics_cache.values() if m.error)
    header_text = Text()
    header_text.append("🖥️  GPU Server Dashboard", style="bold white")
    header_text.append(f"    {online} online", style="green")
    if errored:
        header_text.append(f"  {errored} error", style="red")
    header_text.append(f"    {now}", style="dim")
    layout["header"].update(Panel(header_text))

    # Body: table
    table = Table(
        show_header=True,
        header_style="bold dim",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Server", style="bold", width=12)
    table.add_column("GPU", width=30)
    table.add_column("GPU Mem", width=14)
    table.add_column("Temp", width=6)
    table.add_column("CPU", width=14)
    table.add_column("RAM", width=14)
    table.add_column("Status", width=10)

    for server in servers:
        m = metrics_cache.get(server.name)
        if m is None:
            table.add_row(
                server.name,
                "[dim]--[/dim]",
                "[dim]--[/dim]",
                "[dim]--[/dim]",
                "[dim]--[/dim]",
                "[dim]--[/dim]",
                "[dim]probing...[/dim]",
            )
            continue

        dot = _status_dot(m)

        if m.error:
            table.add_row(
                f"{dot} {server.name}",
                "",
                "",
                "",
                "",
                "",
                f"[red]{m.error[:20]}[/red]",
            )
            continue

        # Build GPU summary (one line per GPU)
        gpu_lines: list[str] = []
        gpu_mem_lines: list[str] = []
        temp_lines: list[str] = []
        for g in m.gpu_info:
            bar = _make_progress(g.utilization_gpu)
            gpu_lines.append(f"GPU{g.index}: {bar} {g.utilization_gpu:.0f}%")
            mem_used = g.memory_used_mb / 1024
            mem_total = g.memory_total_mb / 1024
            gpu_mem_lines.append(f"{mem_used:.0f}/{mem_total:.0f}G")
            temp_lines.append(
                f"{g.temperature_gpu:.0f}°C" if g.temperature_gpu is not None else "--"
            )
        if not gpu_lines:
            gpu_lines.append("[dim]no GPU[/dim]")
            gpu_mem_lines.append("[dim]--[/dim]")
            temp_lines.append("[dim]--[/dim]")

        cpu_bar = _make_progress(m.cpu_percent)
        ram_bar = _make_progress(m.ram_percent)

        table.add_row(
            f"{dot} {server.name}",
            "\n".join(gpu_lines),
            "\n".join(gpu_mem_lines),
            "\n".join(temp_lines),
            f"{cpu_bar} {m.cpu_percent:.1f}%",
            f"{ram_bar} {m.ram_used_gb:.0f}/{m.ram_total_gb:.0f}G",
            _age_str(m.timestamp),
        )

    layout["body"].update(Panel(table, title=""))
    return layout


async def run_tui(
    config_path: str,
    interval: int = 10,
    ssh_timeout: int = 5,
) -> None:
    """Run the interactive terminal dashboard.

    Press Ctrl+C to exit.
    """
    servers = load_servers(config_path)
    if not servers:
        print("No servers found in config.")
        return

    console = Console()
    metrics_cache: dict[str, ServerMetrics] = {}

    async def _probe_once():
        nonlocal metrics_cache
        try:
            new_metrics = await probe_all_servers(servers, timeout=ssh_timeout)
        except Exception:
            logger.exception("Probe cycle failed")
            return
        metrics_cache.update(new_metrics)

    # Initial probe
    console.print("[dim]Connecting to servers...[/dim]")
    await _probe_once()

    layout = build_layout(servers, metrics_cache)
    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        while True:
            await asyncio.sleep(interval)
            await _probe_once()
            live.update(build_layout(servers, metrics_cache))
