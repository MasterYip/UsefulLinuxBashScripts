# GPU Server Resource Dashboard — Implementation Plan

## Context

The user has 12 GPU servers listed in `util_scripts/gpu_server_probe/server.md` (H20, H200, and 4090 GPUs across various IPs/ports). They want a dashboard that displays real-time GPU, CPU, and RAM usage for all servers via SSH. The user wants **both a web dashboard and a terminal TUI**, with server configuration in a **YAML file**.

## Architecture Overview

```
servers.yaml  ──► config.py ──► probe.py (asyncssh) ──► Remote Servers
                                     │
                                     ▼
                              metrics_cache (shared dict)
                                     │
                          ┌──────────┴──────────┐
                          ▼                      ▼
                    FastAPI + SSE           Rich TUI
                    (web dashboard)         (terminal)
```

Two modes, one codebase:
- `run_dashboard.py web` — starts FastAPI server on port 8080
- `run_dashboard.py tui` — launches interactive terminal dashboard using Rich

## File Structure

```
util_scripts/gpu_server_probe/
├── server.md                  # (existing) server list reference
├── servers.yaml               # machine-readable YAML config
├── requirements.txt           # Python dependencies
├── run_dashboard.py           # CLI entry point
└── dashboard/
    ├── __init__.py
    ├── config.py              # YAML loading + Pydantic validation
    ├── models.py              # ServerConfig, GpuInfo, ServerMetrics models
    ├── probe.py               # asyncssh parallel data collection
    ├── web.py                 # FastAPI app, SSE endpoint, background probe loop
    ├── tui.py                 # Rich-based terminal dashboard
    └── templates/
        └── dashboard.html     # Self-contained web dashboard (Jinja2 + JS)
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SSH library | **asyncssh** | Async-native, pairs with FastAPI event loop; 12 servers probed in parallel via `asyncio.gather` |
| Web framework | **FastAPI** | Async, built-in SSE support, clean API design |
| TUI library | **Rich** | Live auto-refresh, progress bars, color support, widely available |
| Frontend updates | **SSE (Server-Sent Events)** | Push-based real-time, simpler than WebSocket, browser auto-reconnects |
| Config format | **YAML** | Human-readable, supports comments, PyYAML trivial to parse |
| SSH timeout | **5 seconds** per server | Prevents one unreachable server from blocking the whole probe cycle |
| Probe interval | **10 seconds** | Good balance between freshness and SSH connection overhead |

## Data Collection Commands

Three commands run on each remote server (sequentially over one SSH connection):

| Metric | Command |
|--------|---------|
| GPU | `nvidia-smi --query-gpu=index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits` |
| CPU | `top -bn2 -d 0.5 \| grep 'Cpu(s)' \| tail -1` (two-iteration for accurate instantaneous measurement) |
| RAM | `free -b \| awk '/^Mem:/{print \$2,\$3,\$4,\$6,\$7}'` |

## YAML Config Schema

```yaml
defaults:
  user: user
  identity_file: ~/.ssh/id_rsa

servers:
  - name: H20-1
    host: 223.167.85.187
    port: 51820
    # user and identity_file inherited from defaults
  - name: H20-2
    host: 223.167.85.187
    port: 51821
  # ... 10 more
```

## Web Dashboard Layout

Dark-themed CSS Grid (4 columns → 2 on tablet → 1 on mobile). Each server card shows:
- Header: server name + colored status dot (🟢 online / 🟡 stale / 🔴 error)
- GPU rows: utilization bar (green < 60% < yellow < 85% < red), memory used/total, temperature
- CPU bar with percentage
- RAM bar with GB used/total + percentage
- Footer: "updated Xs ago"

Auto-refresh via SSE `EventSource` — JavaScript patches each card's DOM on every update.

## TUI Dashboard Layout

Rich `Live` display with:
- Header: "GPU Server Dashboard — [timestamp]"
- One panel per server in a grid/table layout
- GPU utilization as progress bars with color thresholds
- CPU/RAM as progress bars
- Error servers highlighted in red
- Auto-refresh every 10s

## Error Handling

| Failure | Behavior |
|---------|----------|
| Server unreachable / timeout | Card shows error state, retains last-known data with "stale (X min ago)" |
| SSH auth failed | "SSH auth failed" message |
| `nvidia-smi` not found | GPU section hidden, CPU/RAM still shown |
| Parse failure | Partial data shown, error logged to console |
| All servers down | All cards show red/error, timestamp freezes |

## Dependencies (`requirements.txt`)

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
asyncssh>=2.17.0
pydantic>=2.0
pyyaml>=6.0
jinja2>=3.1.0
rich>=13.0.0
```

## Implementation Order

1. **`servers.yaml`** — write the YAML config derived from server.md table
2. **`dashboard/models.py`** — Pydantic models (ServerConfig, GpuInfo, ServerMetrics)
3. **`dashboard/config.py`** — YAML loading with validation
4. **`dashboard/probe.py`** — asyncssh parallel probe logic with parse functions
5. **`dashboard/templates/dashboard.html`** — self-contained HTML with SSE JavaScript
6. **`dashboard/web.py`** — FastAPI app with SSE endpoint + background probe loop
7. **`dashboard/tui.py`** — Rich-based terminal dashboard
8. **`run_dashboard.py`** — CLI entry point with `web` and `tui` subcommands
9. **`requirements.txt`** — pinned dependencies

## Verification

1. Run `python run_dashboard.py web --port 8080` and open browser to verify dashboard loads
2. Run `python run_dashboard.py tui` to verify terminal dashboard refreshes
3. Temporarily set an unreachable server in YAML to verify error cards display correctly
4. Check that all 12 servers show data within a single probe cycle (~5s max)
