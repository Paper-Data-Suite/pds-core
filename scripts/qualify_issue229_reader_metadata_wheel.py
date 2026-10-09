"""Verify Issue #229 from an explicit built Core wheel in a clean Python venv.

This is a development-candidate smoke. It is NOT the published release or the
historical Core 0.6.4 released-consumer qualification matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import venv
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path
from typing import Final, cast
from zipfile import BadZipFile, ZipFile

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PROBE: Final[Path] = REPO_ROOT / "scripts" / "issue229_reader_contract_wheel_probe.py"
RECORD_TYPE: Final[str] = "pds_core_issue229_installed_reader_contract_qualification_v1"
_NAME: Final[re.Pattern[str]] = re.compile(r"^pds_core-[^/]+\.dist-info/METADATA$")
_MAX_DETAIL: Final[int] = 1000


class QualificationError(RuntimeError):
    """An installed-wheel qualification precondition or check failed."""


@dataclass(frozen=True, slots=True)
class Candidate:
    path: Path
    version: str
    sha256: str


def inspect_candidate_wheel(path: Path) -> Candidate:
    """Validate an exact local pds-core wheel without importing project code."""
    path = path.resolve()
    if not path.is_file() or not path.name.startswith("pds_core-") or path.suffix != ".whl":
        raise QualificationError("Provide an existing pds_core-*.whl candidate.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            matches = [name for name in names if _NAME.fullmatch(name)]
            if len(matches) != 1:
                raise QualificationError("Core wheel must have one pds_core dist-info METADATA.")
            if len(names) != len(set(names)):
                raise QualificationError("Core wheel has duplicate ZIP members.")
            if "pds_core/__init__.py" not in names or "pds_core/publication_compatibility.py" not in names:
                raise QualificationError("Core wheel is missing the public reader-metadata module.")
            if archive.testzip() is not None:
                raise QualificationError("Core wheel failed ZIP integrity verification.")
            metadata = Parser().parsestr(archive.read(matches[0]).decode("utf-8"))
    except (BadZipFile, UnicodeError, OSError) as error:
        raise QualificationError("Core wheel could not be inspected safely.") from error
    if metadata.get("Name", "").lower().replace("_", "-") != "pds-core":
        raise QualificationError("Wheel metadata is not for pds-core.")
    version = metadata.get("Version", "")
    if not version or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version) is None:
        raise QualificationError("Core wheel metadata version is invalid.")
    if not path.name.startswith(f"pds_core-{version}-"):
        raise QualificationError("Wheel filename and metadata version disagree.")
    return Candidate(path=path, version=version, sha256=digest.hexdigest())


def _run(command: list[str], *, cwd: Path) -> str:
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr.strip() or result.stdout.strip())[-_MAX_DETAIL:]
        detail = detail.replace(str(Path.home()), "<home>").replace(str(REPO_ROOT), "<core-checkout>")
        raise QualificationError(f"Installed qualification command failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def _venv_python(env_dir: Path) -> Path:
    return env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run_installed(candidate: Candidate) -> dict[str, object]:
    """Run the actual reader API in a fresh no-system-site-packages environment."""
    if not PROBE.is_file():
        raise QualificationError("Installed reader-contract probe script is missing.")
    with tempfile.TemporaryDirectory(prefix="pds-core-issue229-installed-") as temp:
        root = Path(temp)
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(root / "venv")
        python = _venv_python(root / "venv")
        execution = root / "execution"
        execution.mkdir()
        _run(
            [str(python), "-m", "pip", "--isolated", "install", "--no-input", "--no-index", "--no-deps", str(candidate.path)],
            cwd=execution,
        )
        _run([str(python), "-m", "pip", "check"], cwd=execution)
        raw = _run(
            [str(python), "-I", str(PROBE), "--expected-version", candidate.version, "--forbidden-root", str(REPO_ROOT)],
            cwd=execution,
        )
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise QualificationError("Installed probe produced invalid JSON.") from error
        if (
            not isinstance(result, dict)
            or any(not isinstance(key, str) for key in result)
            or result.get("status") != "pass"
        ):
            raise QualificationError("Installed probe did not confirm success.")
        if result.get("core_distribution_version") != candidate.version:
            raise QualificationError("Installed probe version evidence disagrees with wheel.")
        if result.get("import_source") != "installed_wheel_outside_checkout":
            raise QualificationError("Installed probe did not verify import isolation.")
        return cast(dict[str, object], result)


def qualification_record(candidate: Candidate, installed: dict[str, object]) -> bytes:
    """Build deterministic, path-free evidence; not a published-release claim."""
    payload: dict[str, object] = {
        "record_type": RECORD_TYPE,
        "schema_version": "1",
        "qualification_stage": "pre_release_development_candidate",
        "candidate_wheel": {
            "filename": candidate.path.name,
            "distribution": "pds-core",
            "version": candidate.version,
            "sha256": candidate.sha256,
        },
        "status": "pass",
        "installed_probe": installed,
        "released_consumer_matrix": "not_executed_by_this_probe",
    }
    return (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-wheel", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    arguments = parser.parse_args()
    try:
        candidate = inspect_candidate_wheel(arguments.core_wheel)
        installed = run_installed(candidate)
        record = qualification_record(candidate, installed)
        if arguments.evidence is None:
            print(record.decode("utf-8"), end="")
        else:
            target = arguments.evidence.resolve()
            if target.exists():
                raise QualificationError("Refusing to overwrite an existing qualification record.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(record)
            print(f"Evidence written: {target}")
        print(f"Core #229 installed reader contract: PASS ({candidate.version}, SHA-256 {candidate.sha256})")
        return 0
    except (QualificationError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Core #229 installed reader qualification failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
