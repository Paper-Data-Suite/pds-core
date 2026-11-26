"""Private C4B Standards browsing and reviewed membership workflow."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from pds_core.classroom_menu_school_year import _header
from pds_core.classroom_standards_commit import (
    MembershipAction,
    ProfileMembershipChange,
    StandardsReviewError,
    StandardsReviewWriteError,
    commit_profile_membership,
    inspect_standards_snapshot,
    plan_profile_membership,
)
from pds_core.teacher_context import (
    SharedTeacherMenuRequest,
    SharedTeacherMenuResult,
    TeacherChangeScope,
    TeacherDurability,
    TeacherMenuExit,
)

_PAGE = 12
_MAX_REVIEW_IDS = 100
_MAX_ID_LENGTH = 200


class _Return(Exception):
    def __init__(self, outcome: TeacherMenuExit) -> None:
        self.outcome = outcome


class _Back(Exception):
    """Return to the Standards home."""


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


class _StandardsFlow:
    def __init__(
        self,
        request: SharedTeacherMenuRequest,
        root: Path,
        read_line: Callable[[], str],
        output: TextIO,
        error_output: TextIO,
    ) -> None:
        self.request = request
        self.root = root
        self.read_line = read_line
        self.output = output
        self.errors = error_output

    def receipt(
        self,
        outcome: TeacherMenuExit,
        detail: str,
        durability: TeacherDurability = TeacherDurability.NO_CHANGE,
    ) -> SharedTeacherMenuResult:
        return SharedTeacherMenuResult(
            self.request.return_token,
            outcome,
            durability,
            frozenset()
            if durability is TeacherDurability.NO_CHANGE
            else frozenset({TeacherChangeScope.STANDARDS}),
            f"{detail} Revalidate workspace, school year, class, roster and work on return.",
        )

    def read(self, prompt: str) -> str:
        print(prompt, end="", file=self.output, flush=True)
        try:
            raw = self.read_line()
        except (EOFError, StopIteration, KeyboardInterrupt):
            raise _Return(TeacherMenuExit.CANCELLED) from None
        if type(raw) is not str:
            raise _Return(TeacherMenuExit.FAILED)
        if raw == "":
            raise _Return(TeacherMenuExit.CANCELLED)
        choice = raw.strip()
        if choice.casefold() == "b":
            raise _Back
        if choice.casefold() == "m":
            raise _Return(TeacherMenuExit.MAIN_MENU)
        if choice.casefold() == "q":
            raise _Return(TeacherMenuExit.QUIT)
        return choice

    def browse(self, *, profiles: bool) -> None:
        page = 0
        while True:
            snapshot = inspect_standards_snapshot(self.root)
            if profiles:
                rows = tuple(
                    f"{_quoted(p.profile_id)} | {_quoted((p.title or p.profile_id)[:120])} | {len(p.standards)} standards"
                    for p in snapshot.library.profiles
                )
            else:
                rows = tuple(
                    f"{_quoted(s.standard_id)} | {_quoted(s.short_name[:120])} | {'active' if s.active else 'inactive'}"
                    for s in snapshot.library.standards
                )
            page = min(page, max(0, (len(rows) - 1) // _PAGE))
            _header(
                self.request,
                "Standards profiles" if profiles else "Standards definitions",
                self.output,
            )
            print(f"Total: {len(rows)}", file=self.output)
            for row in rows[page * _PAGE : (page + 1) * _PAGE]:
                print(row, file=self.output)
            if not rows:
                print("No records found.", file=self.output)
            print(
                ">. Next  <. Previous  B. Back  M. Main Menu  Q. Quit", file=self.output
            )
            choice = self.read("Choice: ")
            if choice == ">":
                page += 1
            elif choice == "<":
                page = max(0, page - 1)

    def edit(self) -> SharedTeacherMenuResult:
        _header(self.request, "Edit profile membership", self.output)
        print(
            "1. Add standards  2. Remove standards  3. Replace membership",
            file=self.output,
        )
        print("B. Back  M. Main Menu  Q. Quit", file=self.output)
        choice = self.read("Choice: ")
        actions: dict[str, MembershipAction] = {"1": "add", "2": "remove", "3": "set"}
        if choice not in actions:
            raise _Back
        action = actions[choice]
        profile = self.read("Exact profile ID (or B/M/Q): ")
        print(
            "Enter exact standard IDs separated by commas. For empty replacement, enter NONE.",
            file=self.output,
        )
        raw = self.read("Standard IDs (or B/M/Q): ")
        ids = (
            ()
            if raw == "NONE" and action == "set"
            else tuple(item.strip() for item in raw.split(","))
        )
        if (
            not profile
            or len(profile) > _MAX_ID_LENGTH
            or len(ids) > _MAX_REVIEW_IDS
            or any(not item or len(item) > _MAX_ID_LENGTH for item in ids)
        ):
            raise StandardsReviewError(
                "invalid_change", "Profile proposal exceeds review limits."
            )
        change = ProfileMembershipChange(action, profile, ids)
        review = plan_profile_membership(self.root, change)
        if any(
            len(values) > _MAX_REVIEW_IDS
            or any(len(item) > _MAX_ID_LENGTH for item in values)
            for values in (review.before, review.after)
        ):
            raise StandardsReviewError(
                "review_limit",
                "Membership exceeds interactive review limits; use CLI preview.",
            )
        _header(self.request, "Review profile membership", self.output)
        print(
            f"Workspace: {_quoted(str(review.snapshot.workspace_root))}",
            file=self.output,
        )
        print(f"Profile: {_quoted(profile)}", file=self.output)
        print(f"Operation: {action}", file=self.output)
        print(
            f"Before: {json.dumps(review.before, ensure_ascii=True)}", file=self.output
        )
        print(f"After: {json.dumps(review.after, ensure_ascii=True)}", file=self.output)
        print(
            "Standard definitions and other profiles are preserved.", file=self.output
        )
        print("PREVIEW ONLY — no write occurred.", file=self.output)
        if (
            self.read(
                "C. Confirm exact membership  B. Cancel  M. Main Menu  Q. Quit: "
            ).casefold()
            != "c"
        ):
            raise _Back
        result = commit_profile_membership(
            self.root,
            change,
            expected_current_state_token=review.snapshot.state_token,
            expected_candidate_state_token=review.candidate_state_token,
            confirmed=True,
        )
        if result.outcome == "no_change":
            print("Membership already matched; no write.", file=self.output)
            return self.receipt(TeacherMenuExit.BACK, "Profile membership unchanged.")
        print("Profile membership committed.", file=self.output)
        return self.receipt(
            TeacherMenuExit.BACK,
            "Profile membership committed.",
            TeacherDurability.COMMITTED,
        )

    def run(self) -> SharedTeacherMenuResult | None:
        try:
            while True:
                snapshot = inspect_standards_snapshot(self.root)
                _header(self.request, "Standards management", self.output)
                print(
                    f"Standards: {len(snapshot.library.standards)}; profiles: {len(snapshot.library.profiles)}",
                    file=self.output,
                )
                print("1. Browse standards", file=self.output)
                print("2. Browse profiles", file=self.output)
                print("3. Edit existing profile membership", file=self.output)
                print("B. Back  M. Main Menu  Q. Quit", file=self.output)
                try:
                    choice = self.read("Choice: ")
                except _Back:
                    return None
                try:
                    if choice in {"1", "2"}:
                        self.browse(profiles=choice == "2")
                    elif choice == "3":
                        return self.edit()
                except _Back:
                    continue
        except _Return as nav:
            return self.receipt(nav.outcome, "Standards management returned.")
        except StandardsReviewWriteError:
            print(
                "Standards write uncertain; inspect canonical state before retry.",
                file=self.errors,
            )
            return self.receipt(
                TeacherMenuExit.FAILED,
                "Standards write outcome uncertain.",
                TeacherDurability.INDETERMINATE,
            )
        except StandardsReviewError:
            print(
                "Standards operation refused; inspect current library.",
                file=self.errors,
            )
            return self.receipt(TeacherMenuExit.FAILED, "Standards operation refused.")


def run_standards_review(
    request: SharedTeacherMenuRequest,
    *,
    workspace_root: Path,
    read_line: Callable[[], str],
    output: TextIO,
    error_output: TextIO,
) -> SharedTeacherMenuResult | None:
    return _StandardsFlow(
        request, workspace_root, read_line, output, error_output
    ).run()
