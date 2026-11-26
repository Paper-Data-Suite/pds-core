# Core #242 final review repair

All 15 CI jobs passed at a510c8bb71fd6e4ad6d777cfcf83441af9cf6dd8,
including exact installed wheel and sdist on Windows and Ubuntu and
4/4 Ubuntu symlink safety vectors without skips.

Final source review identified an untested receipt-integrity edge:
a terminal output error after a successful roster commit could be
caught by the surrounding refusal handler and returned as NO_CHANGE.
Other mutation flows could lose their return receipt to failed output.

All six mutation controllers now use a narrowly scoped best-effort
outcome-notice helper after the service has reported an outcome.
Closed/broken streams and an interruption of outcome display do not
replace the already determined durability and change scopes. Prompts
and review display remain ordinary I/O; this is not permission to
commit after a failed preview. No writer or token semantics changed.

New real-capability tests exercise actual commits across workspace,
year, class, Standards membership, full roster import, and student
edits, with failed output and error streams immediately after
confirmation (OSError, ValueError, KeyboardInterrupt), and partial
class/indeterminate roster outcomes. No actual teacher data.
Requalify focused scope; rerun exact-head PR CI and installed checks.
Prior full local source and installed evidence applies to the earlier
SHA, not this repair. No merge without explicit owner approval.
