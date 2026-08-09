from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    host: str
    port: int
    prod: bool


def get_runtime_config() -> RuntimeConfig:
    """Return the network settings for the current process environment."""
    prod = os.getenv("SYNAPSE_ENV", "dev").strip().lower() == "prod"
    default_host = "0.0.0.0" if prod else "127.0.0.1"
    default_port = 8000 if prod else 8082

    host = os.getenv("SYNAPSE_HOST", default_host).strip() or default_host
    raw_port = os.getenv("SYNAPSE_PORT", str(default_port)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("SYNAPSE_PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SYNAPSE_PORT must be an integer between 1 and 65535")

    return RuntimeConfig(host=host, port=port, prod=prod)
