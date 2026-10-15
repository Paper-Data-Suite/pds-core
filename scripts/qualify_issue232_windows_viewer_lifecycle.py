"""Interactive real-Windows #232 acceptance for HTML assets and Explorer folders.

Uses synthetic bytes only and cleans up only links created by this probe.
The child opener process exits *before* the user confirms viewer visibility.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from types import ModuleType
import subprocess
import sys
import tempfile


def _core_module() -> ModuleType:
    # Repository source qualification; later installed-wheel qualification uses
    # -I and imports the packaged Core through a different release gate.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from pds_core import local_open

    return local_open


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prompt_yes(question: str) -> None:
    answer = input(question + " (Y/N): ").strip().casefold()
    if answer != "y":
        raise RuntimeError("Actual viewer accessibility was NOT confirmed.")


def _build_long_root(base: Path, *, minimum_length: int = 295) -> Path:
    root = base / "synthetic-workspace"
    while len(str(root)) < minimum_length:
        root = root / "nested"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _alias_entries(root: Path) -> set[str]:
    return {entry.name for entry in root.iterdir() if entry.name.startswith("v_")}


def _launch_in_short_lived_child(target: Path, expected_kind: str, root: Path) -> Path:
    local_open = _core_module()
    before = _alias_entries(root)
    result = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--child", str(target)],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "The isolated child process could not submit a launch request: "
            + (result.stderr.strip() or result.stdout.strip())[:500]
        )
    if "CORE232_CHILD_LAUNCH_ACCEPTED" not in result.stdout:
        raise RuntimeError("The isolated child did not acknowledge its launch request.")
    after = _alias_entries(root)
    created = after - before
    if len(created) != 1:
        raise RuntimeError(
            "Expected one persistent junction after child exit; "
            f"observed {len(created)}."
        )
    link = root / created.pop()
    if not local_open._is_reparse_point(link):
        raise RuntimeError("The new alias is not a directory reparse point.")
    alias_target = link if expected_kind == "directory" else link / target.name
    if not alias_target.exists() or not os.path.samefile(alias_target, target):
        raise RuntimeError(
            "The alias no longer refers to the exact synthetic file/folder."
        )
    if local_open._windows_path_units(alias_target) > 240:
        raise RuntimeError("Alias still exceeds the 240-WCHAR handoff budget.")
    print(
        f"Launch accepted; child exited; original path units="
        f"{local_open._windows_path_units(target)}, alias units="
        f"{local_open._windows_path_units(alias_target)}"
    )
    return link


def _run_html(base: Path, alias_root: Path) -> None:
    local_open = _core_module()
    folder = _build_long_root(base / "html")
    html = folder / "document.html"
    css = folder / "style.css"
    css.write_text(
        "body { font-family: sans-serif } .proof { color: green; "
        "font-size: 38px; font-weight: bold }",
        encoding="utf-8",
    )
    html.write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<link rel="stylesheet" href="style.css"></head><body>'
        '<h1>Paper Data Suite — Core #232 HTML qualification</h1>'
        '<p class="proof">GREEN means relative CSS loaded successfully.</p>'
        '</body></html>',
        encoding="utf-8",
    )
    before = (_sha256(html), _sha256(css))
    print("\nCASE 1: Deep HTML + relative CSS in default browser")
    link = _launch_in_short_lived_child(html, "file", alias_root)
    try:
        _prompt_yes("Did the HTML AND its large GREEN message appear correctly?")
    finally:
        input("Close that browser tab/window, then press ENTER for link cleanup: ")
        local_open._remove_viewer_junction(link)
    if os.path.lexists(link):
        raise RuntimeError("HTML alias was not removed.")
    if before != (_sha256(html), _sha256(css)):
        raise RuntimeError("Synthetic HTML or CSS bytes were changed.")
    print(
        "HTML: VIEWER ACCESSIBLE; relative assets loaded; "
        "child exited; clean removal."
    )


def _run_folder(base: Path, alias_root: Path) -> None:
    local_open = _core_module()
    folder = _build_long_root(base / "folder")
    marker = folder / "CHECK-CORE232.txt"
    marker.write_text("CORE #232 FOLDER DISPLAY CHECK", encoding="utf-8")
    before = _sha256(marker)
    print("\nCASE 2: Deep folder in Windows File Explorer")
    link = _launch_in_short_lived_child(folder, "directory", alias_root)
    try:
        _prompt_yes("Did Explorer open the folder showing CHECK-CORE232.txt?")
    finally:
        input("Close that Explorer window, then press ENTER for link cleanup: ")
        local_open._remove_viewer_junction(link)
    if os.path.lexists(link):
        raise RuntimeError("Folder alias was not removed.")
    if before != _sha256(marker):
        raise RuntimeError("Synthetic folder source file was modified.")
    print("FOLDER: EXPLORER ACCESSIBLE; child exited; clean removal.")


def _run_cleanup(root: Path) -> None:
    local_open = _core_module()
    source = root / "cleanup-target"
    source.mkdir()
    sentinel = source / "source-must-survive.txt"
    sentinel.write_text("SOURCE SURVIVED", encoding="utf-8")
    alias_root = root / "owned-aliases-only"
    alias_root.mkdir()
    link = alias_root / ("v_" + "d" * 32)
    local_open._create_windows_junction(link, source)
    if not local_open._is_reparse_point(link):
        raise RuntimeError("Cleanup fixture did not create a junction.")
    previous = local_open._WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS
    try:
        # This private disposable root has exactly one synthetic junction.
        # Force it to be eligible without editing junction/target timestamps.
        setattr(local_open, "_WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS", -1)
        local_open._prune_stale_aliases(alias_root)
    finally:
        setattr(local_open, "_WINDOWS_VIEWER_ALIAS_RETENTION_SECONDS", previous)
    if os.path.lexists(link):
        raise RuntimeError("Expired disposable junction was not pruned on Windows.")
    if sentinel.read_text(encoding="utf-8") != "SOURCE SURVIVED":
        raise RuntimeError("Original source was changed or deleted by cleanup.")
    print("CLEANUP: expired synthetic junction removed; source untouched.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("This physical qualification requires Windows.")
    local_open = _core_module()
    if args.child is not None:
        canonical = args.child.resolve(strict=True)
        returned = local_open.open_local_path(canonical)
        if returned != canonical:
            raise SystemExit("Opener did not return the canonical path.")
        print("CORE232_CHILD_LAUNCH_ACCEPTED", flush=True)
        return 0

    print("CORE #232 — REAL WINDOWS VIEWER LIFECYCLE ACCEPTANCE")
    print("The test creates only synthetic HTML/CSS/text. No PDS workspace data.")
    alias_root = local_open._viewer_alias_root()
    print("Short alias root: under current user's local application data")
    with tempfile.TemporaryDirectory(prefix="pds-core232-lifecycle-") as td:
        temp = Path(td)
        _run_html(temp, alias_root)
        _run_folder(temp, alias_root)
        _run_cleanup(temp)
    print("\nCORE #232 LIFECYCLE: PASS — HTML, folder, child-exit retention, cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
