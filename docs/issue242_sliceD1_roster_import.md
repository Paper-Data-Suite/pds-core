# Core #242 D1 — full-roster import composition

C4B qualified at 68de5b76f9d5e385eb2c1137ec7ee9dda8a63d04.

Private test gate only. Classes and rosters -> select class -> I opens
full-roster import. Require canonical class metadata in active school year.
Select an external complete Core-format CSV. Existing roster import preview
and commit services remain the only writer authority, with their existing
candidate/current state tokens and roster lock. Existing noninteractive
roster import-preview/import-commit commands provide service parity;
their broader legacy scope is unchanged. Shared menu adds active class/year
context, review display limits and refusal to drop existing optional columns.

The review includes both column orders, both student ID orders, counts,
full before/after records for changed students and records for added/removed
students, including optional fields and readable name plus exact student ID.
Escaped display avoids control sequences. Pages must be advanced sequentially
before one C confirmation. B cancels to parent; M/Q/EOF return to caller.
Interactive review is bounded; larger proposals are refused, not truncated.
Re-read candidate and canonical state before commit; coordinate participating
year/class operations using existing local year lock. Recheck year bytes,
class metadata and both roster tokens. Equal roster tokens are no-op.
Confirmed commit returns immediately, with ROSTER scope. Writer failure
after entering the commit service is conservatively INDETERMINATE when
write completion is uncertain. Inspect before retry; no silent retry.
Historical producer data, conflict copies and other files remain untouched.

No distributed lock or guarantee against external concurrent filesystem
changes. No new CLI write, public menu, release or merge. D2 individual
enrollment changes remain separate. Use the Git-tracked qualification runner.
