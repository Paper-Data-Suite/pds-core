# Core #242 C3B5 — guarded empty-class creation

Source candidate only. C3B4 accepted at c7b0f736944734a74aefa1099af49c9baa79111b.

The service composes the C3B1 read-only plan and existing class metadata factory,
serializer and canonical loader. The reviewed tokens bind workspace, year state,
class destination and explicit timezone-aware creation timestamp. No roster is
created. The C3B2 local year lock coordinates participating year and class writers.
Revalidate the proposal under that lock immediately before creating the destination.
Never overwrite existing class folders or class metadata.

Stage the validated class record outside the classes collection using the existing
atomic metadata writer; create the canonical class directory exclusively; publish
the staged file with a no-replace hard link. Filesystems that cannot perform that
operation fail closed. This is a local coordination boundary, not a distributed
transaction or a guarantee against uncoordinated writers, sync providers or
filesystem redirection races. A newly created classes collection may remain even
if no canonical class is created.

After an interrupted operation, bounded read-only recovery reports absent,
empty_directory, matches_review or conflict. These are observations, not proof
of ownership. A known created empty folder is reported partial; ambiguous
post-publication state is indeterminate even if metadata matches the review.
Do not automatically delete, adopt, overwrite or retry a partial destination.
An empty orphan requires separate operator inspection and an explicitly approved
recovery policy before reuse. A matching record can be inspected as existing
class data; it does not retroactively constitute a successful commit receipt.
Stage cleanup is best effort through the temporary-directory context.
No automatic stale-lock removal.

Acceptance: scoped autoformat, Ruff format/lint, mypy, focused class-commit,
admin-preview, year-commit, school-year CLI and staged teacher menu tests.
No CLI registration, teacher menu wiring, public capability, merge or release.
Next: qualify class CLI parity and define the teacher-facing recovery path.
