# PDS Core

PDS Core contains shared infrastructure for Paper Data Suite modules.

Planned responsibilities include:

- identifier validation;
- QR payload construction and parsing;
- legacy ScoreForm `OMR1` compatibility;
- shared Paper Data Suite `PDS1` QR contracts;
- safe route/path construction;
- scan inbox/archive conventions;
- project-root conventions.

PDS Core is intended to be used by:

- `pds-scoreform`
- `pds-quillan`

Module-specific scoring, tagging, PDF layout, and reporting logic should remain in the module repositories.

## Current Status

Early setup and design.

See [`migration_plan.md`](migration_plan.md) for the current migration direction.

See [`docs/qr_payload_and_routing_contract.md`](docs/qr_payload_and_routing_contract.md) for the shared QR payload and routing contract.

## Development Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"