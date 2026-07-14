"""Collision-resistant identifier generation for PDS2 page routes."""

from __future__ import annotations

import secrets


def generate_route_id() -> str:
    """Return a non-semantic route ID using 128 bits of secure randomness."""
    return f"rt_{secrets.token_hex(16)}"
