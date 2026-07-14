# SSH Reverse Tunnel — Exposing a Local Service via a Remote Server

## Quick SOP

> Replace anything in `<angle brackets>` with your own values.

### One-Time Server Setup (requires sudo, do once per server)

```bash
# 1. Enable GatewayPorts on the server
ssh <user>@<server_ip> -p <ssh_port> \
  'sudo sed -i "s/^#GatewayPorts no/GatewayPorts clientspecified/" /etc/ssh/sshd_config && sudo systemctl restart sshd'

# 2. Ensure the remote port is in the firewall allow list (check first, add if missing)
ssh <user>@<server_ip> -p <ssh_port> 'sudo ufw status | grep <remote_port>'
ssh <user>@<server_ip> -p <ssh_port> 'sudo ufw allow <remote_port>/tcp'
```

### Open the Tunnel (run on your local machine)

```bash
# One-liner — replace <remote_port> and <local_port>
ssh -N -R 0.0.0.0:<remote_port>:localhost:<local_port> \
  -o ServerAliveInterval=60 \
  -o ExitOnForwardFailure=yes \
  -i ~/.ssh/id_rsa \
  -p <ssh_port> \
  <user>@<server_ip>
```

### Verify

```bash
# On server: check port is listening on 0.0.0.0 (not 127.0.0.1)
ssh <user>@<server_ip> -p <ssh_port> 'ss -tlnp | grep <remote_port>'

# From any device:
curl http://<server_ip>:<remote_port>/
```

Your service is now reachable at **`http://<server_ip>:<remote_port>/`**.

### Persistent Tunnel (systemd, survives reboots)

Create `/etc/systemd/system/ssh-tunnel-<name>.service` on your **local** machine:

```ini
[Unit]
Description=SSH Reverse Tunnel — <name>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<local_user>
ExecStart=/usr/bin/ssh \
  -N \
  -R 0.0.0.0:<remote_port>:localhost:<local_port> \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -o IdentityFile=/home/<local_user>/.ssh/id_rsa \
  -p <ssh_port> \
  <user>@<server_ip>
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ssh-tunnel-<name>
```

---

## How It Works

You have a service on your local machine (e.g., a dashboard on `localhost:<local_port>`)
behind NAT with no public IP. You own a remote server with a public IP.
An SSH reverse tunnel listens on the **remote** server and forwards all incoming
connections back through the SSH pipe to your **local** service.

```
Internet client  --->  Server:<remote_port>  ---(SSH tunnel)--->  Localhost:<local_port>
```

This is `ssh -R` (remote port forwarding). Compare with `ssh -L` (local forwarding),
which does the opposite — listens locally and forwards to the remote side.

### The Core Command

```bash
ssh -N -R [BIND_ADDRESS:]<remote_port>:localhost:<local_port> <user>@<server>
```

| Flag / Argument | Meaning |
|---|---|
| `-N` | Do not execute a remote command; only forward ports. |
| `-R` | Create a **remote** (reverse) tunnel. |
| `BIND_ADDRESS` | IP the remote side binds to. Defaults to `localhost` (loopback only). |
| `<remote_port>` | Port on the server that clients connect to. |
| `<local_port>` | Port your local service listens on. |
| `-f` | (Optional) Fork to background after authentication. |

### Concrete Example

```bash
ssh -N -R 0.0.0.0:39090:localhost:9090 user@server
```

This makes port `39090` on every network interface of the server (`0.0.0.0`) forward
incoming connections back through the tunnel to `localhost:9090` on your machine.

---

## The `GatewayPorts` Problem

By default, most SSH servers set `GatewayPorts no`, which forces `BIND_ADDRESS` to
`127.0.0.1` regardless of what you specify. The tunnel only listens on the server's
loopback interface, making it unreachable from the internet.

### Fix on the server

Edit `/etc/ssh/sshd_config`:

```ini
# Before (default):
#GatewayPorts no

# After:
GatewayPorts clientspecified
```

Then restart sshd:

```bash
sudo systemctl restart sshd
```

### GatewayPorts values

| Value | Behavior |
|---|---|
| `no` | All `-R` binds are forced to `localhost` (safe but useless for public exposure). |
| `clientspecified` | The client (`ssh -R`) decides the bind address. Use `0.0.0.0` for public exposure. |
| `yes` | All `-R` binds default to `0.0.0.0`. Less granular — avoid. |

Prefer `clientspecified` for explicit control.

---

## Firewall

The remote port must be allowed through the server's firewall:

```bash
# ufw
sudo ufw status
sudo ufw allow <remote_port>/tcp

# iptables
sudo iptables -L INPUT -n | grep <remote_port>
sudo iptables -A INPUT -p tcp --dport <remote_port> -j ACCEPT

# firewalld
sudo firewall-cmd --add-port=<remote_port>/tcp --permanent
sudo firewall-cmd --reload
```

---

## Keeping the Tunnel Alive

A bare `ssh -R` dies on network hiccups. Two approaches:

### Option 1: autossh

```bash
sudo apt install autossh

autossh -M 0 \
  -o "ServerAliveInterval=60" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -N -R 0.0.0.0:<remote_port>:localhost:<local_port> <user>@<server>
```

- `-M 0` — disable the monitoring port (let ServerAlive handle keepalive).
- `ServerAliveInterval=60` — send a keepalive every 60 seconds.
- `ServerAliveCountMax=3` — disconnect after 3 consecutive missed keepalives.
- `ExitOnForwardFailure=yes` — fail immediately if the port is unavailable.
- autossh restarts the process if the SSH connection dies.

### Option 2: systemd service

See the SOP section above for the unit file template.

---

## SSH Config Shortcut

Add to `~/.ssh/config`:

```
Host tunnel-<name>
  HostName <server_ip>
  Port <ssh_port>
  User <user>
  IdentityFile ~/.ssh/id_rsa
  RemoteForward 0.0.0.0:<remote_port> localhost:<local_port>
  ServerAliveInterval 60
  ServerAliveCountMax 3
  ExitOnForwardFailure yes
  SessionType none
```

Then:

```bash
ssh -N tunnel-<name>
```

---

## Verification

### On the server

```bash
ss -tlnp | grep <remote_port>

# Expected — note 0.0.0.0, not 127.0.0.1:
# LISTEN  0  128  0.0.0.0:<remote_port>  0.0.0.0:*  users:(("sshd",pid=...,fd=...))
```

If it shows `127.0.0.1:<remote_port>`, `GatewayPorts` is not working.

### From another machine

```bash
curl http://<server_ip>:<remote_port>/
```

---

## Security Considerations

- Everyone who can reach the server's port can reach your local service. There is **no
  authentication** at the port-forward level.
- Restrict source IPs in the firewall if only specific clients need access:
  ```bash
  sudo ufw allow from <trusted_ip> to any port <remote_port> proto tcp
  ```
- Keep your service's own auth layer enabled (HTTP basic auth, OAuth, etc.).
- Prefer `clientspecified` over `yes` for `GatewayPorts` — each tunnel should explicitly
  opt into public exposure.
- Use a non-standard SSH port to reduce automated-attack noise.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ssh: connect to host ... Connection refused` | Wrong SSH port or sshd not running | Verify `-p <port>` and `systemctl status sshd` |
| `remote port forwarding failed for listen port` | Port already in use or GatewayPorts disabled | Check `ss -tlnp`, verify GatewayPorts |
| Tunnel works but only from server itself | GatewayPorts is `no` — listening on `127.0.0.1` | Set `GatewayPorts clientspecified` and restart sshd |
| Tunnel dies after a few minutes | NAT timeout or idle connection dropped | Use `ServerAliveInterval=60` or autossh |
| `Warning: remote port forwarding failed` | ExitOnForwardFailure working as intended | Free the port or pick a different one on the server |
