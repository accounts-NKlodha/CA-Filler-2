# Lodha OS (Practice Agentic OS)

The practice operating system for the firm. `CLAUDE.md` holds the rules and the build order; `STATUS.md` says what is done.

## Run

Needs Python 3.11 or newer. This step has no other dependencies.

- `start.bat`: this computer only, then open http://localhost:8750
- `start_lan.bat`: the whole office network, others open `http://<this-computer-name>:8750`

On first run it asks you to create the partner account. Then open **Settings** and set the client folders location.

## Where data is kept

| What | Where |
|---|---|
| Client master, people, settings | `data/` beside this folder (not in git). Set `LODHA_OS_DATA` to move it. |
| Each client's work and audit trail | The client's own folder, `Group name - Client name`, under the client folders location. The trail is `_os/trail.jsonl`. |

Back up `data/` with the client folders.

## Tests

`python -m unittest`

## Financials

Financials > tick clients > Get data. The OS reads this year's and last year's trial balance from Tally (the client
companies must be open in Tally) and builds the Schedule III workbook into each client folder.

Set these once in Settings:

- Client folders location.
- Form Filler folder: a checkout of the Form-Filler repo. Its `sch3/engine` is used as it is, so run its
  `sch3/setup.bat` once (openpyxl, pycel, pypdf).
- Tally host and port (default localhost, 9000).

Read contract for the Proposal Maker link: `docs/proposal-link.md`.
