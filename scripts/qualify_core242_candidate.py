"""Exact-head focused qualification with verified Ruff-only recovery/publication.

Run using the repository virtual environment. No execution-policy changes.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def capture(*args: str) -> bytes:
    return subprocess.check_output(args)


def git(*args: str) -> str:
    return capture("git", *args).decode("utf-8").strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def paths(*args: str) -> set[str]:
    raw = capture("git", *args, "-z").decode("utf-8")
    return {path for path in raw.split("\x00") if path}


def status() -> set[str]:
    raw = capture(
        "git", "status", "--porcelain=v1", "--untracked-files=all", "-z"
    ).decode("utf-8")
    modified: set[str] = set()
    for entry in raw.split("\x00"):
        if not entry:
            continue
        require(entry.startswith(" M "), f"Unexpected working-tree status: {entry}")
        modified.add(entry[3:])
    return modified


def verify_ruff_only(files: set[str]) -> None:
    for name in sorted(files):
        original = capture("git", "show", f"HEAD:{name}")
        formatted = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--stdin-filename", name, "-"],
            input=original,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        actual = Path(name).read_bytes()
        require(
            actual.replace(b"\r\n", b"\n") == formatted.replace(b"\r\n", b"\n"),
            f"Refused: {name} contains changes beyond Ruff formatting.",
        )
        print(f"Verified Ruff-only change: {name}", flush=True)


def remote_head(branch: str) -> str:
    fields = git("ls-remote", "--exit-code", "origin", f"refs/heads/{branch}").split()
    require(len(fields) == 2, "Remote branch cannot be verified.")
    return fields[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--skip-format", nargs="*", default=[])
    parser.add_argument("--tests", nargs="+", required=True)
    args = parser.parse_args()
    branch: str = args.branch
    base: str = args.base
    candidate: str = args.candidate
    label: str = args.label
    tests: list[str] = args.tests
    skipped: set[str] = set(args.skip_format)
    require(
        all(re.fullmatch("[0-9a-f]{40}", s) for s in (base, candidate)),
        "Full lowercase SHA-1 commits are required.",
    )
    require(re.fullmatch("[A-Za-z0-9_-]+", label) is not None, "Invalid label.")
    root = Path(git("rev-parse", "--show-toplevel")).resolve()
    require(Path.cwd().resolve() == root, "Run from the repository root.")
    require(git("branch", "--show-current") == branch, "Unexpected branch.")
    origin = git("remote", "get-url", "origin").lower().removesuffix(".git")
    require(
        origin
        in {
            "https://github.com/paper-data-suite/pds-core",
            "git@github.com:paper-data-suite/pds-core",
            "ssh://git@github.com/paper-data-suite/pds-core",
        },
        "Unexpected origin.",
    )
    head = git("rev-parse", "HEAD")
    require(head in {base, candidate}, "Unexpected local HEAD.")

    print("=== VERIFY REMOTE CANDIDATE ===", flush=True)
    run("git", "fetch", "origin", branch)
    require(remote_head(branch) == candidate, "Remote candidate changed.")
    run("git", "merge-base", "--is-ancestor", base, candidate)
    changed = paths("diff", "--name-only", base, candidate)
    python_files = {name for name in changed if name.endswith(".py")}
    require(skipped <= python_files, "Unexpected format exclusions.")
    format_files = python_files - skipped
    require(bool(format_files), "No scoped Python files.")
    require(
        all(name.startswith("tests/") and name.endswith(".py") for name in tests),
        "Focused tests must be repository test files.",
    )

    print("=== SAFELY RECOVER INTERRUPTED FORMATTING ===", flush=True)
    dirty = status()
    require(dirty <= format_files, "Changes outside formatting scope.")
    if dirty:
        verify_ruff_only(dirty)
        run("git", "restore", "--", *sorted(dirty))
    require(not status(), "Checkout not clean after recovery.")
    if head == base and head != candidate:
        run("git", "merge", "--ff-only", candidate)
    require(git("rev-parse", "HEAD") == candidate, "Unexpected checkout SHA.")
    require(
        all(Path(name).is_file() for name in python_files | set(tests)),
        "A scoped file does not exist.",
    )

    print("=== AUTOMATIC RUFF FORMATTING ===", flush=True)
    scoped = sorted(format_files)
    static = sorted(python_files)
    run(sys.executable, "-m", "ruff", "format", *scoped)
    run(sys.executable, "-m", "ruff", "format", "--check", *scoped)
    run(sys.executable, "-m", "ruff", "check", *static)
    run(sys.executable, "-m", "mypy", *static)
    print("=== FOCUSED REGRESSION ===", flush=True)
    run(sys.executable, "-m", "pytest", "-q", "-ra", *tests)

    print("=== VERIFY AUTOMATIC CHANGE SCOPE ===", flush=True)
    dirty = status()
    require(dirty <= format_files, "Unexpected modifications after tests.")
    run("git", "diff", "--check")
    if dirty:
        verify_ruff_only(dirty)
        require(remote_head(branch) == candidate, "Remote advanced; no push.")
        run("git", "add", "--", *sorted(dirty))
        require(
            paths("diff", "--cached", "--name-only") == dirty,
            "Unexpected staged files.",
        )
        run("git", "diff", "--cached", "--check")
        run(
            "git", "commit", "-m", f"style(core242): autoformat {label} qualified files"
        )
        run("git", "push", "origin", f"HEAD:refs/heads/{branch}")
    else:
        print("No formatting commit required.", flush=True)

    print("=== FINAL INTEGRITY ===", flush=True)
    final = git("rev-parse", "HEAD")
    require(remote_head(branch) == final, "Local/remote HEAD mismatch.")
    require(not status(), "Final checkout is not clean.")
    run("git", "status", "--short", "--branch")
    print(f"CORE #242 {label} QUALIFIED.\nQUALIFIED HEAD: {final}", flush=True)


if __name__ == "__main__":
    main()
