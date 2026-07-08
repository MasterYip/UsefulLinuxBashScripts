"""Parallel SSH data collection from GPU servers using asyncssh."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import asyncssh

from .models import GpuInfo, ServerConfig, ServerMetrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Remote commands
# ---------------------------------------------------------------------------

GPU_CMD = (
    "nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,"
    "memory.used,memory.total,temperature.gpu,power.draw "
    "--format=csv,noheader,nounits"
)

CPU_CMD = "top -bn2 -d 0.5 | grep 'Cpu(s)' | tail -1"

RAM_CMD = "free -b | awk '/^Mem:/{print $2,$3,$4,$6,$7}'"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def probe_server(
    server: ServerConfig,
    timeout: int = 5,
) -> ServerMetrics:
    """Connect to *server* via SSH, collect GPU/CPU/RAM metrics.

    Parameters
    ----------
    server : ServerConfig
        Connection details.
    timeout : int
        SSH connection + command timeout in seconds.

    Returns
    -------
    ServerMetrics
        Collected metrics, or an error-bearing object on failure.
    """
    ts = time.time()
    try:
        async with asyncio.timeout(timeout):
            metrics = await _collect(server, ts)
    except asyncio.TimeoutError:
        return ServerMetrics(
            server_name=server.name,
            timestamp=ts,
            error=f"Timeout ({timeout}s)",
        )
    except (OSError, asyncssh.Error) as exc:
        return ServerMetrics(
            server_name=server.name,
            timestamp=ts,
            error=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected error probing %s", server.name)
        return ServerMetrics(
            server_name=server.name,
            timestamp=ts,
            error=f"{type(exc).__name__}: {exc}",
        )

    return metrics


async def probe_all_servers(
    servers: list[ServerConfig],
    timeout: int = 5,
    max_concurrent: int = 0,
) -> dict[str, ServerMetrics]:
    """Probe all servers in parallel.

    Parameters
    ----------
    servers : list[ServerConfig]
    timeout : int
        Per-server SSH timeout in seconds.
    max_concurrent : int
        Max concurrent connections (0 = no limit).

    Returns
    -------
    dict[str, ServerMetrics]
        Mapping of server name -> metrics.
    """
    sem = asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None

    async def _probe_one(s: ServerConfig) -> ServerMetrics:
        if sem:
            async with sem:
                return await probe_server(s, timeout=timeout)
        return await probe_server(s, timeout=timeout)

    tasks = [asyncio.create_task(_probe_one(s)) for s in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    metrics_map: dict[str, ServerMetrics] = {}
    for server, result in zip(servers, results):
        if isinstance(result, Exception):
            metrics_map[server.name] = ServerMetrics(
                server_name=server.name,
                timestamp=time.time(),
                error=f"{type(result).__name__}: {result}",
            )
        else:
            metrics_map[server.name] = result

    return metrics_map


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _collect(
    server: ServerConfig,
    ts: float,
) -> ServerMetrics:
    """Open one SSH connection and run all three metric commands."""
    conn_kwargs: dict = {}
    identity_file = server.identity_file or "~/.ssh/id_rsa"
    conn_kwargs["client_keys"] = [identity_file]
    conn_kwargs["known_hosts"] = None  # skip host-key verification

    async with asyncssh.connect(
        server.host,
        port=server.port,
        username=server.user,
        **conn_kwargs,
    ) as conn:
        gpu_raw, cpu_raw, ram_raw = await asyncio.gather(
            _run_remote(conn, GPU_CMD),
            _run_remote(conn, CPU_CMD),
            _run_remote(conn, RAM_CMD),
        )

    gpu_info = _parse_nvidia_smi(gpu_raw) if gpu_raw else []
    cpu_pct = _parse_cpu(cpu_raw) if cpu_raw else 0.0
    ram_pct, ram_used_gb, ram_total_gb = (
        _parse_ram(ram_raw) if ram_raw else (0.0, 0.0, 0.0)
    )

    return ServerMetrics(
        server_name=server.name,
        timestamp=ts,
        gpu_info=gpu_info,
        cpu_percent=cpu_pct,
        ram_percent=ram_pct,
        ram_used_gb=ram_used_gb,
        ram_total_gb=ram_total_gb,
    )


async def _run_remote(conn: asyncssh.SSHClientConnection, cmd: str) -> Optional[str]:
    """Run *cmd* on the remote connection and return stdout, or None on failure."""
    try:
        result = await conn.run(cmd, check=False)
        if result.exit_status == 0 and result.stdout:
            return result.stdout.strip()
        elif result.exit_status != 0:
            logger.debug(
                "Remote command exited %d: %s\nstderr: %s",
                result.exit_status,
                cmd[:80],
                (result.stderr or b"").decode(errors="replace")[:200],
            )
            return None
        return None
    except Exception:
        logger.debug("Remote command failed: %s", cmd[:80], exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_nvidia_smi(output: str) -> list[GpuInfo]:
    """Parse nvidia-smi CSV output into GpuInfo objects."""
    gpus: list[GpuInfo] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        try:
            gpus.append(
                GpuInfo(
                    index=int(parts[0]),
                    name=parts[1],
                    utilization_gpu=_float(parts[2]),
                    utilization_memory=_float(parts[3]),
                    memory_used_mb=_float(parts[4]),
                    memory_total_mb=_float(parts[5]),
                    temperature_gpu=_float_or_none(parts[6]),
                    power_draw_w=_float_or_none(parts[7]),
                )
            )
        except (ValueError, IndexError):
            logger.debug("Failed to parse nvidia-smi line: %s", line)
            continue
    return gpus


def _parse_cpu(output: str) -> float:
    """Extract total CPU usage percentage from 'top -bn2' output.

    Expected format:
        %Cpu(s):  5.2 us,  2.1 sy,  0.0 ni, 92.0 id,  0.5 wa,  0.0 hi,  0.2 si,  0.0 st
    Returns 100 - idle%.
    """
    # Look for the idle percentage
    import re

    idle_match = re.search(r"(\d+\.\d+)\s*id", output)
    if idle_match:
        idle_pct = float(idle_match.group(1))
        return round(100.0 - idle_pct, 1)
    return 0.0


def _parse_ram(output: str) -> tuple[float, float, float]:
    """Parse 'free -b' output.

    Returns (percent_used, used_gb, total_gb).
    """
    parts = output.split()
    if len(parts) < 5:
        return 0.0, 0.0, 0.0

    total_b = _float(parts[0])
    used_b = _float(parts[1])
    # free_b  = _float(parts[2])
    # buff_cache_b = _float(parts[3])
    available_b = _float(parts[4])

    total_gb = total_b / (1024**3)
    used_gb = (total_b - available_b) / (1024**3)  # "used" from OS perspective
    pct = ((total_b - available_b) / total_b * 100) if total_b > 0 else 0.0

    return round(pct, 1), round(used_gb, 1), round(total_gb, 1)


def _float(val: str) -> float:
    """Parse string to float, treating '[Not Supported]' etc. as 0."""
    try:
        return float(val)
    except ValueError:
        return 0.0


def _float_or_none(val: str) -> Optional[float]:
    """Parse string to float, returning None for unsupported values."""
    try:
        return float(val)
    except ValueError:
        return None
