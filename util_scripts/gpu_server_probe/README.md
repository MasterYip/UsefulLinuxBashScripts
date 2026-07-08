# GPU Server Probe — Resource Dashboard

Real-time GPU, CPU, and RAM monitoring dashboard for multiple servers via SSH.
Two modes: **web dashboard** (browser) and **terminal TUI** (Rich).

## Prerequisites

- Python 3.10+
- SSH key-based access to all target servers (the servers must have your public key in `~/.ssh/authorized_keys`)

## Installation

```bash
cd util_scripts/gpu_server_probe
pip install -r requirements.txt
```

## Configuration

Edit `servers.yaml` to match your setup. The `defaults` block provides fallback values:

```yaml
defaults:
  user: your_ssh_user           # default SSH user
  identity_file: ~/.ssh/id_rsa  # default SSH key

servers:
  - name: MyServer-1
    host: 192.168.1.10
    port: 22                    # optional, defaults to 22
    # user and identity_file inherited from defaults

  - name: MyServer-2
    host: 192.168.1.11
    port: 22222
    user: custom_user           # override default user
    identity_file: ~/.ssh/custom_key  # override default key
```

The existing `servers.yaml` is pre-populated from `server.md`.

## Usage

### Web Dashboard

```bash
# Start on http://localhost:8080
./run_dashboard.py web --config servers_rp.yaml

# Custom port and probe interval
./run_dashboard.py web --port 9090 --interval 5 --ssh-timeout 8
```

Open your browser to the displayed address. The dashboard auto-refreshes via
Server-Sent Events — no manual refresh needed.

### Terminal TUI

```bash
./run_dashboard.py tui

# Faster refresh
./run_dashboard.py tui --interval 5
```

Press `Ctrl+C` to exit.

### Full CLI Help

```bash
./run_dashboard.py --help
./run_dashboard.py web --help
./run_dashboard.py tui --help
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--config PATH` | `servers.yaml` (next to script) | Path to server config |
| `--interval N` | `10` | Seconds between probe cycles |
| `--ssh-timeout N` | `5` | Per-server SSH timeout (seconds) |
| `--verbose, -v` | off | Enable debug logging |
| `--port N` (web only) | `8080` | HTTP listen port |
| `--host H` (web only) | `0.0.0.0` | HTTP bind address |

## How It Works

1. Reads server list from `servers.yaml`
2. Every `--interval` seconds, probes all servers **in parallel** via `asyncssh`
3. On each server, runs:
   - `nvidia-smi` for GPU utilization, memory, temperature, power
   - `top -bn2` for CPU usage
   - `free -b` for RAM usage
4. Results are displayed in a dark-themed dashboard with color-coded bars

## Dashboard Features

- 🟢🟡🔴 **Color-coded status**: green (<60%), yellow (<85%), red (≥85%)
- **GPU**: per-GPU utilization bar, memory used/total, temperature, power draw
- **CPU**: aggregate percentage with bar
- **RAM**: used/total GB with bar
- **Error handling**: unreachable servers show error cards with last-known data

## File Structure

```
gpu_server_probe/
├── server.md               # Server list reference (human-readable)
├── servers.yaml             # Machine-readable server config
├── requirements.txt         # Python dependencies
├── run_dashboard.py         # CLI entry point
├── README.md                # This file
└── dashboard/
    ├── __init__.py
    ├── models.py            # Pydantic data models
    ├── config.py            # YAML config loader
    ├── probe.py             # asyncssh parallel probing
    ├── web.py               # FastAPI + SSE web backend
    ├── tui.py               # Rich terminal dashboard
    └── templates/
        └── dashboard.html   # Self-contained web UI
```
