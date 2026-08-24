"""Offline contracts for Core released-consumer compatibility qualification."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from email import message_from_bytes
from pathlib import Path
from typing import Final, cast

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

FIXTURE_RECORD_TYPE: Final[str] = "pds_core_released_consumer_compatibility_fixture"
FIXTURE_SCHEMA_VERSION: Final[str] = "1"
EXPECTED_CORE_VERSION: Final[str] = "0.6.3"
SOURCE_CORE_VERSION: Final[str] = "0.6.1"
PROVISIONAL_CORE_VERSION: Final[str] = "0.6.2"
REQUIRED_CONSUMERS: Final[frozenset[str]] = frozenset(
    {"scoreform", "quillan", "concord", "meridian", "vitrine"}
)
REQUIRED_QUALIFICATION_PROBES: Final[tuple[str, ...]] = (
    "release_asset_authentication",
    "consumer_wheel_metadata",
    "isolated_installation",
    "pip_check",
    "installed_public_contracts",
    "cli_help",
    "cli_version",
)
CORE_CONSOLE_SCRIPTS: Final[dict[str, str]] = {
    "pds-core": "pds_core.cli:main",
    "core": "pds_core.core_menu:main",
}
REQUIRED_CANDIDATE_FILES: Final[frozenset[str]] = frozenset(
    {
        "pds_core/__init__.py",
        "pds_core/roster_imports.py",
        "pds_core/provider_diagnostics.py",
        "pds_core/module_operations.py",
        "pds_core/cli_support/roster_imports.py",
        "pds_core/standards.py",
        "pds_core/starter_standards.py",
        "pds_core/standards_selection.py",
    }
)
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]*$")
_REPOSITORY_RE: Final[re.Pattern[str]] = re.compile(
    r"^Paper-Data-Suite/[A-Za-z0-9_.-]+$"
)


class CompatibilityFixtureError(ValueError):
    """Raised when released-consumer fixture data is invalid."""


class CandidateWheelError(ValueError):
    """Raised when a supplied Core candidate wheel is invalid."""


class ProvisionalCandidateError(RuntimeError):
    """Raised when a provisional Core candidate cannot be built safely."""


@dataclass(frozen=True, slots=True)
class ProviderExpectations:
    routing: str | None
    publication: str | None
    module_operations: str | None


@dataclass(frozen=True, slots=True)
class ConsumerRelease:
    tag: str
    wheel: str
    download_url: str
    sha256: str | None
    sha256_source: str


@dataclass(frozen=True, slots=True)
class ConsumerFixture:
    component_id: str
    display_name: str
    repository: str
    distribution: str
    import_name: str
    version: str
    requires_python: str
    core_requirement: str
    console_script: str
    qualification_probes: tuple[str, ...]
    intentional_exclusions: tuple[str, ...]
    providers: ProviderExpectations
    release: ConsumerRelease


@dataclass(frozen=True, slots=True)
class CompatibilityFixture:
    candidate_core_version: str
    consumers: tuple[ConsumerFixture, ...]

    def by_component_id(self) -> dict[str, ConsumerFixture]:
        return {consumer.component_id: consumer for consumer in self.consumers}


@dataclass(frozen=True, slots=True)
class CandidateWheelIdentity:
    path: Path
    filename: str
    distribution: str
    version: str
    requires_python: str
    sha256: str
    console_scripts: tuple[tuple[str, str], ...]
    runtime_requirements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProvisionalCandidateResult:
    wheel: Path
    wheel_sha256: str
    source_commit: str
    source_runtime_tree_sha256: str
    source_version: str
    effective_version: str


def _require_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CompatibilityFixtureError(f"{field} must be an object.")
    if any(not isinstance(key, str) for key in value):
        raise CompatibilityFixtureError(f"{field} keys must be strings.")
    return cast(dict[str, object], value)


def _require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise CompatibilityFixtureError(f"{field} must be an array.")
    return cast(list[object], value)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CompatibilityFixtureError(f"{field} must be nonempty trimmed text.")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)



def _text_tuple(value: object, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    items = _require_list(value, field)
    result = tuple(_required_text(item, f"{field}[]") for item in items)
    if not allow_empty and not result:
        raise CompatibilityFixtureError(f"{field} must not be empty.")
    if len(result) != len(set(result)):
        raise CompatibilityFixtureError(f"{field} must not contain duplicates.")
    return result

def _validate_identifier(value: str, field: str) -> str:
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise CompatibilityFixtureError(f"{field} is not a safe identifier.")
    return value


def _validate_version(value: str, field: str) -> str:
    try:
        parsed = Version(value)
    except InvalidVersion as error:
        raise CompatibilityFixtureError(f"{field} is not a valid version.") from error
    if str(parsed) != value:
        raise CompatibilityFixtureError(f"{field} must use normalized version text.")
    return value


def _validate_sha256(value: str | None, field: str) -> str | None:
    if value is not None and _SHA256_RE.fullmatch(value) is None:
        raise CompatibilityFixtureError(f"{field} must be lowercase SHA-256 hex.")
    return value


def _validate_core_requirement(text: str, candidate_version: str) -> str:
    try:
        requirement = Requirement(text)
    except InvalidRequirement as error:
        raise CompatibilityFixtureError("core_requirement is invalid.") from error
    if canonicalize_name(requirement.name) != "pds-core":
        raise CompatibilityFixtureError("core_requirement must target pds-core.")
    if requirement.marker is not None or requirement.url is not None or requirement.extras:
        raise CompatibilityFixtureError(
            "core_requirement must be a direct unmarked pds-core specifier."
        )
    if Version(candidate_version) not in requirement.specifier:
        raise CompatibilityFixtureError(
            f"core_requirement does not accept Core {candidate_version}."
        )
    return text


def _parse_provider_expectations(value: object, prefix: str) -> ProviderExpectations:
    raw = _require_mapping(value, prefix)
    expected_keys = {"routing", "publication", "module_operations"}
    if set(raw) != expected_keys:
        raise CompatibilityFixtureError(
            f"{prefix} must contain exactly {sorted(expected_keys)!r}."
        )
    return ProviderExpectations(
        routing=_optional_text(raw["routing"], f"{prefix}.routing"),
        publication=_optional_text(raw["publication"], f"{prefix}.publication"),
        module_operations=_optional_text(
            raw["module_operations"], f"{prefix}.module_operations"
        ),
    )


def _parse_release(value: object, prefix: str) -> ConsumerRelease:
    raw = _require_mapping(value, prefix)
    expected_keys = {"tag", "wheel", "download_url", "sha256", "sha256_source"}
    if set(raw) != expected_keys:
        raise CompatibilityFixtureError(
            f"{prefix} must contain exactly {sorted(expected_keys)!r}."
        )
    tag = _required_text(raw["tag"], f"{prefix}.tag")
    if not tag.startswith("v"):
        raise CompatibilityFixtureError(f"{prefix}.tag must begin with 'v'.")
    wheel = _required_text(raw["wheel"], f"{prefix}.wheel")
    if not wheel.endswith(".whl"):
        raise CompatibilityFixtureError(f"{prefix}.wheel must name a wheel.")
    download_url = _required_text(raw["download_url"], f"{prefix}.download_url")
    if not download_url.startswith("https://github.com/Paper-Data-Suite/"):
        raise CompatibilityFixtureError(
            f"{prefix}.download_url must be a Paper-Data-Suite GitHub URL."
        )
    sha_raw = raw["sha256"]
    if sha_raw is not None and not isinstance(sha_raw, str):
        raise CompatibilityFixtureError(f"{prefix}.sha256 must be text or null.")
    sha256 = _validate_sha256(sha_raw, f"{prefix}.sha256")
    sha256_source = _required_text(raw["sha256_source"], f"{prefix}.sha256_source")
    if sha256 is None and sha256_source != "github-release-asset-digest":
        raise CompatibilityFixtureError(
            f"{prefix} without a pinned SHA-256 must require GitHub asset digest authority."
        )
    return ConsumerRelease(
        tag=tag,
        wheel=wheel,
        download_url=download_url,
        sha256=sha256,
        sha256_source=sha256_source,
    )


def _parse_consumer(value: object, candidate_version: str) -> ConsumerFixture:
    raw = _require_mapping(value, "consumer")
    expected_keys = {
        "component_id",
        "display_name",
        "repository",
        "distribution",
        "import_name",
        "version",
        "requires_python",
        "core_requirement",
        "console_script",
        "qualification_probes",
        "intentional_exclusions",
        "providers",
        "release",
    }
    if set(raw) != expected_keys:
        raise CompatibilityFixtureError(
            f"consumer must contain exactly {sorted(expected_keys)!r}."
        )
    component_id = _validate_identifier(
        _required_text(raw["component_id"], "component_id"), "component_id"
    )
    repository = _required_text(raw["repository"], "repository")
    if _REPOSITORY_RE.fullmatch(repository) is None:
        raise CompatibilityFixtureError("repository must be a Paper-Data-Suite slug.")
    distribution = _required_text(raw["distribution"], "distribution")
    import_name = _required_text(raw["import_name"], "import_name")
    if not import_name.replace("_", "").isalnum():
        raise CompatibilityFixtureError("import_name is invalid.")
    version = _validate_version(_required_text(raw["version"], "version"), "version")
    core_requirement = _validate_core_requirement(
        _required_text(raw["core_requirement"], "core_requirement"),
        candidate_version,
    )
    console_script = _required_text(raw["console_script"], "console_script")
    qualification_probes = _text_tuple(
        raw["qualification_probes"], "qualification_probes", allow_empty=False
    )
    if qualification_probes != REQUIRED_QUALIFICATION_PROBES:
        raise CompatibilityFixtureError(
            "qualification_probes must match the complete deterministic #195 probe sequence."
        )
    intentional_exclusions = _text_tuple(
        raw["intentional_exclusions"], "intentional_exclusions", allow_empty=True
    )
    release = _parse_release(raw["release"], f"{component_id}.release")
    if release.tag != f"v{version}":
        raise CompatibilityFixtureError(
            f"{component_id} release tag must match exact version."
        )
    expected_url = (
        f"https://github.com/{repository}/releases/download/"
        f"{release.tag}/{release.wheel}"
    )
    if release.download_url != expected_url:
        raise CompatibilityFixtureError(
            f"{component_id} download URL must identify the exact pinned release asset."
        )
    try:
        wheel_distribution, wheel_version, wheel_build, wheel_tags = parse_wheel_filename(
            release.wheel
        )
    except InvalidWheelFilename as error:
        raise CompatibilityFixtureError(
            f"{component_id} release wheel filename is invalid."
        ) from error
    if canonicalize_name(wheel_distribution) != canonicalize_name(distribution):
        raise CompatibilityFixtureError(
            f"{component_id} wheel distribution does not match fixture distribution."
        )
    if str(wheel_version) != version or wheel_build:
        raise CompatibilityFixtureError(
            f"{component_id} wheel must identify the exact unbuilt release version."
        )
    if {str(tag) for tag in wheel_tags} != {"py3-none-any"}:
        raise CompatibilityFixtureError(
            f"{component_id} fixture expects the exact py3-none-any release wheel."
        )
    return ConsumerFixture(
        component_id=component_id,
        display_name=_required_text(raw["display_name"], "display_name"),
        repository=repository,
        distribution=distribution,
        import_name=import_name,
        version=version,
        requires_python=_required_text(raw["requires_python"], "requires_python"),
        core_requirement=core_requirement,
        console_script=console_script,
        qualification_probes=qualification_probes,
        intentional_exclusions=intentional_exclusions,
        providers=_parse_provider_expectations(
            raw["providers"], f"{component_id}.providers"
        ),
        release=release,
    )


def load_compatibility_fixture(path: Path) -> CompatibilityFixture:
    """Load and validate the exact released-consumer fixture manifest."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompatibilityFixtureError(f"Could not read fixture {path}.") from error
    root = _require_mapping(value, "fixture")
    expected_keys = {
        "record_type",
        "schema_version",
        "candidate_core_version",
        "consumers",
    }
    if set(root) != expected_keys:
        raise CompatibilityFixtureError(
            f"fixture must contain exactly {sorted(expected_keys)!r}."
        )
    if root["record_type"] != FIXTURE_RECORD_TYPE:
        raise CompatibilityFixtureError("fixture record_type is unsupported.")
    if root["schema_version"] != FIXTURE_SCHEMA_VERSION:
        raise CompatibilityFixtureError("fixture schema_version is unsupported.")
    candidate_version = _validate_version(
        _required_text(root["candidate_core_version"], "candidate_core_version"),
        "candidate_core_version",
    )
    if candidate_version != EXPECTED_CORE_VERSION:
        raise CompatibilityFixtureError(
            f"fixture must target Core {EXPECTED_CORE_VERSION}."
        )
    consumers = tuple(
        _parse_consumer(item, candidate_version)
        for item in _require_list(root["consumers"], "consumers")
    )
    ids = [item.component_id for item in consumers]
    if len(ids) != len(set(ids)):
        raise CompatibilityFixtureError("fixture contains duplicate component_id values.")
    if frozenset(ids) != REQUIRED_CONSUMERS:
        raise CompatibilityFixtureError(
            "fixture must contain exactly ScoreForm, Quillan, Concord, Meridian, and Vitrine."
        )
    ordered = tuple(sorted(consumers, key=lambda item: item.component_id))
    return CompatibilityFixture(candidate_core_version=candidate_version, consumers=ordered)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_metadata(archive: zipfile.ZipFile) -> tuple[bytes, bytes]:
    names = archive.namelist()
    metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
    entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
    if len(metadata_names) != 1:
        raise CandidateWheelError("candidate wheel must contain exactly one METADATA file.")
    if len(entry_names) != 1:
        raise CandidateWheelError(
            "candidate wheel must contain exactly one entry_points.txt file."
        )
    return archive.read(metadata_names[0]), archive.read(entry_names[0])


def _parse_console_scripts(data: bytes) -> tuple[tuple[str, str], ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateWheelError("entry_points.txt must be UTF-8.") from error
    current_group: str | None = None
    scripts: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1]
            continue
        if current_group != "console_scripts" or "=" not in line:
            continue
        name, target = (part.strip() for part in line.split("=", maxsplit=1))
        if name:
            scripts[name] = target
    return tuple(sorted(scripts.items()))


def inspect_candidate_wheel(
    path: Path,
    *,
    expected_version: str = EXPECTED_CORE_VERSION,
) -> CandidateWheelIdentity:
    """Inspect one supplied Core wheel without importing from it."""
    candidate = path.resolve()
    if not candidate.is_file():
        raise CandidateWheelError(f"candidate wheel does not exist: {candidate}")
    if candidate.suffix != ".whl":
        raise CandidateWheelError("candidate path must name a wheel.")
    expected_filename = f"pds_core-{expected_version}-py3-none-any.whl"
    if candidate.name != expected_filename:
        raise CandidateWheelError(
            f"candidate wheel filename must be {expected_filename}."
        )
    try:
        with zipfile.ZipFile(candidate) as archive:
            metadata_bytes, entry_points = _wheel_metadata(archive)
            names = set(archive.namelist())
            missing = sorted(REQUIRED_CANDIDATE_FILES - names)
            if missing:
                raise CandidateWheelError(
                    f"candidate wheel is missing required Core files: {missing!r}."
                )
            if not any(
                name.startswith("pds_core/starter_data/standards/")
                and name.endswith(".json")
                for name in names
            ):
                raise CandidateWheelError(
                    "candidate wheel is missing starter standards package data."
                )
            init_text = archive.read("pds_core/__init__.py").decode("utf-8")
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise CandidateWheelError("candidate wheel is unreadable or malformed.") from error
    metadata = message_from_bytes(metadata_bytes)
    distribution = metadata.get("Name")
    version = metadata.get("Version")
    requires_python = metadata.get("Requires-Python")
    if distribution != "pds-core":
        raise CandidateWheelError("candidate distribution must be pds-core.")
    if version != expected_version:
        raise CandidateWheelError(
            f"candidate distribution version must be {expected_version}."
        )
    if requires_python != ">=3.11":
        raise CandidateWheelError("candidate Requires-Python must remain >=3.11.")
    runtime_requirements: list[str] = []
    for raw_requirement in metadata.get_all("Requires-Dist", []):
        try:
            requirement = Requirement(raw_requirement)
        except InvalidRequirement as error:
            raise CandidateWheelError(
                "candidate wheel contains malformed Requires-Dist metadata."
            ) from error
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            runtime_requirements.append(raw_requirement)
    if runtime_requirements:
        raise CandidateWheelError(
            "candidate Core wheel must not add unconditional runtime dependencies."
        )
    runtime_version_line = f'__version__ = "{expected_version}"'
    if runtime_version_line not in init_text:
        raise CandidateWheelError(
            "candidate pds_core.__version__ does not match distribution metadata."
        )
    scripts = dict(_parse_console_scripts(entry_points))
    for name, target in CORE_CONSOLE_SCRIPTS.items():
        if scripts.get(name) != target:
            raise CandidateWheelError(
                f"candidate wheel is missing expected console script {name}."
            )
    return CandidateWheelIdentity(
        path=candidate,
        filename=candidate.name,
        distribution=distribution,
        version=version,
        requires_python=requires_python,
        sha256=sha256_file(candidate),
        console_scripts=tuple(sorted(scripts.items())),
        runtime_requirements=tuple(runtime_requirements),
    )


def runtime_tree_sha256(repo_root: Path) -> str:
    """Hash package-relevant source bytes deterministically for provisional evidence."""
    root = repo_root.resolve()
    paths = [root / "pyproject.toml", root / "README.md", root / "LICENSE"]
    paths.extend(
        sorted(
            path
            for path in (root / "pds_core").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    )
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise ProvisionalCandidateError(
                f"package-relevant source path is missing: {path.relative_to(root)}"
            )
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ProvisionalCandidateError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _copy_repository_for_provisional_build(source: Path, target: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git",
        ".venv",
        "build",
        "dist",
        "*.egg-info",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    )
    shutil.copytree(source, target, ignore=ignored)


def _substitute_provisional_version(build_root: Path) -> None:
    pyproject = build_root / "pyproject.toml"
    init_file = build_root / "pds_core" / "__init__.py"
    pyproject_text = pyproject.read_text(encoding="utf-8")
    init_text = init_file.read_text(encoding="utf-8")
    source_project = f'version = "{SOURCE_CORE_VERSION}"'
    target_project = f'version = "{PROVISIONAL_CORE_VERSION}"'
    source_runtime = f'__version__ = "{SOURCE_CORE_VERSION}"'
    target_runtime = f'__version__ = "{PROVISIONAL_CORE_VERSION}"'
    if pyproject_text.count(source_project) != 1:
        raise ProvisionalCandidateError(
            "source pyproject does not contain exactly one expected Core version field."
        )
    if init_text.count(source_runtime) != 1:
        raise ProvisionalCandidateError(
            "source pds_core.__version__ does not match the expected pre-release baseline."
        )
    pyproject.write_text(
        pyproject_text.replace(source_project, target_project), encoding="utf-8"
    )
    init_file.write_text(init_text.replace(source_runtime, target_runtime), encoding="utf-8")


def build_provisional_candidate(
    repo_root: Path,
    output_dir: Path,
) -> ProvisionalCandidateResult:
    """Build a non-release 0.6.2 wheel from a temporary copy of the current source."""
    root = repo_root.resolve()
    out = output_dir.resolve()
    if not (root / ".git").exists():
        raise ProvisionalCandidateError("repo_root must be a Git working tree.")
    if not (root / "pyproject.toml").is_file() or not (root / "pds_core").is_dir():
        raise ProvisionalCandidateError("repo_root is not the pds-core source tree.")
    try:
        out.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProvisionalCandidateError(
            "provisional candidate output must be outside the Core source tree."
        )
    source_pyproject = (root / "pyproject.toml").read_bytes()
    source_init = (root / "pds_core" / "__init__.py").read_bytes()
    source_commit = _git(root, "rev-parse", "HEAD")
    source_digest = runtime_tree_sha256(root)
    out.mkdir(parents=True, exist_ok=True)
    expected_wheel = out / f"pds_core-{PROVISIONAL_CORE_VERSION}-py3-none-any.whl"
    if expected_wheel.exists():
        raise ProvisionalCandidateError(
            f"refusing to overwrite existing candidate wheel: {expected_wheel}"
        )

    with tempfile.TemporaryDirectory(prefix="pds-core-v062-provisional-") as temporary:
        build_root = Path(temporary) / "source"
        _copy_repository_for_provisional_build(root, build_root)
        _substitute_provisional_version(build_root)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--outdir",
                str(out),
                str(build_root),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ProvisionalCandidateError(f"provisional wheel build failed: {detail}")

    if (root / "pyproject.toml").read_bytes() != source_pyproject:
        raise ProvisionalCandidateError("provisional build modified repository pyproject.toml.")
    if (root / "pds_core" / "__init__.py").read_bytes() != source_init:
        raise ProvisionalCandidateError("provisional build modified pds_core/__init__.py.")
    identity = inspect_candidate_wheel(
        expected_wheel,
        expected_version=PROVISIONAL_CORE_VERSION,
    )
    return ProvisionalCandidateResult(
        wheel=identity.path,
        wheel_sha256=identity.sha256,
        source_commit=source_commit,
        source_runtime_tree_sha256=source_digest,
        source_version=SOURCE_CORE_VERSION,
        effective_version=PROVISIONAL_CORE_VERSION,
    )


def provisional_result_json(result: ProvisionalCandidateResult) -> bytes:
    payload = {
        "artifact_status": "provisional-non-release",
        "effective_version": result.effective_version,
        "record_type": "pds_core_provisional_compatibility_candidate",
        "schema_version": "1",
        "source_commit": result.source_commit,
        "source_runtime_tree_sha256": result.source_runtime_tree_sha256,
        "source_version": result.source_version,
        "wheel": result.wheel.name,
        "wheel_sha256": result.wheel_sha256,
    }
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ConsumerWheelIdentity:
    """Authenticated metadata inspected from one exact released consumer wheel."""

    path: Path
    filename: str
    distribution: str
    version: str
    requires_python: str
    sha256: str
    core_requirement: str
    console_script_target: str
    routing_target: str | None
    publication_target: str | None
    module_operations_target: str | None


def _parse_entry_point_groups(data: bytes) -> dict[str, dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateWheelError("entry_points.txt must be UTF-8.") from error
    groups: dict[str, dict[str, str]] = {}
    current_group: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1].strip()
            groups.setdefault(current_group, {})
            continue
        if current_group is None or "=" not in line:
            continue
        name, target = (part.strip() for part in line.split("=", maxsplit=1))
        if not name or not target:
            raise CandidateWheelError("entry_points.txt contains an empty entry point.")
        group = groups.setdefault(current_group, {})
        if name in group:
            raise CandidateWheelError(
                f"entry_points.txt contains duplicate entry point {current_group}:{name}."
            )
        group[name] = target
    return groups


def _matching_core_requirement(
    metadata_requirements: list[str],
    expected_text: str,
) -> str:
    expected = Requirement(expected_text)
    candidates: list[Requirement] = []
    for raw in metadata_requirements:
        try:
            requirement = Requirement(raw)
        except InvalidRequirement as error:
            raise CandidateWheelError(
                "consumer wheel contains malformed Requires-Dist metadata."
            ) from error
        if canonicalize_name(requirement.name) == "pds-core":
            candidates.append(requirement)
    if len(candidates) != 1:
        raise CandidateWheelError(
            "consumer wheel must declare exactly one pds-core runtime requirement."
        )
    actual = candidates[0]
    if (
        actual.extras
        or actual.marker is not None
        or actual.url is not None
        or actual.specifier != expected.specifier
    ):
        raise CandidateWheelError(
            "consumer wheel pds-core requirement does not match the fixture."
        )
    return str(actual)


def _require_provider_group(
    groups: dict[str, dict[str, str]],
    *,
    group_name: str,
    component_id: str,
    expected_target: str | None,
) -> str | None:
    actual = groups.get(group_name, {})
    if expected_target is None:
        if actual:
            raise CandidateWheelError(
                f"consumer wheel unexpectedly declares {group_name} entry points."
            )
        return None
    expected = {component_id: expected_target}
    if actual != expected:
        raise CandidateWheelError(
            f"consumer wheel {group_name} entry points do not match the fixture."
        )
    return expected_target


def inspect_consumer_wheel(
    path: Path,
    consumer: ConsumerFixture,
) -> ConsumerWheelIdentity:
    """Inspect an exact released consumer wheel before isolated installation."""
    wheel = path.resolve()
    if not wheel.is_file():
        raise CandidateWheelError(f"consumer wheel does not exist: {wheel}")
    if wheel.name != consumer.release.wheel:
        raise CandidateWheelError(
            f"consumer wheel filename must be {consumer.release.wheel}."
        )
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_bytes, entry_points_bytes = _wheel_metadata(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise CandidateWheelError("consumer wheel is unreadable or malformed.") from error

    metadata = message_from_bytes(metadata_bytes)
    distribution = metadata.get("Name")
    version = metadata.get("Version")
    requires_python = metadata.get("Requires-Python")
    if distribution is None or canonicalize_name(distribution) != canonicalize_name(
        consumer.distribution
    ):
        raise CandidateWheelError("consumer wheel distribution does not match fixture.")
    if version is None or version != consumer.version:
        raise CandidateWheelError("consumer wheel version does not match fixture.")
    if requires_python is None or requires_python != consumer.requires_python:
        raise CandidateWheelError(
            "consumer wheel Requires-Python does not match fixture."
        )

    core_requirement = _matching_core_requirement(
        list(metadata.get_all("Requires-Dist", [])),
        consumer.core_requirement,
    )
    groups = _parse_entry_point_groups(entry_points_bytes)
    console_scripts = groups.get("console_scripts", {})
    console_target = console_scripts.get(consumer.console_script)
    if console_target is None:
        raise CandidateWheelError(
            f"consumer wheel is missing console script {consumer.console_script}."
        )

    routing_target = _require_provider_group(
        groups,
        group_name="paper_data_suite.modules",
        component_id=consumer.component_id,
        expected_target=consumer.providers.routing,
    )
    publication_target = _require_provider_group(
        groups,
        group_name="paper_data_suite.publication_producers",
        component_id=consumer.component_id,
        expected_target=consumer.providers.publication,
    )
    operations_target = _require_provider_group(
        groups,
        group_name="paper_data_suite.module_operations",
        component_id=consumer.component_id,
        expected_target=consumer.providers.module_operations,
    )

    return ConsumerWheelIdentity(
        path=wheel,
        filename=wheel.name,
        distribution=distribution,
        version=version,
        requires_python=requires_python,
        sha256=sha256_file(wheel),
        core_requirement=core_requirement,
        console_script_target=console_target,
        routing_target=routing_target,
        publication_target=publication_target,
        module_operations_target=operations_target,
    )
