"""FastAPI web dashboard with Server-Sent Events for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import StreamingResponse

from .config import load_servers
from .models import ServerConfig, ServerMetrics
from .probe import probe_all_servers

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class AppState:
    """Shared mutable state for the dashboard."""

    def __init__(
        self,
        servers: list[ServerConfig],
        interval: int = 10,
        ssh_timeout: int = 5,
    ):
        self.servers = servers
        self.interval = interval
        self.ssh_timeout = ssh_timeout
        self.metrics_cache: dict[str, ServerMetrics] = {}
        self.cache_lock = asyncio.Lock()
        self._update_event = asyncio.Event()


# ---------------------------------------------------------------------------
# Terminal launcher
# ---------------------------------------------------------------------------

_TERMINALS = [
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "lxterminal",
    "terminator",
    "tilix",
    "kitty",
    "alacritty",
    "wezterm",
    "xterm",
    "uxterm",
]

_TERMINAL_ARGS: dict[str, list[str]] = {
    "gnome-terminal": ["--", "bash", "-c"],
    "konsole":       ["-e", "bash", "-c"],
    "xfce4-terminal": ["-e", "bash", "-c"],
    "mate-terminal":  ["-e", "bash", "-c"],
    "lxterminal":     ["-e", "bash", "-c"],
    "terminator":     ["-e", "bash", "-c"],
    "tilix":          ["-e", "bash", "-c"],
    "kitty":          ["bash", "-c"],
    "alacritty":      ["-e", "bash", "-c"],
    "wezterm":        ["start", "--", "bash", "-c"],
    "xterm":          ["-e", "bash", "-c"],
    "uxterm":         ["-e", "bash", "-c"],
}


def _find_terminal() -> tuple[str, list[str]] | None:
    """Return (binary_path, base_args) for the first available terminal emulator."""
    for name in _TERMINALS:
        path = shutil.which(name)
        if path:
            args = _TERMINAL_ARGS.get(name, ["-e", "bash", "-c"])
            return path, args
    return None


def _launch_terminal(ssh_cmd: str) -> str | None:
    """Spawn a terminal emulator running *ssh_cmd*. Returns error message or None."""
    found = _find_terminal()
    if not found:
        return "No terminal emulator found. Copy the SSH command instead."

    term_path, term_args = found
    # Wrap in a 'read' so the terminal stays open after exit
    full_cmd = f"{ssh_cmd} ; echo '---'; read -p 'Press Enter to close...'"
    cmd = [term_path] + term_args + [full_cmd]

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return f"Failed to launch terminal: {exc}"

    return None


def _launch_vscode(ssh_cmd: str, server_name: str) -> str | None:
    """Launch a detached VSCode window connecting to the remote. Returns error or None."""
    code_path = shutil.which("code")
    if not code_path:
        return "VSCode 'code' CLI not found. Install it from VSCode: Cmd+Shift+P → 'Shell Command: Install code command'"

    # vscode://vscode-remote/ssh-remote+user@host:port → code --remote ssh-remote+...
    # ssh_cmd is "ssh user@host -p port" — extract user@host:port
    parts = ssh_cmd.replace("ssh ", "").replace(" -p ", ":").split()
    remote = parts[0]  # user@host:port
    code_remote = f"ssh-remote+{remote}"

    try:
        subprocess.Popen(
            [code_path, "--new-window", "--remote", code_remote],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return f"Failed to launch VSCode: {exc}"

    return None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    config_path: str,
    interval: int = 10,
    ssh_timeout: int = 5,
) -> FastAPI:
    """Build and return the FastAPI application."""
    servers = load_servers(config_path)
    if not servers:
        raise SystemExit("No servers found in config.")

    # Build a lookup for fast access
    server_map: dict[str, ServerConfig] = {s.name: s for s in servers}

    app = FastAPI(title="GPU Server Dashboard", version="1.0.0")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    state = AppState(servers=servers, interval=interval, ssh_timeout=ssh_timeout)

    @app.on_event("startup")
    async def _start_background_probe():
        asyncio.create_task(_probe_loop(state))

    # ---- Routes -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "servers": state.servers,
                "server_count": len(state.servers),
                "interval": state.interval,
            },
        )

    @app.get("/api/servers")
    async def list_servers():
        return {
            s.name: {"host": s.host, "port": s.port, "user": s.user}
            for s in state.servers
        }

    @app.get("/api/metrics")
    async def get_metrics():
        async with state.cache_lock:
            return {
                name: m.model_dump()
                for name, m in state.metrics_cache.items()
            }

    @app.get("/api/stream")
    async def stream():
        """SSE endpoint — pushes metrics every interval seconds."""
        async def _event_generator():
            last_sent: float = 0
            while True:
                try:
                    await asyncio.wait_for(
                        state._update_event.wait(),
                        timeout=state.interval * 2,
                    )
                except asyncio.TimeoutError:
                    pass
                state._update_event.clear()

                async with state.cache_lock:
                    payload = {
                        name: m.model_dump()
                        for name, m in state.metrics_cache.items()
                    }
                    newest = max(
                        (m.timestamp for m in state.metrics_cache.values()),
                        default=0,
                    )

                if newest <= last_sent:
                    continue
                last_sent = newest

                yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/connect/{name}")
    async def connect_info(name: str):
        """Return SSH connection details for a server."""
        s = server_map.get(name)
        if not s:
            return JSONResponse({"error": f"Unknown server: {name}"}, status_code=404)
        ssh_cmd = f"ssh {s.user}@{s.host} -p {s.port}"
        return {
            "name": s.name,
            "ssh_cmd": ssh_cmd,
            "host": s.host,
            "port": s.port,
            "user": s.user,
        }

    @app.post("/api/terminal/{name}")
    async def open_terminal(name: str):
        """Launch a local terminal emulator connected to the server via SSH."""
        s = server_map.get(name)
        if not s:
            return JSONResponse({"error": f"Unknown server: {name}"}, status_code=404)

        ssh_cmd = f"ssh {s.user}@{s.host} -p {s.port}"
        err = await asyncio.to_thread(_launch_terminal, ssh_cmd)

        if err:
            return JSONResponse({"error": err, "ssh_cmd": ssh_cmd}, status_code=500)
        return {"ok": True, "ssh_cmd": ssh_cmd}

    @app.post("/api/vscode/{name}")
    async def open_vscode(name: str):
        """Launch a detached VSCode window connected to the server via Remote-SSH."""
        s = server_map.get(name)
        if not s:
            return JSONResponse({"error": f"Unknown server: {name}"}, status_code=404)

        ssh_cmd = f"ssh {s.user}@{s.host} -p {s.port}"
        err = await asyncio.to_thread(_launch_vscode, ssh_cmd, name)

        if err:
            return JSONResponse({"error": err, "ssh_cmd": ssh_cmd}, status_code=500)
        return {"ok": True, "ssh_cmd": ssh_cmd}

    return app


async def _probe_loop(state: AppState) -> None:
    """Background task: probe all servers on a fixed interval."""
    logger.info(
        "Probe loop started: %d servers, %ds interval, %ds timeout",
        len(state.servers), state.interval, state.ssh_timeout,
    )

    while True:
        start = time.monotonic()
        try:
            new_metrics = await probe_all_servers(
                state.servers, timeout=state.ssh_timeout,
            )
        except Exception:
            logger.exception("Probe cycle failed")
            await asyncio.sleep(state.interval)
            continue

        async with state.cache_lock:
            state.metrics_cache.update(new_metrics)
        state._update_event.set()

        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0, state.interval - elapsed))
