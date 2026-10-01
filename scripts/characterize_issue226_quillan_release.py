"""Authenticate and characterize Quillan 0.10.3 against Core 0.6.4 for #226."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.qualify_released_consumers import (  # noqa: E402
    download_authenticated_consumer_artifact,
)
from scripts.released_consumer_compatibility import (  # noqa: E402
    inspect_candidate_wheel,
    inspect_consumer_wheel,
    load_compatibility_fixture,
)

EXPECTED_CORE_VERSION = "0.6.4"
EXPECTED_QUILLAN_VERSION = "0.10.3"
EXPECTED_LEGACY_FAILURE = "retained filename contradicts the Core retention event."


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"{field} must be an object.")
    return cast(dict[str, object], value)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"{label} failed: {detail[-1600:]}")
    return completed


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def characterization_evidence(
    *,
    candidate_filename: str,
    candidate_version: str,
    candidate_sha256: str,
    quillan_wheel: str,
    quillan_version: str,
    quillan_sha256: str,
    probe: dict[str, object],
) -> bytes:
    payload = {
        "candidate": {
            "filename": candidate_filename,
            "sha256": candidate_sha256,
            "version": candidate_version,
        },
        "characterization_status": (
            "release_blocker_confirmed"
            if probe.get("release_blocker") is True
            else "compatible"
        ),
        "probe": probe,
        "quillan": {
            "version": quillan_version,
            "wheel": quillan_wheel,
            "wheel_sha256": quillan_sha256,
        },
        "record_type": "pds_core_issue226_quillan_release_characterization",
        "schema_version": "1",
    }
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-wheel", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "tests"
            / "fixtures"
            / "released_consumers"
            / "v1"
            / "manifest.json"
        ),
    )
    parser.add_argument(
        "--legacy-fixture",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "tests"
            / "fixtures"
            / "issue226"
            / "legacy_retained_source_v063.json"
        ),
    )
    args = parser.parse_args()

    candidate = inspect_candidate_wheel(
        args.core_wheel,
        expected_version=EXPECTED_CORE_VERSION,
    )
    matrix = load_compatibility_fixture(args.fixture).by_component_id()
    quillan = matrix.get("quillan")
    if quillan is None or quillan.version != EXPECTED_QUILLAN_VERSION:
        raise RuntimeError("Fixture does not pin exact Quillan 0.10.3.")

    with tempfile.TemporaryDirectory(prefix="pds-core-issue226-quillan-release-") as temp:
        root = Path(temp)
        artifact = download_authenticated_consumer_artifact(quillan, root / "artifacts")
        inspect_consumer_wheel(artifact.path, quillan)

        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(environment)
        python = _venv_python(environment)
        if not python.is_file():
            raise RuntimeError("Characterization virtual environment was not created.")

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PIP_NO_INPUT"] = "1"

        smoke = root / "smoke"
        smoke.mkdir()
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                str(candidate.path),
                str(artifact.path),
            ],
            cwd=smoke,
            env=env,
            label="Core/Quillan isolated installation",
        )
        _run(
            [str(python), "-m", "pip", "check"],
            cwd=smoke,
            env=env,
            label="pip check",
        )
        probe_result = _run(
            [
                str(python),
                str(REPOSITORY_ROOT / "scripts" / "issue226_quillan_provenance_probe.py"),
                "--legacy-fixture",
                str(args.legacy_fixture.resolve()),
                "--source-checkout",
                str(REPOSITORY_ROOT.resolve()),
            ],
            cwd=smoke,
            env=env,
            label="Issue #226 Quillan provenance probe",
        )
        probe = _mapping(json.loads(probe_result.stdout), "probe result")

    if probe.get("fresh_bounded_provenance") != "pass":
        raise RuntimeError("Fresh Core 0.6.4 retained provenance did not pass Quillan.")
    if probe.get("legacy_v063_long_name_provenance") != "fail":
        raise RuntimeError("Historical Core 0.6.3 long-name provenance unexpectedly passed.")
    if probe.get("legacy_failure") != EXPECTED_LEGACY_FAILURE:
        raise RuntimeError("Historical failure message did not match the expected blocker.")
    if probe.get("release_blocker") is not True:
        raise RuntimeError("Characterization did not mark the historical rejection as blocking.")

    evidence = characterization_evidence(
        candidate_filename=candidate.filename,
        candidate_version=candidate.version,
        candidate_sha256=candidate.sha256,
        quillan_wheel=quillan.release.wheel,
        quillan_version=quillan.version,
        quillan_sha256=artifact.sha256,
        probe=probe,
    )
    destination = (
        args.evidence.resolve()
        if args.evidence is not None
        else candidate.path.parent
        / "pds_core-0.6.4-issue226-quillan-0.10.3-characterization.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(evidence)

    print("Issue #226 Quillan 0.10.3 characterization: RELEASE BLOCKER CONFIRMED")
    print(f"evidence: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
