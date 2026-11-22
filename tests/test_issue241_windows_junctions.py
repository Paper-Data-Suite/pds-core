"""Core #241 B2: Windows junction refusal without symlink privileges."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pds_core.classes import write_class_roster
from pds_core.roster_edits import (
    StudentRosterChange,
    StudentRosterEditWriteError,
    plan_student_roster_edit,
)
from pds_core.rosters import create_roster, load_roster

CLASS_ID = "english12_p2"


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows junctions")
@pytest.mark.parametrize("level", ["classes", "class"])
def test_windows_directory_junction_cannot_redirect_roster(
    tmp_path: Path, level: str
) -> None:
    root = tmp_path / "primary"
    roster = create_roster(
        CLASS_ID,
        [
            {
                "student_id": "0007",
                "first_name": "Ari",
                "last_name": "Rivera",
                "period": "2",
            },
            {
                "student_id": "0011",
                "first_name": "Casey",
                "last_name": "Park",
                "period": "2",
            },
        ],
    )
    original = write_class_roster(root, roster)
    before = original.read_bytes()
    foreign = tmp_path / "foreign"
    foreign.mkdir()

    if level == "classes":
        link = root / "classes"
        target = foreign / "classes"
    else:
        link = root / "classes" / CLASS_ID
        target = foreign / CLASS_ID

    link.rename(target)

    # Windows directory junctions ordinarily need neither elevation nor
    # Developer Mode, unlike symlinks. A failed creation is a real test failure.
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, "Windows junction creation failed"
    assert link.is_dir()

    with pytest.raises(StudentRosterEditWriteError) as raised:
        plan_student_roster_edit(
            root,
            CLASS_ID,
            StudentRosterChange("update", "0007", {"period": "3"}),
        )

    assert raised.value.reason == "unsafe_path"
    observed = target / "roster.csv"
    if level == "classes":
        observed = target / CLASS_ID / "roster.csv"
    assert load_roster(observed).students[0].period == "2"
    assert observed.read_bytes() == before
