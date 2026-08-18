"""Write deterministic SHA-256 checksums for final pds-core v0.6.1 assets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist/SHA256SUMS.txt"))
    args = parser.parse_args()

    files = tuple(sorted(args.files, key=lambda path: path.name))
    if len({path.name for path in files}) != len(files):
        raise ValueError("Release artifact filenames must be unique.")
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in files
    )
    args.output.write_text(content, encoding="ascii", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
