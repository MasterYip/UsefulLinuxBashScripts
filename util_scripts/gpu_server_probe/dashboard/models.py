"""Pydantic data models for server configuration and collected metrics."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Connection details for a single GPU server."""

    name: str
    host: str
    port: int = 22
    user: Optional[str] = None  # None = inherit from defaults
    identity_file: str = "~/.ssh/id_rsa"


class GpuInfo(BaseModel):
    """Metrics for a single GPU on a server."""

    index: int
    name: str
    utilization_gpu: float = 0.0  # 0-100 %
    utilization_memory: float = 0.0  # 0-100 %
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    temperature_gpu: Optional[float] = None
    power_draw_w: Optional[float] = None


class ServerMetrics(BaseModel):
    """All collected metrics for one server at a point in time."""

    server_name: str
    timestamp: float  # time.time()
    gpu_info: list[GpuInfo] = Field(default_factory=list)
    cpu_percent: float = 0.0  # 0-100
    ram_percent: float = 0.0  # 0-100
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    error: Optional[str] = None  # e.g. "Connection timeout"
