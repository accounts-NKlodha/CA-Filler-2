# Status

Last updated: 18 Nov 2026, by the orchestrator session.

## Done
- Step 1, skeleton (pull request #1): app shell with the fixed menu, first-run set-up, sign-in, three roles, client
  master with PAN, GSTIN, CIN checks, one folder per client (`Group name - Client name`), audit trail in each client
  folder (`_os/trail.jsonl`), Settings. Port 8750. `python -m lodha_os.server`, or `start.bat`.
- Step 2, Financials "Get data" (same pull request): tick clients, one click reads this year and last year from Tally
  and builds the Schedule III workbook, one client after another. Engine is loaded from the Form-Filler checkout set
  in Settings (`sch3/engine`), not copied. Files use Form Filler's layout inside the client folder
  (`financials/config.json`, `financials/<FY>/tb_cy.csv`, `tb_py.csv`, `last_build.json`). When a company is not open
  in Tally, staff pick from the open companies. Review points come from the workbook's Checks sheet and from ledger
  heads nobody has approved.
- Step 2, reviewer's part (same pull request): Ledger heads screen (reviewer confirms or changes the proposed head for
  each ledger, recorded per ledger with the name, then the workbook is rebuilt), review points cleared with a written
  reason, and the "Verified, OK to file" tick. The tick is refused while a point is open or the workbook is out of
  date, and is withdrawn by any new build or head change. Reviewer and partner only. State is kept in
  `financials/<FY>/review.json`.
- Step 1a, read contract only: `docs/proposal-link.md`.
- Tests: `python -m unittest discover -s tests` (61). Set `LODHA_OS_FORM_FILLER` to a Form-Filler checkout to also run
  one real Schedule III build on a synthetic trial balance.

## In progress
- Nothing. Waiting for the owner to merge pull request #1 and run Get data on 3 real clients at the office desktop.

## Next
- Financials, third part: upload of a trial balance file when Tally is not available, Setup values (rounding, dates),
  and the documents of the pack (notes, board report, auditor report, minutes) through the engine's `make_docs_std.py`.
- Hand-off to Form Filler: approved workbook plus answers out, status and SRN back.
- Proposals link (1a) once the gaps in `docs/proposal-link.md` are answered.
- Apply the high-fidelity design (signed off by the owner on 18 Nov 2026, for now).

## Not verified
- Get data against a live Tally. The cloud session cannot reach Tally; tests use a stand-in for Tally and the real
  engine for the build.

## Questions for orchestrator
