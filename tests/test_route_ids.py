from __future__ import annotations

import inspect
import re

from pds_core.identifiers import is_valid_identifier
from pds_core.route_ids import generate_route_id
from pds_core.routing_models import PDS2_SCHEMA, ModuleWorkRef, RouteLocator


def test_generate_route_id_uses_canonical_safe_fixed_format() -> None:
    route_id = generate_route_id()

    assert re.fullmatch(r"rt_[0-9a-f]{32}", route_id)
    assert is_valid_identifier(route_id)
    assert inspect.signature(generate_route_id).parameters == {}


def test_generate_route_id_uses_16_random_bytes(monkeypatch: object) -> None:
    calls: list[int] = []

    def fake_token_hex(byte_count: int) -> str:
        calls.append(byte_count)
        return "0123456789abcdef0123456789abcdef"

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "pds_core.route_ids.secrets.token_hex", fake_token_hex
    )

    assert generate_route_id() == "rt_0123456789abcdef0123456789abcdef"
    assert calls == [16]


def test_repeated_route_ids_are_distinct() -> None:
    assert len({generate_route_id() for _ in range(16)}) == 16


def test_generated_route_id_is_accepted_by_route_locator() -> None:
    locator = RouteLocator(
        PDS2_SCHEMA,
        ModuleWorkRef("concord", "english10_p3", "seminar_1"),
        generate_route_id(),
    )
    assert locator.route_id.startswith("rt_")
