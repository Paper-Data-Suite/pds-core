"""Build the non-release Core 0.6.2 compatibility candidate for issue #195."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.released_consumer_compatibility import (  # noqa: E402
    ProvisionalCandidateError,
    build_provisional_candidate,
    provisional_result_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a provisional pds-core 0.6.2 wheel from a temporary copy of "
            "the current source without changing committed package version metadata."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="pds-core working tree (default: repository containing this script)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        required=True,
        help="empty/safe output directory for the provisional wheel and evidence JSON",
    )
    args = parser.parse_args()
    try:
        result = build_provisional_candidate(args.repo_root, args.outdir)
    except ProvisionalCandidateError as error:
        parser.exit(1, f"provisional candidate build failed: {error}\n")

    evidence = args.outdir.resolve() / "pds_core-0.6.2-provisional-evidence.json"
    evidence.write_bytes(provisional_result_json(result))
    print("pds-core 0.6.2 provisional compatibility candidate: PASS")
    print(f"source commit: {result.source_commit}")
    print(f"source runtime tree sha256: {result.source_runtime_tree_sha256}")
    print(f"wheel: {result.wheel}")
    print(f"wheel sha256: {result.wheel_sha256}")
    print(f"evidence: {evidence}")
    print("status: PROVISIONAL / NON-RELEASE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
