# Practice Agentic OS: instructions for the Claude session working in this repo

This file is the single source of direction for this repo. Read it at the start of every session.
The orchestrator (the Claude project that planned the firm OS) updates it; when it changes, the new version wins.
If something here is unclear or blocks you, write the question in `STATUS.md` under "Questions for orchestrator" and carry on with other work.

## What this repo is

The practice operating system for a chartered accountancy firm: one web app the whole office logs in to.
It is Project 2 of two.

| Project | Repo | Scope |
|---|---|---|
| 1. MCA automation - Form Filler | `Form-Filler` | Tally -> Schedule III financials -> staff review -> fill MCA forms (AOC-4, MGT-7/7A, ADT-1). Owned by the other Claude account. Do not change it from here. |
| 2. Practice Agentic OS (this repo) | `CA-Filler-2` | Home, proposals, clients, Professional Services (Financials, ROC, GST, Income tax, TDS, Other levies), AI (Agents at work, Queries), Office (Inbox, Billing, Settings). |

Interface between the two: the OS hands Form Filler an approved Schedule III workbook plus answers; Form Filler returns status, SRN and the filed documents. Reuse Form Filler's Tally reader and Schedule III builder; do not fork them.

## Proposal Maker link (decided by the owner, 16 Nov 2026)

Every client starts as a proposal. The Proposal Maker is a separate, existing app (repo `nkl-proposal-stream`, React on Lovable Cloud with managed Postgres, partners only). It is linked, not rebuilt. Do not change that repo from here and do not copy its screens into this one.

- The "Proposals" menu item lists proposals with their status and opens the selected one in Proposal Maker.
- The OS reads proposals one way, over HTTPS from the office desktop. It never writes to the Proposal Maker database. The connection details are a secret kept in Settings, never in this repo.
- When a proposal reaches Executed, the OS prepares a client set-up for staff to confirm once: client master (group, entities, constitution, PAN, GSTIN, contact person), the client folder with the signed engagement letter, the engaged services switched on under Professional Services, tasks and due dates, fee drafts for Billing, and the renewal reminder.
- Fees, internal rates and meeting notes are visible to partners only, in the OS as in Proposal Maker.
- The service list in the OS must use the same service names as the Proposal Maker service library, so an executed proposal maps to service lines without a lookup by hand.
- Before building: write the read contract (which tables and fields, how Executed is detected) in `docs/proposal-link.md` and list any gap in `STATUS.md`.

## Order of work

1. Skeleton: app shell with the menu below, client list, users, one folder per client (`Group name - Client name`).
   1a. Proposals link, as described above, so the client list fills from executed proposals.
2. Financials: "Get data" on one click produces the Schedule III pack for 3 clients (via the shared Schedule III engine).
3. GST annual returns: GSTR-9 and GSTR-9C, output as the official JSON / offline-utility file for upload. No screen filling of the GST portal.
4. TDS: monthly computation workflow, then quarterly return (FVU file).
5. Income tax (JSON upload), then other levies (profession tax Tamil Nadu first, FSSAI).
6. Inbox (dedicated Google Workspace mailbox, dedicated WhatsApp number through Kapso), billing drafts for Tally Prime, folder-driven agents.

Do not start a later item before the earlier one is accepted in `STATUS.md`.

## Menu (fixed)

- Home, Proposals, Clients
- Professional Services: Financials, ROC, GST, Income tax, TDS, Other levies
- AI: Agents at work, Queries
- Office: Inbox, Billing, Settings

## Rules that never bend

- Agents prepare; people commit. Agents may save drafts, send reminders and request documents. They never submit a return, never pay, never attach a DSC, never approve an invoice in Tally.
- Login, captcha, OTP, DSC, submit and payment on any government portal stay with staff.
- Outgoing mail and WhatsApp are sent only after a staff member approves. The WhatsApp bot gives no professional advice.
- Cloud AI is optional and off by default. Before anything goes to a cloud model, mask client name, CIN, PAN and GSTIN (the client's and its debtors' and creditors'). Amounts are not masked. Local AI (Ollama on the office LAN) is the default.
- Portal passwords are visible to reviewers only and stored encrypted. Never commit a secret, a client file or real client data to this repo. Test data must be synthetic.
- Every figure must be traceable: keep the chain source (Tally ledger / file) -> mapping -> working -> output field, with who and when, in the client folder. Records are kept 8 years.
- A query goes first to the local model, then to a staff reviewer the same working day, and to a partner only for doubts and critical items.
- Show a low-fidelity wireframe and get the owner's sign-off before building any new screen.
- The high-fidelity "Lodha OS design" (9 screens) was signed off by the owner on 18 Nov 2026 "for now". Build those screens to it. Screens not in it (Income tax, TDS, Other levies) still need a wireframe first.

## Engineering

- Windows desktop on the office LAN, about 10 staff, office hours. Python, standard library where it is enough, no heavy framework without a reason. English only.
- Each service line is a pack (inputs, checks, output writer) behind one common interface, so a new return type is a new pack and not a change in the core.
- Design: IBM Plex Sans, ink #1b1d21 on ground #f7f7f5, dark sidebar, 12-column grid, 24px gaps, sentence case, nothing under 13px, one filled button per screen, no invented figures in the UI.
- Work on a branch, open a pull request, keep `main` runnable. Tests for every calculation that produces a statutory figure.

## Reporting

Keep `STATUS.md` at the repo root current, at the end of every session: Done, In progress, Next, Questions for orchestrator. The orchestrator reads that file and replies by editing this one.
