"""Standalone installed-wheel probe for one exact released Core consumer."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import re
from pathlib import Path
from typing import Final, cast

EXPECTED_CORE_VERSION: Final[str] = "0.6.2"
_PROVIDER_KINDS: Final[tuple[tuple[str, str], ...]] = (
    ("routing_module", "routing_target"),
    ("publication_producer", "publication_target"),
    ("module_operations", "module_operations_target"),
)


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _outside_checkout(module_file: str | None, forbidden_root: Path, label: str) -> None:
    _require(module_file is not None, f"{label} package has no __file__.")
    assert module_file is not None
    path = Path(module_file).resolve()
    _require(
        not path.is_relative_to(forbidden_root),
        f"{label} resolved from the Core source checkout.",
    )


def _provider_probe(
    *,
    component_id: str,
    distribution: str,
    kind: str,
    expected_target: str | None,
) -> str:
    from pds_core.provider_diagnostics import (
        ProviderKind,
        diagnose_core_providers,
        inspect_core_provider_entry_points,
    )

    provider_kind = cast(ProviderKind, kind)
    metadata_rows = inspect_core_provider_entry_points(provider_kind=provider_kind)
    diagnostic_rows = diagnose_core_providers(provider_kind=provider_kind)
    if expected_target is None:
        _require(
            metadata_rows == (),
            f"unexpected installed {kind} provider metadata.",
        )
        _require(
            diagnostic_rows == (),
            f"unexpected installed {kind} provider diagnostics.",
        )
        return "absent"

    _require(len(metadata_rows) == 1, f"expected exactly one {kind} provider.")
    metadata = metadata_rows[0]
    _require(
        metadata.entry_point_name == component_id,
        f"{kind} entry-point identity mismatch.",
    )
    _require(
        metadata.entry_point_target == expected_target,
        f"{kind} entry-point target mismatch.",
    )
    _require(
        metadata.distribution_name is not None
        and _canonical_distribution_name(metadata.distribution_name)
        == _canonical_distribution_name(distribution),
        f"{kind} provider distribution mismatch.",
    )
    _require(len(diagnostic_rows) == 1, f"expected one {kind} diagnostic result.")
    diagnostic = diagnostic_rows[0]
    _require(diagnostic.code == "provider.valid", f"{kind} provider is not valid.")
    _require(diagnostic.stage == "valid", f"{kind} provider did not reach valid stage.")
    _require(
        diagnostic.validated_profile is not None,
        f"{kind} provider has no validated profile.",
    )
    return "valid"


def run_probe(args: argparse.Namespace) -> dict[str, object]:
    """Run installed public-contract checks and return path-free evidence."""
    import pds_core

    forbidden_root = args.forbidden_root.resolve()
    _require(
        importlib.metadata.version("pds-core") == EXPECTED_CORE_VERSION,
        "installed Core distribution version mismatch.",
    )
    _require(
        pds_core.__version__ == EXPECTED_CORE_VERSION,
        "installed pds_core.__version__ mismatch.",
    )
    _outside_checkout(pds_core.__file__, forbidden_root, "pds_core")

    consumer_module = importlib.import_module(args.import_name)
    _require(
        importlib.metadata.version(args.distribution) == args.version,
        "installed consumer distribution version mismatch.",
    )
    _outside_checkout(
        getattr(consumer_module, "__file__", None),
        forbidden_root,
        args.component_id,
    )

    provider_results: dict[str, str] = {}
    for kind, attribute in _PROVIDER_KINDS:
        provider_results[kind] = _provider_probe(
            component_id=args.component_id,
            distribution=args.distribution,
            kind=kind,
            expected_target=getattr(args, attribute),
        )

    return {
        "component_id": args.component_id,
        "consumer_version": args.version,
        "core_version": EXPECTED_CORE_VERSION,
        "consumer_import": "pass",
        "core_import": "pass",
        "providers": provider_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-id", required=True)
    parser.add_argument("--distribution", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--import-name", required=True)
    parser.add_argument("--forbidden-root", type=Path, required=True)
    parser.add_argument("--routing-target")
    parser.add_argument("--publication-target")
    parser.add_argument("--module-operations-target")
    args = parser.parse_args()
    try:
        result = run_probe(args)
    except Exception as error:
        parser.exit(1, f"installed released-consumer probe failed: {error}\n")
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
