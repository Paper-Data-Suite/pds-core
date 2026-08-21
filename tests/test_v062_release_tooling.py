from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_v062_release_artifacts import (
    REQUIRED_MODULES,
    SDIST_NAME,
    WHEEL_NAME,
    verify_sdist,
    verify_wheel,
)
from scripts.write_v062_release_checksums import write_checksums


def _metadata(*, runtime_requirement: str | None = None) -> bytes:
    lines = [
        "Metadata-Version: 2.4",
        "Name: pds-core",
        "Version: 0.6.2",
        "Requires-Python: >=3.11",
        "License-Expression: MIT",
        "License-File: LICENSE",
    ]
    if runtime_requirement is not None:
        lines.append(f"Requires-Dist: {runtime_requirement}")
    return ("\n".join((*lines, ""))).encode("utf-8")


def _write_wheel(
    root: Path,
    *,
    runtime_requirement: str | None = None,
    omit_module: str | None = None,
) -> Path:
    path = root / WHEEL_NAME
    dist_info = "pds_core-0.6.2.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            _metadata(runtime_requirement=runtime_requirement),
        )
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            (
                "[console_scripts]\n"
                "core = pds_core.core_menu:main\n"
                "pds-core = pds_core.cli:main\n"
            ).encode("utf-8"),
        )
        archive.writestr(f"{dist_info}/licenses/LICENSE", b"synthetic license\n")
        archive.writestr("pds_core/__init__.py", b'__version__ = "0.6.2"\n')
        archive.writestr(
            "pds_core/starter_data/standards/synthetic.json",
            b"{}\n",
        )
        for module in sorted(REQUIRED_MODULES):
            if module != omit_module:
                archive.writestr(module, b"# synthetic\n")
    return path


def _add_tar_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


def _write_sdist(root: Path, *, omit_module: str | None = None) -> Path:
    path = root / SDIST_NAME
    archive_root = "pds_core-0.6.2"
    with tarfile.open(path, "w:gz") as archive:
        _add_tar_bytes(archive, f"{archive_root}/PKG-INFO", _metadata())
        _add_tar_bytes(archive, f"{archive_root}/LICENSE", b"synthetic license\n")
        _add_tar_bytes(
            archive,
            f"{archive_root}/pds_core/__init__.py",
            b'__version__ = "0.6.2"\n',
        )
        _add_tar_bytes(
            archive,
            f"{archive_root}/pds_core/starter_data/standards/synthetic.json",
            b"{}\n",
        )
        for module in sorted(REQUIRED_MODULES):
            if module != omit_module:
                _add_tar_bytes(archive, f"{archive_root}/{module}", b"# synthetic\n")
    return path


def test_v062_release_artifact_verifier_accepts_exact_artifacts(
    tmp_path: Path,
) -> None:
    wheel = _write_wheel(tmp_path)
    sdist = _write_sdist(tmp_path)

    wheel_identity = verify_wheel(wheel)
    sdist_identity = verify_sdist(sdist)

    assert wheel_identity.filename == WHEEL_NAME
    assert sdist_identity.filename == SDIST_NAME
    assert wheel_identity.version == "0.6.2"
    assert sdist_identity.version == "0.6.2"


def test_v062_release_artifact_verifier_rejects_runtime_dependency(
    tmp_path: Path,
) -> None:
    wheel = _write_wheel(tmp_path, runtime_requirement="requests>=2")
    with pytest.raises(ValueError, match="runtime dependencies"):
        verify_wheel(wheel)


def test_v062_release_artifact_verifier_rejects_missing_new_surface(
    tmp_path: Path,
) -> None:
    missing = "pds_core/module_operations.py"
    wheel = _write_wheel(tmp_path, omit_module=missing)
    with pytest.raises(ValueError, match="missing required Core modules"):
        verify_wheel(wheel)

    sdist = _write_sdist(tmp_path, omit_module=missing)
    with pytest.raises(ValueError, match="sdist is missing"):
        verify_sdist(sdist)


def test_v062_checksum_writer_is_deterministic_and_exact(tmp_path: Path) -> None:
    wheel = tmp_path / WHEEL_NAME
    sdist = tmp_path / SDIST_NAME
    wheel.write_bytes(b"wheel-bytes")
    sdist.write_bytes(b"sdist-bytes")
    output = tmp_path / "SHA256SUMS.txt"

    first = write_checksums(wheel, sdist, output).read_bytes()
    second = write_checksums(wheel, sdist, output).read_bytes()

    assert first == second
    text = first.decode("ascii")
    assert WHEEL_NAME in text
    assert SDIST_NAME in text
    assert len(text.splitlines()) == 2


def test_v062_checksum_writer_rejects_wrong_artifact_name(tmp_path: Path) -> None:
    wheel = tmp_path / "wrong.whl"
    sdist = tmp_path / SDIST_NAME
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    with pytest.raises(ValueError, match="must be exactly"):
        write_checksums(wheel, sdist, tmp_path / "SHA256SUMS.txt")
