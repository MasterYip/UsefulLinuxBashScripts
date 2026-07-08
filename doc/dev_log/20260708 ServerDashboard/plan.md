
GPU Server Resource Dashboard -- Implementation Plan
1. Design Decisions (with rationale)
Web framework: FastAPI -- It is async-native, which means 12 SSH connections can run concurrently without thread-pool overhead. It has built-in SSE/WebSocket support for real-time updates and a clean API-first design. Flask requires extensions for async and lacks native background tasks. Streamlit is too opinionated (it re-runs the entire script on every interaction, which would mean 12 SSH connections per user refresh).

SSH library: asyncssh -- Pairs naturally with FastAPI's async event loop. All 12 servers can be probed in parallel with a single asyncio.gather() call. paramiko is synchronous and would require a ThreadPoolExecutor, adding complexity and resource overhead.

Data collection commands -- Three commands per server, run concurrently on the remote side:

Metric	Command
GPU	nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw,power.limit,clocks.current.sm,clocks.max.sm --format=csv,noheader,nounits
CPU	top -bn2 -d 0.5 | grep 'Cpu(s)' | tail -1 (two-iteration top for accurate instantaneous measurement)
RAM	free -b | awk '/^Mem:/{print $2,$3,$4,$6,$7}' (bytes, with buffers/cache for accurate "available" calculation)
The CPU command uses two iterations with a 0.5-second gap because the first iteration of top -bn1 shows averages since boot, not current usage. The fallback (if top is unavailable) is reading /proc/stat directly.

Frontend: Server-rendered HTML with Server-Sent Events (SSE) -- SSE gives push-based real-time updates without the complexity of WebSocket negotiation. The browser opens one SSE stream to /api/stream; the server pushes metrics every 10 seconds. This requires zero JavaScript dependencies. A single Jinja2 template renders the initial page; updates arrive as SSE events that patch DOM elements by server ID.

Configuration format: YAML -- More human-readable than JSON, supports comments, and uses less syntax noise. The initial YAML will be auto-generated from the existing server.md by a one-time parser script. The dashboard reads from YAML at startup.

Caching/refresh strategy: A background asyncio.Task runs on a 10-second loop. Each server gets a 5-second SSH timeout. Results are stored in a module-level dict (Dict[str, ServerMetrics]) keyed by server name. Each entry has a timestamp and error field. The SSE endpoint reads from this shared state. If a server fails to respond, the previous successful reading is shown with a "stale" indicator and the elapsed time since last success. After 60 seconds of staleness, the server card shows an error state.

2. File Structure

util_scripts/gpu_server_probe/
├── server.md                    # (existing) Human-readable server list
├── servers.yaml                 # Machine-readable config (generated once, hand-editable)
├── requirements.txt             # Python dependencies
├── run_dashboard.py             # CLI entry point: argparse, starts uvicorn
└── dashboard/
    ├── __init__.py              # Empty
    ├── app.py                   # FastAPI app, routes, SSE endpoint, background task
    ├── config.py                # Load/validate servers.yaml into Pydantic models
    ├── probe.py                 # asyncssh connection logic, remote command execution
    ├── models.py                # Pydantic models: ServerConfig, GpuInfo, ServerMetrics
    ├── templates/
    │   └── dashboard.html       # Full-page Jinja2 template with inline CSS + SSE JS
    └── parse_server_md.py       # One-time utility: extracts server list from server.md -> YAML
This follows the existing project convention: util_scripts/<feature>/ contains a flat directory of scripts plus a markdown doc. The dashboard/ sub-package keeps concerns separated without deep nesting.

3. Dependencies (requirements.txt)

fastapi>=0.115.0
uvicorn[standard]>=0.30.0
asyncssh>=2.17.0
pydantic>=2.0
pyyaml>=6.0
jinja2>=3.1.0        # (comes with fastapi, explicit for clarity)
Every dependency is pure Python -- no system packages needed. uvicorn[standard] includes uvloop and httptools for production-grade performance.

4. Architecture Diagram (text)

┌─────────────────────────────────────────────────────────────┐
│                     User's Browser                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  dashboard.html                                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ... x 12    │   │
│  │  │ Server   │  │ Server   │  │ Server   │            │   │
│  │  │ Card     │  │ Card     │  │ Card     │            │   │
│  │  │ H20-1    │  │ H20-2    │  │ H20-3    │            │   │
│  │  │ GPU: 85% │  │ GPU: 42% │  │ ERROR    │            │   │
│  │  │ CPU: 23% │  │ CPU: 67% │  │ OFFLINE  │            │   │
│  │  │ RAM: 45% │  │ RAM: 33% │  │          │            │   │
│  │  └─────────┘  └─────────┘  └─────────┘              │   │
│  │           ▲ SSE stream (text/event-stream)           │   │
│  └───────────┼──────────────────────────────────────────┘   │
└──────────────┼──────────────────────────────────────────────┘
               │  HTTP GET /api/stream
               ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server (app.py)                   │
│                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  SSE Endpoint     │◄───│  Shared State (module dict)  │   │
│  │  /api/stream      │    │  metrics_cache:              │   │
│  │  /api/metrics     │    │    "H20-1" -> ServerMetrics   │   │
│  │  /api/servers     │    │    "H20-2" -> ServerMetrics   │   │
│  │  / (dashboard)    │    │    "4090-1" -> ServerMetrics  │   │
│  └──────────────────┘    │    ... (12 entries)            │   │
│                          └──────────────┬───────────────┘   │
│                                         │                    │
│                          ┌──────────────▼───────────────┐   │
│                          │  Background Probe Loop        │   │
│                          │  (asyncio.create_task)        │   │
│                          │  every 10 seconds:            │   │
│                          │    asyncio.gather(            │   │
│                          │      probe_server("H20-1"),   │   │
│                          │      probe_server("H20-2"),   │   │
│                          │      ... x 12                 │   │
│                          │    )                          │   │
│                          └──────────────┬───────────────┘   │
└─────────────────────────────────────────┼───────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────┐
              │         probe.py          │                   │
              │                           ▼                   │
              │  async def probe_server(server) -> ServerMetrics
              │    1. asyncssh.connect(ip, port, key)         │
              │    2. conn.run("nvidia-smi ...")  ────────────┼──► H20-1:22
              │    3. conn.run("top -bn2 ...")    ────────────┼──► H20-2:22
              │    4. conn.run("free -b ...")     ────────────┼──► 4090-1:22
              │    5. Parse CSV/text into GpuInfo             │
              │    6. Return ServerMetrics                    │
              │    timeout=5s per server                      │
              │    on failure: return error fields            │
              └───────────────────────────────────────────────┘
5. Data Flow
Phase 1 -- Startup:

run_dashboard.py parses CLI args (--port, --interval, --config).
config.py reads servers.yaml, validates with Pydantic, returns list[ServerConfig].
app.py creates the FastAPI app, stores the server list, starts the background probe loop.
Uvicorn begins serving on 0.0.0.0:8080.
Phase 2 -- First probe:
5. Background task calls asyncio.gather(*[probe_server(s) for s in servers]).
6. probe.py opens 12 asyncssh connections in parallel.
7. On each server, it runs the three metrics commands (sequentially on that one connection, for simplicity).
8. Parses nvidia-smi CSV output into list[GpuInfo].
9. Parses top and free output into CPU and RAM percentages.
10. Wraps everything into a ServerMetrics Pydantic model with timestamp=now() and error=None.
11. On connection failure or timeout: creates ServerMetrics with error="Connection refused" and retains previous gpu_info/cpu_percent/ram_percent if available (stale data) or None if first attempt.

Phase 3 -- SSE delivery:
12. /api/stream is an EventSourceResponse (from sse-starlette or manual). It loops every interval seconds, serializes the full metrics_cache dict as JSON, and yields it as an SSE data: event.
13. The browser's EventSource receives the JSON, iterates over the server list, and updates each card's DOM elements (GPU bars, CPU/RAM bars, status badge, timestamp).

Phase 4 -- Subsequent probes (loop):
14. Step 5 repeats every 10 seconds. New data overwrites the cache. Stale messages in the SSE queue are dropped (check asyncio.Event pattern or compare timestamps before sending).

6. Component Responsibilities
run_dashboard.py -- CLI Entry Point
Follows the existing manage_wandb_space.py pattern exactly:


#!/usr/bin/env python3
"""Docstring with usage examples."""

import argparse

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--config", default="servers.yaml", help="Path to server config YAML")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--interval", type=int, default=10, help="Probe interval in seconds")
    parser.add_argument("--ssh-timeout", type=int, default=5, help="SSH connection timeout per server")
    args = parser.parse_args()
    uvicorn.run("dashboard.app:create_app", ...)

if __name__ == "__main__":
    main()
config.py -- Configuration
load_servers(path: str) -> list[ServerConfig]: reads YAML, validates each entry.
parse_server_md(path: str) -> list[ServerConfig]: regex-based extraction from the existing markdown table (used by parse_server_md.py utility).
YAML schema:

servers:
  - name: H20-1
    host: 223.167.85.187
    port: 51820
    user: user                    # optional, defaults to current user
    identity_file: ~/.ssh/id_rsa  # optional, defaults to ~/.ssh/id_rsa
    tags: [h20]                   # optional, for future filtering
  - name: H20-2
    host: 223.167.85.187
    port: 51821
  # ... 10 more
models.py -- Pydantic Data Models

class ServerConfig(BaseModel):
    name: str
    host: str
    port: int = 22
    user: str | None = None
    identity_file: str = "~/.ssh/id_rsa"
    tags: list[str] = []

class GpuInfo(BaseModel):
    index: int
    name: str
    utilization_gpu: float       # 0-100 percentage
    utilization_memory: float    # 0-100 percentage
    memory_used_mb: float
    memory_total_mb: float
    temperature_gpu: float | None
    power_draw_w: float | None
    power_limit_w: float | None
    clock_sm_mhz: float | None
    clock_max_sm_mhz: float | None

class ServerMetrics(BaseModel):
    server_name: str
    timestamp: float             # time.time() when collected
    gpu_info: list[GpuInfo]
    cpu_percent: float           # 0-100
    ram_percent: float           # 0-100
    ram_used_gb: float
    ram_total_gb: float
    error: str | None = None     # e.g. "Connection timeout", "Permission denied"
probe.py -- SSH Data Collection

async def probe_server(server: ServerConfig, timeout: int = 5) -> ServerMetrics:
    """Connect to server via SSH, collect GPU/CPU/RAM metrics."""

async def _run_remote_command(conn, cmd: str) -> str:
    """Execute a command on the remote and return stdout as string."""

def _parse_nvidia_smi(output: str) -> list[GpuInfo]:
    """Parse nvidia-smi CSV output into GpuInfo objects."""

def _parse_cpu(output: str) -> float:
    """Extract CPU usage percentage from 'top -bn2' output."""

def _parse_ram(output: str) -> tuple[float, float, float]:
    """Extract RAM used/total bytes and compute percentage from 'free -b' output."""
Error handling within probe_server:

ConnectionRefusedError / OSError / TimeoutError from asyncssh: caught, returned as ServerMetrics(error="<type>: <message>")
Command failure (non-zero exit): logged, returned as ServerMetrics(error="nvidia-smi not found") or similar
Parse failure: logged, partial data returned with error="Failed to parse nvidia-smi output"
app.py -- FastAPI Application

def create_app(config_path: str, interval: int, ssh_timeout: int) -> FastAPI:
    """Factory function: loads config, wires routes, starts background task."""
Routes:

GET / -- renders dashboard.html with initial servers list as template context (for card generation).
GET /api/metrics -- returns JSON snapshot of current metrics_cache.
GET /api/servers -- returns the server configuration list.
GET /api/stream -- SSE endpoint. Uses starlette.responses.StreamingResponse with text/event-stream content type. Loops every interval seconds, sends current cache as JSON event.
Background task (_probe_loop):

Runs while True with asyncio.sleep(interval).
Calls asyncio.gather(*[probe_server(s, ssh_timeout) for s in servers], return_exceptions=True).
Updates metrics_cache dict. On return_exceptions=True, exceptions become ServerMetrics(error=str(exc)).
Application state is held in a simple dataclass or module-level variables (consistent with the script-oriented style of the existing codebase):


class AppState:
    servers: list[ServerConfig]
    metrics_cache: dict[str, ServerMetrics]
    cache_lock: asyncio.Lock   # prevents concurrent read/write
dashboard.html -- Frontend Template
A single self-contained HTML file. Design:


┌─────────────────────────────────────────────────────────────────┐
│  GPU Server Dashboard                    [Auto-refresh: ON]     │
│  Last update: 2026-07-08 14:32:15                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ● H20-1      │  │ ● H20-2      │  │ ● H200-1     │    ...   │
│  │   ONLINE     │  │   ONLINE     │  │   ONLINE     │          │
│  │              │  │              │  │              │          │
│  │ GPU 0: ████  │  │ GPU 0: ██░░  │  │ GPU 0: █████ │          │
│  │  H20  85%    │  │  H20  42%    │  │  H200 97%    │          │
│  │ Mem: 68/96G  │  │ Mem: 35/96G  │  │ Mem: 90/141G │          │
│  │ GPU 1: ██░░  │  │ GPU 1: ████  │  │ GPU 1: ████  │          │
│  │  H20  38%    │  │  H20  82%    │  │  H200 71%    │          │
│  │ Mem: 22/96G  │  │ Mem: 78/96G  │  │ Mem: 100/141G│          │
│  │              │  │              │  │              │          │
│  │ CPU: ██░░ 45%│  │ CPU: ███░ 67%│  │ CPU: ███░ 72%│          │
│  │ RAM: ██░░ 38%│  │ RAM: ██░░ 33%│  │ RAM: ███░ 55%│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐                              │
│  │ ⬤ 4090-5     │  │ ● H20-3      │                             │
│  │   OFFLINE    │  │   ONLINE     │                             │
│  │ Connection   │  │ ...          │                             │
│  │ timeout      │  │              │                             │
│  │ (2 min ago)  │  │              │                             │
│  └──────────────┘  └──────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
Cards are arranged in a CSS Grid: 4 columns on wide screens, 2 on tablets, 1 on mobile. Each card has:

Header bar: server name + colored status dot (green=OK, yellow=stale, red=error)
GPU section: one row per GPU with utilization bar (color-coded: green < 60%, yellow < 85%, red >= 85%), memory used/total, temperature badge
CPU bar: horizontal bar with percentage
RAM bar: horizontal bar with percentage and used/total in GB
Footer: "updated 3s ago" timestamp
The SSE JavaScript:


const evtSource = new EventSource("/api/stream");
evtSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    for (const [serverName, metrics] of Object.entries(data)) {
        updateServerCard(serverName, metrics);
    }
    document.getElementById("last-update").textContent = new Date().toLocaleTimeString();
};

function updateServerCard(name, metrics) {
    const card = document.getElementById(`card-${name}`);
    if (metrics.error) {
        card.classList.add("error");
        card.querySelector(".error-msg").textContent = metrics.error;
    } else {
        card.classList.remove("error");
        // Update GPU bars, CPU bar, RAM bar, timestamp
    }
}
No external CSS or JS frameworks. All CSS is inline or in a <style> block. The design uses the dataviz skill conventions if the user wants it, but the default color scheme is:

Background: #0d1117 (dark)
Card: #161b22 with #30363d border
Green: #3fb950
Yellow: #d29922
Red: #f85149
Text: #c9d1d9
7. Error Handling Strategy
Failure Mode	Detection	User-Facing Behavior
Server offline / unreachable	ConnectionRefusedError, timeout after 5s	Card turns red, shows "Connection refused" or "Timeout", retains last-known data with "stale (X min ago)"
SSH key missing or invalid	PermissionError from asyncssh	Card shows "SSH auth failed: check ~/.ssh/id_rsa"
nvidia-smi not found	Command exits non-zero	GPU section shows "No GPU / nvidia-smi not found", CPU and RAM still display normally
nvidia-smi output format changed	CSV parse raises ValueError	GPU section shows "Parse error", raw output available in browser console
All servers down	All 12 probes return errors	Dashboard shows all cards in red/error state, last-update time freezes
Browser loses connection	EventSource onerror fires	Browser auto-reconnects (native EventSource behavior), cards show stale data with timestamp until reconnected
Single slow server	5s timeout per server, parallel execution	Other 11 cards update normally, slow server shows timeout error with stale data
8. Implementation Sequence
Step 1: Create servers.yaml and parse_server_md.py

Write the one-time parser that reads server.md, regex-extracts the table rows (name, IP, port), and writes servers.yaml.
Manually verify the output and add any missing fields (user, identity_file).
Step 2: Create models.py

Define ServerConfig, GpuInfo, ServerMetrics as Pydantic models.
This file has zero dependencies on other dashboard modules, so it can be tested in isolation.
Step 3: Create config.py

load_servers() function using yaml.safe_load and Pydantic validation.
parse_server_md() function for the utility script.
Step 4: Create probe.py

probe_server() with asyncssh, timeout handling, and command execution.
Individual _parse_*() functions.
Test manually against one server first using python -c "import asyncio; from dashboard.probe import ...".
Step 5: Create app.py

FastAPI app factory with SSE endpoint, background task, and state management.
Start with hardcoded config for testing, then wire in CLI args.
Step 6: Create dashboard.html

Jinja2 template with inline CSS grid, status dots, progress bars, and SSE JavaScript.
Test with fake/static data first to get layout right.
Step 7: Create run_dashboard.py

Argparse CLI that mirrors the existing manage_wandb_space.py pattern.
Wires everything together and calls uvicorn.run().
Step 8: Create requirements.txt

List the four dependencies with version pins.
9. Potential Challenges and Mitigations
Challenge	Mitigation
12 concurrent SSH connections may overload the client machine's SSH agent	Use known_hosts=None in asyncssh to skip host key verification for internal-network servers; configurable via YAML
nvidia-smi CSV output differs across driver versions	The query uses named fields that are stable across driver versions since ~450.x; add a --query-gpu fallback that tries older field names on parse failure
Running the dashboard on a machine without nvidia-smi (e.g., operator's laptop) is fine since commands run on the remote servers only	No action needed
Browser tab left open for days accumulates stale SSE events	SSE endpoint checks if the client is still connected before yielding; use await asyncio.sleep() with asyncio.Event that is set() when new metrics arrive, so the loop only sends when there is new data
Different server types (H20 vs H200 vs 4090) have different GPU counts, memory sizes, and nvidia-smi field availability	The Pydantic models use Optional for all fields; the template iterates gpu_info dynamically, so 1-GPU and 8-GPU servers both render correctly
Critical Files for Implementation
/home/user/CodeSpace/Utils/UsefulLinuxBashScripts/util_scripts/gpu_server_probe/dashboard/app.py
/home/user/CodeSpace/Utils/UsefulLinuxBashScripts/util_scripts/gpu_server_probe/dashboard/probe.py
/home/user/CodeSpace/Utils/UsefulLinuxBashScripts/util_scripts/gpu_server_probe/dashboard/models.py
/home/user/CodeSpace/Utils/UsefulLinuxBashScripts/util_scripts/gpu_server_probe/dashboard/templates/dashboard.html
/home/user/CodeSpace/Utils/UsefulLinuxBashScripts/util_scripts/gpu_server_probe/run_dashboard.py