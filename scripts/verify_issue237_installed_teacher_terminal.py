"""Issue #237 installed-wheel teacher-terminal acceptance, run outside checkout.

This script intentionally uses only the Python standard library plus the installed
pds-core wheel. Invoke it using the isolated environment's Python with ``-I``.
It never writes inside the source checkout and does not qualify producer menus.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise RuntimeError(f"Issue #237 installed acceptance: {detail}")


def assert_not_under(path: Path, forbidden: Path) -> None:
    try:
        path.resolve().relative_to(forbidden.resolve())
    except ValueError:
        return
    raise RuntimeError(f"installed module resolved inside source checkout: {path}")


def _exercise_public_imports(expected_version: str, source: Path) -> dict[str, Any]:
    import pds_core
    import pds_core.teacher_commands as commands
    import pds_core.teacher_experience as experience
    import pds_core.teacher_ui as ui
    from pds_core.menu_navigation import (
        NavigationChoice,
        QuitPDS,
        ReturnToMainMenu,
        parse_navigation_choice,
    )

    require(
        importlib.metadata.version("pds-core") == expected_version,
        "installed distribution version is not the pinned candidate version",
    )
    require(pds_core.__version__ == expected_version, "installed Core version mismatch")
    for module in (pds_core, commands, experience, ui):
        module_path = module.__file__
        if not isinstance(module_path, str):
            raise RuntimeError("installed module file is missing")
        assert_not_under(Path(module_path), source)

    require(
        experience.TEACHER_EXPERIENCE_CONTRACT_VERSION == "1", "contract version drift"
    )
    expected_caps = frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
    caps = experience.get_teacher_experience_capabilities()
    require(type(caps) is frozenset and caps == expected_caps, "capabilities not exact")
    for absent in (
        "notes.records.v1",
        "notes.menu.v1",
        "notes.cli.v1",
        "classroom.roster_edits.v1",
        "classroom.menu.v1",
        "notes.portability.v1",
    ):
        require(absent not in caps, f"premature capability advertisement: {absent}")
    for nonexistent in ("pds_core.teacher_context", "pds_core.teacher_menus"):
        require(
            importlib.util.find_spec(nonexistent) is None,
            f"premature API: {nonexistent}",
        )

    require(
        tuple(ui.__all__)
        == ("TeacherScreenHeader", "render_teacher_header", "print_teacher_header"),
        "header public exports drifted",
    )
    require(
        tuple(commands.__all__)
        == ("PromptKind", "SharedTeacherCommand", "parse_shared_teacher_command"),
        "shared-command public exports drifted",
    )
    header = ui.TeacherScreenHeader(
        "Quillan", "Review Student Work", "Fictional English 12 Assignment"
    )
    plain = "Quillan\nReview Student Work\nFictional English 12 Assignment"
    require(ui.render_teacher_header(header) == plain, "plain header bytes drifted")
    require(
        ui.render_teacher_header(header, ansi=True)
        == "\x1b[32mQuillan\x1b[0m\nReview Student Work\nFictional English 12 Assignment",
        "only-name ANSI render bytes drifted",
    )
    require(
        ui.render_teacher_header(ui.TeacherScreenHeader("Portia", "Home"))
        == "Portia\nHome",
        "optional context rendered an extra line",
    )
    output = io.StringIO()
    ui.print_teacher_header(header, output=output, color="never")
    require(output.getvalue() == plain + "\n", "explicit plain stream output drifted")
    output = io.StringIO()
    ui.print_teacher_header(header, output=output, color="auto")
    require(output.getvalue() == plain + "\n", "captured stream emitted ANSI")
    saved_no_color = os.environ.get("NO_COLOR")
    try:
        os.environ["NO_COLOR"] = "1"
        output = io.StringIO()
        ui.print_teacher_header(header, output=output, color="auto")
        require(output.getvalue() == plain + "\n", "NO_COLOR fallback drifted")
    finally:
        if saved_no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = saved_no_color

    for invalid_header in ("Quillan\nInjected", "Quillan\x1b[31m"):
        try:
            ui.TeacherScreenHeader(invalid_header, "Home")
        except ValueError:
            pass
        else:
            raise RuntimeError("unsafe header label was accepted")
    for invalid_color in ("always", True):
        try:
            ui.print_teacher_header(
                header,
                output=io.StringIO(),
                color=invalid_color,  # type: ignore[arg-type]
            )
        except (TypeError, ValueError):
            pass
        else:
            raise RuntimeError("invalid color mode was accepted")

    parser = commands.parse_shared_teacher_command
    kind = commands.PromptKind
    recognized = commands.SharedTeacherCommand.NOTES
    require(
        parser(
            " :NoTeS ", prompt_kind=kind.MENU_CHOICE, interactive=True, allow_notes=True
        )
        is recognized,
        "explicit interactive menu-choice did not recognize Notes",
    )
    for k in (kind.DATA_ENTRY, kind.CONFIRMATION, kind.PAUSE):
        require(
            parser(":notes", prompt_kind=k, interactive=True, allow_notes=True) is None,
            "non-choice field intercepted Notes",
        )
    require(
        parser(
            ":notes", prompt_kind=kind.MENU_CHOICE, interactive=False, allow_notes=True
        )
        is None,
        "noninteractive invocation intercepted Notes",
    )
    require(
        parser(":notes", prompt_kind=kind.MENU_CHOICE, interactive=True) is None,
        "unqualified choice enabled Notes by default",
    )
    for local in (
        "N",
        "W",
        "B",
        "M",
        "Q",
        "A",
        "H",
        "1",
        "12",
        ":note",
        "::notes",
        ":notes 1",
    ):
        require(
            parser(
                local, prompt_kind=kind.MENU_CHOICE, interactive=True, allow_notes=True
            )
            is None,
            f"shared parser intercepted local choice {local!r}",
        )
    require(parse_navigation_choice("B") is NavigationChoice.BACK, "legacy B changed")
    for choice, error in (("M", ReturnToMainMenu), ("Q", QuitPDS)):
        try:
            parse_navigation_choice(choice)
        except error:
            pass
        else:
            raise RuntimeError(f"legacy {choice} exception changed")
    require(parse_navigation_choice("N") is None, "legacy N changed")
    require(parse_navigation_choice("W") is None, "legacy W changed")
    require(parse_navigation_choice(":notes") is None, "legacy parser acquired Notes")
    require(parse_navigation_choice("A") is None, "legacy A became default")
    require(
        parse_navigation_choice("A", allow_all=True) is NavigationChoice.ALL,
        "legacy opt-in A changed",
    )
    for invalid in ("menu_choice", None, 1):
        try:
            parser(
                ":notes",
                prompt_kind=invalid,  # type: ignore[arg-type]
                interactive=True,
                allow_notes=True,
            )
        except TypeError:
            pass
        else:
            raise RuntimeError("untyped prompt kind accepted")
    require(
        "terminal.header.v1" in caps and "notes.menu.v1" not in caps,
        "Notes menu inferred from terminal parser",
    )
    return {
        "contract": experience.TEACHER_EXPERIENCE_CONTRACT_VERSION,
        "capabilities": sorted(caps),
        "installed_core_module": str(Path(pds_core.__file__).resolve()),
        "installed_version": importlib.metadata.version("pds-core"),
        "checks": [
            "installed-imports",
            "module-origins",
            "contract-and-capabilities",
            "plain-and-ansi-render",
            "captured-stream-and-no-color",
            "header-validation",
            "exact-opt-in-parser",
            "literal-fields",
            "legacy-B-M-Q-A-N-W",
            "Notes-unavailable",
            "invalid-types",
        ],
    }


def _exercise_installed_scripts() -> None:
    executable_dir = Path(sys.executable).parent
    for name in ("core", "pds-core"):
        script = executable_dir / (name + ".exe" if os.name == "nt" else name)
        require(script.is_file(), f"installed console script missing: {name}")
        result = subprocess.run(
            [str(script), "--help"],
            cwd=Path.cwd(),
            input="",
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        require(result.returncode == 0, f"installed {name} --help returned nonzero")
        require("usage:" in result.stdout.lower(), f"installed {name} help unavailable")
        require("Traceback" not in result.stderr, f"installed {name} printed traceback")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_checkout.resolve(strict=True)
    wheel = args.wheel.resolve(strict=True)
    report = args.report.resolve()
    require(source.is_dir(), "source checkout is not a directory")
    require(wheel.is_file() and wheel.suffix == ".whl", "wheel missing or invalid")
    assert_not_under(Path.cwd(), source)
    assert_not_under(report, source)
    require(not report.exists(), "report destination already exists")
    before = set(Path.cwd().iterdir())
    summary = _exercise_public_imports(args.expected_version, source)
    _exercise_installed_scripts()
    require(before == set(Path.cwd().iterdir()), "installed smoke created cwd files")
    summary.update(
        {
            "issue": 237,
            "qualification": "D2 isolated candidate-wheel smoke, not a published release",
            "wheel_filename": wheel.name,
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "os": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "console_scripts": ["core", "pds-core"],
            "producer_or_suite_adoption": False,
            "physical_windows_arm64_terminal_validated": False,
        }
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(summary, output, sort_keys=True, indent=2)
        output.write("\n")
    print("Issue #237 isolated installed-wheel teacher-terminal acceptance: PASS")
    print(f"Candidate wheel SHA-256: {summary['wheel_sha256']}")
    print(
        f"Environment: {summary['os']} / {summary['architecture']} / Python {summary['python']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
