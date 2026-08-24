"''Write deterministic SHA-256 checksums for exact pds-core v0.6.3 artifacts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Final

WHEEL_NAME: Final[str] = "pds_core-0.6.3-py3-none-any.whl"
SDIST_NAME: Final[str] = "pds_core-0.6.3.tar.gz"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(wheel: Path, sdist: Path, output: Path) -> Path:
    """Write checksums for the exact wheel/sdist pair and return the output path."""
    artifacts = (wheel.resolve(), sdist.resolve())
    expected_names = {WHEEL_NAME, SDIST_NAME}
    actual_names = {path.name for path in artifacts}
    if actual_names != expected_names:
        raise ValueError(
            f"Release artifacts must be exactly {sorted(expected_names)!r}; "
            f"received {sorted(actual_names)!r}."
        )
    for path in artifacts:
        if not path.is_file():
            raise FileNotFoundError(path)

    destination = output.resolve()
    if destination in artifacts:
        raise ValueError("Checksum output must not overwrite a release artifact.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        f"{_sha256_file(path)}  {path.name}\n"
        for path in sorted(artifacts, key=lambda item: item.name)
    )
    destination.write_text(content, encoding="ascii", newline="\n")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/SHA256SUMS.txt"),
    )
    args = parser.parse_args()

    output = write_checksums(args.wheel, args.sdist, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
