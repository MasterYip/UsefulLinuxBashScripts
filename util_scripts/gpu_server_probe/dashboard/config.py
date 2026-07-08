"""Load and validate server configuration from YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

from .models import ServerConfig


def load_servers(config_path: str) -> list[ServerConfig]:
    """Load server list from a YAML config file.

    Merges per-server fields with ``defaults`` block.
    """
    raw = _read_yaml(config_path)

    defaults: dict = raw.get("defaults", {})
    default_user: Optional[str] = defaults.get("user")
    default_key: str = os.path.expanduser(
        defaults.get("identity_file", "~/.ssh/id_rsa")
    )

    servers: list[ServerConfig] = []
    for entry in raw.get("servers", []):
        merged = {
            "user": default_user,
            "identity_file": default_key,
            **entry,
        }
        # Expand ~ in identity_file if per-server override was given
        merged["identity_file"] = os.path.expanduser(merged["identity_file"])
        servers.append(ServerConfig(**merged))

    return servers


def _read_yaml(path: str) -> dict:
    """Read and parse a YAML file, with helpful error messages."""
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {path}")
    except yaml.YAMLError as exc:
        raise SystemExit(f"Invalid YAML in {path}: {exc}")

    if data is None:
        raise SystemExit(f"Config file is empty: {path}")
    if "servers" not in data:
        raise SystemExit(
            f"Config file {path} must contain a 'servers' list."
        )

    return data
