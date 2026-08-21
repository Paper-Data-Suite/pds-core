"""Qualify one explicit Core 0.6.2 wheel against exact released consumers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.released_consumer_compatibility import (  # noqa: E402
    CandidateWheelError,
    CompatibilityFixtureError,
    ConsumerFixture,
    ConsumerWheelIdentity,
    inspect_candidate_wheel,
    inspect_consumer_wheel,
    load_compatibility_fixture,
    sha256_file,
)

QUALIFICATION_RECORD_TYPE: Final[str] = "pds_core_released_consumer_qualification"
QUALIFICATION_SCHEMA_VERSION: Final[str] = "1"
_GITHUB_API_ACCEPT: Final[str] = "application/vnd.github+json"
_GITHUB_API_VERSION: Final[str] = "2022-11-28"
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_MAX_FAILURE_MESSAGE: Final[int] = 1200


class QualificationError(RuntimeError):
    """Raised when one qualification stage cannot complete safely."""


@dataclass(frozen=True, slots=True)
class ReleaseAssetMetadata:
    name: str
    browser_download_url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class AuthenticatedConsumerArtifact:
    path: Path
    sha256: str
    github_sha256: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise QualificationError(f"{field} must be an object.")
    return cast(dict[str, object], value)


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise QualificationError(f"{field} must be an array.")
    return cast(list[object], value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise QualificationError(f"{field} must be nonempty text.")
    return value


def _github_release_api_url(consumer: ConsumerFixture) -> str:
    return (
        f"https://api.github.com/repos/{consumer.repository}/releases/tags/"
        f"{consumer.release.tag}"
    )


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": _GITHUB_API_ACCEPT,
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        "User-Agent": "pds-core-released-consumer-qualification/1",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_asset_digest(value: object, field: str) -> str:
    digest = _text(value, field)
    prefix = "sha256:"
    if not digest.startswith(prefix):
        raise QualificationError(f"{field} must use GitHub sha256:<hex> form.")
    raw = digest[len(prefix) :]
    if _SHA256_RE.fullmatch(raw) is None:
        raise QualificationError(f"{field} contains an invalid SHA-256 digest.")
    return raw


def parse_release_asset_metadata(
    payload: object,
    consumer: ConsumerFixture,
) -> ReleaseAssetMetadata:
    """Validate exact GitHub release metadata for one pinned consumer asset."""
    release = _mapping(payload, "GitHub release")
    if _text(release.get("tag_name"), "GitHub release tag_name") != consumer.release.tag:
        raise QualificationError("GitHub release tag does not match the fixture.")
    if release.get("draft") is True:
        raise QualificationError("Pinned consumer release is still a draft.")
    assets = _list(release.get("assets"), "GitHub release assets")
    matches: list[dict[str, object]] = []
    for value in assets:
        asset = _mapping(value, "GitHub release asset")
        if asset.get("name") == consumer.release.wheel:
            matches.append(asset)
    if len(matches) != 1:
        raise QualificationError(
            "GitHub release must expose exactly one fixture-named wheel asset."
        )
    asset = matches[0]
    url = _text(asset.get("browser_download_url"), "asset browser_download_url")
    if url != consumer.release.download_url:
        raise QualificationError("GitHub release asset URL does not match the fixture.")
    digest = _github_asset_digest(asset.get("digest"), "asset digest")
    if consumer.release.sha256 is not None and digest != consumer.release.sha256:
        raise QualificationError(
            "GitHub release asset digest disagrees with the pinned fixture SHA-256."
        )
    return ReleaseAssetMetadata(
        name=consumer.release.wheel,
        browser_download_url=url,
        sha256=digest,
    )


def _urlopen_bytes(request: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return bytes(response.read())
    except (OSError, urllib.error.URLError) as error:
        raise QualificationError("Could not retrieve pinned GitHub release data.") from error


def fetch_release_asset_metadata(consumer: ConsumerFixture) -> ReleaseAssetMetadata:
    """Fetch and validate exact GitHub release metadata for one consumer."""
    request = urllib.request.Request(
        _github_release_api_url(consumer),
        headers=_github_headers(),
    )
    data = _urlopen_bytes(request)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationError("GitHub release metadata was not valid UTF-8 JSON.") from error
    return parse_release_asset_metadata(payload, consumer)


def download_authenticated_consumer_artifact(
    consumer: ConsumerFixture,
    destination: Path,
) -> AuthenticatedConsumerArtifact:
    """Download one exact release wheel and authenticate its bytes."""
    metadata = fetch_release_asset_metadata(consumer)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / consumer.release.wheel
    if target.exists():
        raise QualificationError(
            f"refusing to overwrite existing consumer artifact {target.name}."
        )
    request = urllib.request.Request(
        metadata.browser_download_url,
        headers={"User-Agent": "pds-core-released-consumer-qualification/1"},
    )
    data = _urlopen_bytes(request)
    target.write_bytes(data)
    actual = sha256_file(target)
    if actual != metadata.sha256:
        target.unlink(missing_ok=True)
        raise QualificationError("Downloaded consumer wheel failed GitHub SHA-256.")
    if consumer.release.sha256 is not None and actual != consumer.release.sha256:
        target.unlink(missing_ok=True)
        raise QualificationError("Downloaded consumer wheel failed pinned SHA-256.")
    return AuthenticatedConsumerArtifact(
        path=target,
        sha256=actual,
        github_sha256=metadata.sha256,
    )


def _sanitized_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    return env


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> CommandResult:
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
        if len(detail) > _MAX_FAILURE_MESSAGE:
            detail = detail[-_MAX_FAILURE_MESSAGE:]
        raise QualificationError(
            f"{label} failed with exit status {completed.returncode}: {detail}"
        )
    return CommandResult(stdout=completed.stdout, stderr=completed.stderr)


def _venv_python(environment_root: Path) -> Path:
    if os.name == "nt":
        return environment_root / "Scripts" / "python.exe"
    return environment_root / "bin" / "python"


def _venv_console_script(environment_root: Path, script: str) -> Path:
    if os.name == "nt":
        return environment_root / "Scripts" / f"{script}.exe"
    return environment_root / "bin" / script


def _create_isolated_environment(environment_root: Path) -> Path:
    if environment_root.exists():
        raise QualificationError("isolated consumer environment path already exists.")
    venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(environment_root)
    python = _venv_python(environment_root)
    if not python.is_file():
        raise QualificationError("isolated consumer Python executable was not created.")
    return python


def _install_candidate_and_consumer(
    python: Path,
    *,
    candidate_wheel: Path,
    consumer_wheel: Path,
    cwd: Path,
    env: dict[str, str],
) -> None:
    _run_command(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            str(candidate_wheel),
            str(consumer_wheel),
        ],
        cwd=cwd,
        env=env,
        label="isolated consumer installation",
    )


def _run_pip_check(
    python: Path,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    _run_command(
        [str(python), "-m", "pip", "check"],
        cwd=cwd,
        env=env,
        label="pip check",
    )


def _probe_arguments(
    consumer: ConsumerFixture,
    *,
    repository_root: Path,
) -> list[str]:
    arguments = [
        "--component-id",
        consumer.component_id,
        "--distribution",
        consumer.distribution,
        "--version",
        consumer.version,
        "--import-name",
        consumer.import_name,
        "--forbidden-root",
        str(repository_root),
    ]
    for flag, target in (
        ("--routing-target", consumer.providers.routing),
        ("--publication-target", consumer.providers.publication),
        ("--module-operations-target", consumer.providers.module_operations),
    ):
        if target is not None:
            arguments.extend((flag, target))
    return arguments


def _run_installed_probe(
    python: Path,
    consumer: ConsumerFixture,
    *,
    cwd: Path,
    env: dict[str, str],
    repository_root: Path,
) -> dict[str, object]:
    probe_script = repository_root / "scripts" / "released_consumer_installed_probe.py"
    result = _run_command(
        [
            str(python),
            str(probe_script),
            *_probe_arguments(consumer, repository_root=repository_root),
        ],
        cwd=cwd,
        env=env,
        label="installed consumer/Core public-contract probe",
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise QualificationError("installed probe did not emit valid JSON.") from error
    return _mapping(value, "installed probe result")


def _run_cli_probe(
    environment_root: Path,
    consumer: ConsumerFixture,
    *,
    cwd: Path,
    env: dict[str, str],
    argument: str,
) -> None:
    executable = _venv_console_script(environment_root, consumer.console_script)
    if not executable.is_file():
        raise QualificationError(
            f"installed console script {consumer.console_script} is missing."
        )
    _run_command(
        [str(executable), argument],
        cwd=cwd,
        env=env,
        label=f"{consumer.console_script} {argument}",
    )


def _normalize_error(
    error: BaseException,
    *,
    replacements: tuple[tuple[str, str], ...],
) -> str:
    message = str(error).strip() or type(error).__name__
    for raw, replacement in replacements:
        if raw:
            message = message.replace(raw, replacement)
    if len(message) > _MAX_FAILURE_MESSAGE:
        message = message[: _MAX_FAILURE_MESSAGE - 1] + "…"
    return message


def _qualification_result(
    consumer: ConsumerFixture,
    *,
    status: str,
    artifact_sha256: str | None,
    completed_probes: list[str],
    installed_probe: dict[str, object] | None,
    failure_stage: str | None,
    failure_message: str | None,
) -> dict[str, object]:
    return {
        "component_id": consumer.component_id,
        "distribution": consumer.distribution,
        "version": consumer.version,
        "release_tag": consumer.release.tag,
        "wheel": consumer.release.wheel,
        "artifact_sha256": artifact_sha256,
        "artifact_sha256_source": consumer.release.sha256_source,
        "status": status,
        "completed_probes": completed_probes,
        "installed_probe": installed_probe,
        "failure": (
            None
            if failure_stage is None
            else {"stage": failure_stage, "message": failure_message}
        ),
    }


def qualify_consumer(
    consumer: ConsumerFixture,
    *,
    candidate_wheel: Path,
    work_root: Path,
    repository_root: Path,
) -> dict[str, object]:
    """Qualify one consumer independently and return bounded normalized evidence."""
    completed: list[str] = []
    artifact_sha256: str | None = None
    installed_probe: dict[str, object] | None = None
    stage = "release_asset_authentication"
    environment_root = work_root / "envs" / consumer.component_id
    execution_root = work_root / "runs" / consumer.component_id
    execution_root.mkdir(parents=True, exist_ok=True)
    replacements = (
        (str(work_root.resolve()), "<qualification-temp>"),
        (str(repository_root.resolve()), "<core-checkout>"),
        (str(Path.home().resolve()), "<home>"),
        (str(candidate_wheel.resolve()), f"<candidate>/{candidate_wheel.name}"),
    )
    try:
        artifact = download_authenticated_consumer_artifact(
            consumer,
            work_root / "artifacts",
        )
        artifact_sha256 = artifact.sha256
        completed.append(stage)

        stage = "consumer_wheel_metadata"
        identity: ConsumerWheelIdentity = inspect_consumer_wheel(
            artifact.path,
            consumer,
        )
        if identity.sha256 != artifact.sha256:
            raise QualificationError(
                "consumer wheel inspection digest changed after authentication."
            )
        completed.append(stage)

        stage = "isolated_installation"
        python = _create_isolated_environment(environment_root)
        env = _sanitized_environment()
        _install_candidate_and_consumer(
            python,
            candidate_wheel=candidate_wheel,
            consumer_wheel=artifact.path,
            cwd=execution_root,
            env=env,
        )
        completed.append(stage)

        stage = "pip_check"
        _run_pip_check(python, cwd=execution_root, env=env)
        completed.append(stage)

        stage = "installed_public_contracts"
        installed_probe = _run_installed_probe(
            python,
            consumer,
            cwd=execution_root,
            env=env,
            repository_root=repository_root,
        )
        completed.append(stage)

        stage = "cli_help"
        _run_cli_probe(
            environment_root,
            consumer,
            cwd=execution_root,
            env=env,
            argument="--help",
        )
        completed.append(stage)

        stage = "cli_version"
        _run_cli_probe(
            environment_root,
            consumer,
            cwd=execution_root,
            env=env,
            argument="--version",
        )
        completed.append(stage)
    except Exception as error:
        return _qualification_result(
            consumer,
            status="fail",
            artifact_sha256=artifact_sha256,
            completed_probes=completed,
            installed_probe=installed_probe,
            failure_stage=stage,
            failure_message=_normalize_error(error, replacements=replacements),
        )

    return _qualification_result(
        consumer,
        status="pass",
        artifact_sha256=artifact_sha256,
        completed_probes=completed,
        installed_probe=installed_probe,
        failure_stage=None,
        failure_message=None,
    )


def qualification_evidence(
    *,
    candidate_filename: str,
    candidate_version: str,
    candidate_sha256: str,
    consumers: list[dict[str, object]],
) -> bytes:
    """Serialize normalized qualification evidence deterministically."""
    overall = "pass" if all(item.get("status") == "pass" for item in consumers) else "fail"
    payload: dict[str, object] = {
        "record_type": QUALIFICATION_RECORD_TYPE,
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "candidate_core": {
            "filename": candidate_filename,
            "version": candidate_version,
            "sha256": candidate_sha256,
        },
        "overall_status": overall,
        "consumers": consumers,
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _write_evidence(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _run_qualification(
    *,
    core_wheel: Path,
    fixture_path: Path,
    evidence_path: Path,
    repository_root: Path,
    work_root: Path,
) -> int:
    fixture = load_compatibility_fixture(fixture_path)
    candidate = inspect_candidate_wheel(
        core_wheel,
        expected_version=fixture.candidate_core_version,
    )
    results: list[dict[str, object]] = []
    for consumer in fixture.consumers:
        result = qualify_consumer(
            consumer,
            candidate_wheel=candidate.path,
            work_root=work_root,
            repository_root=repository_root,
        )
        results.append(result)
        status = str(result["status"]).upper()
        print(f"{consumer.display_name} {consumer.version}: {status}")
        failure = result.get("failure")
        if isinstance(failure, dict):
            stage = failure.get("stage")
            message = failure.get("message")
            print(f"  stage: {stage}")
            print(f"  failure: {message}")

    evidence = qualification_evidence(
        candidate_filename=candidate.filename,
        candidate_version=candidate.version,
        candidate_sha256=candidate.sha256,
        consumers=results,
    )
    _write_evidence(evidence_path, evidence)
    passed = all(result.get("status") == "pass" for result in results)
    print(f"evidence: {evidence_path.resolve()}")
    print(
        "pds-core released-consumer qualification: "
        + ("PASS" if passed else "FAIL")
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Authenticate exact released PDS consumers and qualify them independently "
            "against one explicit pds-core 0.6.2 candidate wheel."
        )
    )
    parser.add_argument("--core-wheel", type=Path, required=True)
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
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args()

    core_wheel = args.core_wheel.resolve()
    fixture_path = args.fixture.resolve()
    evidence_path = (
        args.evidence.resolve()
        if args.evidence is not None
        else core_wheel.parent / "pds_core-0.6.2-released-consumer-qualification.json"
    )

    try:
        if args.work_root is not None:
            work_root = args.work_root.resolve()
            if work_root.exists() and any(work_root.iterdir()):
                raise QualificationError("--work-root must be absent or empty.")
            work_root.mkdir(parents=True, exist_ok=True)
            return _run_qualification(
                core_wheel=core_wheel,
                fixture_path=fixture_path,
                evidence_path=evidence_path,
                repository_root=REPOSITORY_ROOT,
                work_root=work_root,
            )

        with tempfile.TemporaryDirectory(prefix="pds-core-consumer-qualification-") as temporary:
            return _run_qualification(
                core_wheel=core_wheel,
                fixture_path=fixture_path,
                evidence_path=evidence_path,
                repository_root=REPOSITORY_ROOT,
                work_root=Path(temporary),
            )
    except (CandidateWheelError, CompatibilityFixtureError, QualificationError) as error:
        parser.exit(1, f"released-consumer qualification failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
