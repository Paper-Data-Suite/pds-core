"""Build the deterministic pds-core v0.6.1 grouping-signal fixture asset."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ARCHIVE_NAME = "pds-core-0.6.1-grouping-signal-fixtures.zip"
ARCHIVE_PREFIX = "grouping_signals_v1"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _manifest_entries(fixture_root: Path) -> dict[str, str]:
    manifest_path = fixture_root / "SHA256SUMS.txt"
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="ascii").splitlines(), start=1
    ):
        try:
            digest, relative_path = line.split("  ", maxsplit=1)
        except ValueError as error:
            raise ValueError(
                f"Malformed fixture checksum line {line_number}."
            ) from error
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(
                f"Malformed fixture SHA-256 at line {line_number}."
            )
        if relative_path in entries:
            raise ValueError(f"Duplicate fixture path {relative_path!r}.")
        entries[relative_path] = digest
    return entries


def verify_fixture_directory(fixture_root: Path) -> tuple[Path, ...]:
    """Verify the tracked fixture manifest and return sorted fixture files."""
    entries = _manifest_entries(fixture_root)
    files = tuple(
        sorted(
            (
                path
                for path in fixture_root.rglob("*")
                if path.is_file() and path.name != "SHA256SUMS.txt"
            ),
            key=lambda path: path.relative_to(fixture_root).as_posix(),
        )
    )
    actual_paths = {path.relative_to(fixture_root).as_posix() for path in files}
    if actual_paths != set(entries):
        missing = sorted(set(entries) - actual_paths)
        untracked = sorted(actual_paths - set(entries))
        raise ValueError(
            "Fixture checksum manifest does not match directory contents: "
            f"missing={missing}, untracked={untracked}."
        )
    for path in files:
        relative = path.relative_to(fixture_root).as_posix()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entries[relative]:
            raise ValueError(f"Fixture checksum mismatch for {relative}.")
    return files


def build_archive(fixture_root: Path, output_path: Path) -> Path:
    """Create a deterministic fixture ZIP with fixed file metadata."""
    files = verify_fixture_directory(fixture_root)
    all_files = files + (fixture_root / "SHA256SUMS.txt",)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(
            all_files, key=lambda item: item.relative_to(fixture_root).as_posix()
        ):
            relative = path.relative_to(fixture_root).as_posix()
            info = zipfile.ZipInfo(
                filename=f"{ARCHIVE_PREFIX}/{relative}",
                date_time=FIXED_ZIP_TIME,
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/grouping_signals/v1"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist") / ARCHIVE_NAME,
    )
    args = parser.parse_args()
    output = build_archive(args.fixtures, args.output)
    print(output)
    print(hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
