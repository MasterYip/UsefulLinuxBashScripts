"""FastAPI web dashboard with Server-Sent Events for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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


def create_app(
    config_path: str,
    interval: int = 10,
    ssh_timeout: int = 5,
) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    config_path : str
        Path to servers.yaml.
    interval : int
        Seconds between probe cycles.
    ssh_timeout : int
        Per-server SSH timeout in seconds.
    """
    servers = load_servers(config_path)
    if not servers:
        raise SystemExit("No servers found in config.")

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
            s.name: {
                "host": s.host,
                "port": s.port,
                "user": s.user,
            }
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
                # Wait for the probe loop to signal new data, or send
                # whatever we have after interval*2 (safety timeout).
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

                # Don't send duplicates if nothing changed
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

    return app


async def _probe_loop(state: AppState) -> None:
    """Background task: probe all servers on a fixed interval."""
    logger.info(
        "Probe loop started: %d servers, %ds interval, %ds timeout",
        len(state.servers),
        state.interval,
        state.ssh_timeout,
    )

    while True:
        start = time.monotonic()

        try:
            new_metrics = await probe_all_servers(
                state.servers,
                timeout=state.ssh_timeout,
            )
        except Exception:
            logger.exception("Probe cycle failed")
            await asyncio.sleep(state.interval)
            continue

        async with state.cache_lock:
            state.metrics_cache.update(new_metrics)

        state._update_event.set()

        elapsed = time.monotonic() - start
        sleep_for = max(0, state.interval - elapsed)
        logger.debug(
            "Probe cycle: %.1fs, sleeping %.1fs",
            elapsed,
            sleep_for,
        )
        await asyncio.sleep(sleep_for)
