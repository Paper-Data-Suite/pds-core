"""Issue #232: test an installed Core wheel and a real Windows junction.

Run with the *installed wheel's* Python using -I outside the Core checkout.
This is a non-GUI check: it intercepts the shell dispatch, not the viewer.
Physical PDF/HTML/Explorer display is a separate manual qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import sys
import tempfile

from pds_core import __version__, local_open
from pds_core.local_open import open_local_path


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def _deep_parent(root: Path) -> Path:
    target = root
    while local_open._windows_path_units(target) <= 280:
        target /= "synthetic-review-folder"
    target.mkdir(parents=True)
    return target


def _check_windows_junction() -> None:
    with tempfile.TemporaryDirectory(prefix="core232-wheel-") as tmp:
        root = Path(tmp)
        canonical = _deep_parent(root / "workspace") / "synthetic.pdf"
        data = b"%PDF-1.4\n% Synthetic release qualification only\n%%EOF\n"
        canonical.write_bytes(data)
        digest = hashlib.sha256(canonical.read_bytes()).digest()
        dispatched: list[Path] = []
        original = getattr(os, "startfile")
        setattr(os, "startfile", lambda target: dispatched.append(Path(target)))
        try:
            result = open_local_path(canonical)
        finally:
            setattr(os, "startfile", original)
        alias = dispatched[0] if len(dispatched) == 1 else None
        try:
            _check(result == canonical.resolve(), "Canonical API result changed")
            _check(alias is not None, "Expected exactly one shell handoff")
            assert alias is not None
            _check(alias != canonical, "Deep file did not use a short alias")
            _check(
                local_open._windows_path_units(alias) <= 240,
                "Shell alias exceeded the documented path budget",
            )
            _check(alias.is_file(), "Alias not accessible after handoff")
            _check(os.path.samefile(alias, canonical), "Alias targets different source")
            _check(alias.read_bytes() == data, "Alias bytes differ")
            _check(
                hashlib.sha256(canonical.read_bytes()).digest() == digest,
                "Canonical source bytes changed",
            )
            junction = alias.parent
            _check(local_open._is_reparse_point(junction), "Expected a junction")
        finally:
            if alias is not None:
                junction = alias.parent
                if os.path.lexists(junction) and local_open._is_reparse_point(junction):
                    local_open._remove_viewer_junction(junction)
        _check(alias is not None and not os.path.lexists(alias.parent),
               "Junction cleanup failed")
        _check(canonical.read_bytes() == data, "Cleanup modified canonical bytes")
    print("Core #232 installed Windows real-junction qualification: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", default="0.6.6")
    parser.add_argument("--forbidden-root", type=Path, required=True)
    args = parser.parse_args()
    distribution = importlib.metadata.version("pds-core")
    _check(distribution == args.expected_version, "Installed version mismatch")
    _check(__version__ == args.expected_version, "Runtime version mismatch")
    package = Path(local_open.__file__).resolve()
    forbidden = args.forbidden_root.resolve()
    _check(not package.is_relative_to(forbidden), "Imported source checkout, not wheel")
    _check(sys.prefix != sys.base_prefix, "Not running inside isolated venv")
    if os.name == "nt":
        _check_windows_junction()
    else:
        print("Core #232 installed import/identity qualification: PASS (non-Windows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
