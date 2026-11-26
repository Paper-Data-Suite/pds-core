"""Build and qualify both Core distributions from one clean exact Git commit."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def _run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root).decode("utf-8").strip()


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel")).resolve()
    expected: str = args.expected_head
    assert len(expected) == 40 and _git(root, "rev-parse", "HEAD") == expected
    assert not _git(root, "status", "--porcelain", "--untracked-files=all"), (
        "Requires clean checkout"
    )
    print(f"EXACT SOURCE HEAD: {expected}", flush=True)
    with tempfile.TemporaryDirectory(prefix="core242-artifacts-") as directory:
        temp = Path(directory)
        archive = temp / "source.zip"
        source = temp / "source"
        source.mkdir()
        _run("git", "archive", "--format=zip", "-o", str(archive), expected, cwd=root)
        with zipfile.ZipFile(archive) as snapshot:
            snapshot.extractall(source)
        dist = temp / "dist"
        _run(sys.executable, "-m", "build", "--outdir", str(dist), cwd=source)
        wheels = tuple(dist.glob("*.whl"))
        sdists = tuple(dist.glob("*.tar.gz"))
        assert len(wheels) == len(sdists) == 1
        _run(
            sys.executable,
            "-m",
            "twine",
            "check",
            str(wheels[0]),
            str(sdists[0]),
            cwd=temp,
        )
        for kind, artifact in (("wheel", wheels[0]), ("sdist", sdists[0])):
            print(
                f"{kind.upper()} SHA256: {_digest(artifact)} {artifact.name}",
                flush=True,
            )
            environment = temp / f"{kind}-venv"
            _run(sys.executable, "-m", "venv", str(environment), cwd=temp)
            python = str(_python(environment))
            _run(python, "-I", "-m", "pip", "install", str(artifact), cwd=temp)
            _run(python, "-I", "-m", "pip", "check", cwd=temp)
            smoke = temp / f"{kind}-smoke"
            smoke.mkdir()
            _run(
                python,
                "-I",
                str(source / "scripts/issue242_installed_acceptance.py"),
                cwd=smoke,
            )
            assert not tuple(smoke.iterdir()), "Installed probe left unexpected residue"
    assert _git(root, "rev-parse", "HEAD") == expected
    assert not _git(root, "status", "--porcelain", "--untracked-files=all")
    print(f"CORE #242 WHEEL + SDIST QUALIFIED AT {expected}", flush=True)


if __name__ == "__main__":
    main()
