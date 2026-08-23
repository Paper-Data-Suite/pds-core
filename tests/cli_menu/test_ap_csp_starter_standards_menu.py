"""Interactive menu coverage for the AP CSP Fall 2023 reference pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library
from tests.cli_menu.conftest import library_file, run_menu


def test_menu_can_select_and_install_ap_csp_as_first_sorted_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n4\n1\nYES\n\n5\n6\n",
    )
    assert code == 0
    assert "1. AP Computer Science Principles Fall 2023 Framework References" in out
    assert "Pack ID: ap_csp_fall_2023" in out
    assert "Grade bands: not specified" in out
    assert "Framework IDs: ap_csp_fall_2023" in out
    assert "Installed starter standards pack: ap_csp_fall_2023" in out
    assert err == ""
    library = load_standards_library(library_file(tmp_path))
    assert len(library.standards) == 95
    assert len(library.profiles) == 3
    assert len(library.frameworks) == 1
    assert not (tmp_path / "standards" / "usage").exists()
