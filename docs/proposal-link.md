# Proposal Maker link: read contract

Status: written before building, as CLAUDE.md asks. Nothing here is built yet. Source read: `nkl-proposal-stream`,
`db/reviewed/v1_production_schema.sql` (main, 18 Nov 2026). The OS never changes that repo or its database.

## How the OS reads

- Over HTTPS from the office desktop, through the Lovable Cloud (Supabase) REST interface.
- As a signed-in partner account. The database gives the `authenticated` role SELECT only, and only on rows of
  firms the partner belongs to, so this path cannot write even by mistake.
- The service-role key is never used by the OS: it can write.
- The project address and the reader's sign-in are entered in Settings and stored encrypted on the desktop.
  They are never in this repo.

## What is read

| Table | Fields | Used for |
|---|---|---|
| `proposals` | id, firm_id, client_id, proposal_number, financial_year, status, subject, sent_at, expires_at, accepted_at, executed_at, renewal_due_on, updated_at | Proposals list and status; renewal reminder |
| `clients` | id, group_name, constitution, contact_person, contact_designation, email, mobile | Group and contact person in the client master |
| `client_entities` | id, client_id, position, legal_name, constitution, pan, gstin | One OS client per entity; folder `Group name - Client name` |
| `proposal_services` | proposal_id, position, service_id, name, category | Services switched on under Professional Services |
| `services` | id, code, name, category, active | Stable code for each service name |
| `proposal_fee_components` | proposal_id, position, label, amount, billing_basis, applies_from, note | Fee drafts for Billing. Partners only |
| `proposal_executed_documents` | proposal_id, file_name, sha256, storage_object_path, uploaded_at | Signed engagement letter copied to the client folder, checked against sha256 |
| `firms` | id, name | Which of the three issuing firms |

Never read: `proposal_meeting_notes`, `services.internal_rate`, `proposal_fee_components.internal_benchmark`,
`proposal_versions`, `audit_events`. The OS has no use for them, and notes and internal rates are partner-only.

## How Executed is detected

`proposals.status = 'executed'`. The schema guarantees `executed_at` is set in that status, with `sent_at` and
`accepted_at` before it. The OS polls for proposals with `updated_at` later than its last read, and prepares a client
set-up once per proposal id. Staff confirm the set-up; nothing is created in the client master before that.

Status shown in the Proposals list: draft, ready, sent, awaiting firm signature, executed, expired, declined.

## Mapping to the client master

| OS field | From |
|---|---|
| Group | `clients.group_name` |
| Client name | `client_entities.legal_name` |
| Constitution | `client_entities.constitution` (enum mapped to the OS list) |
| PAN, GSTIN | `client_entities.pan`, `client_entities.gstin` |
| Contact person, mobile, e-mail | `clients.contact_person`, `mobile`, `email` |
| Services | `proposal_services.name`, matched on `services.code` where `service_id` is set |
| Renewal reminder | `proposals.renewal_due_on` |

## Gaps (also listed in STATUS.md)

1. Reader account. Decided by the owner on 18 Nov 2026: the OS reads with an existing partner sign-in (two are
   named; the addresses are kept in Settings, not here). The password is entered in Settings by that partner.
2. CIN or LLPIN is not held in Proposal Maker. Staff enter it when confirming the set-up.
3. A proposal's services are not tied to an entity. When a group has several entities, staff choose which entity gets
   which service at confirmation.
4. Signed letter download needs read access to the storage bucket for the reader account. Not verified.
5. Tasks and due dates are not in the proposal. The OS derives them from the service and its billing basis; the rules
   are to be agreed per service line as each is built.
6. `lodha_os/services.py` holds the 16 service names from `src/data/services.ts`. It should also hold each service's
   `code`, so a renamed service still maps. To be checked against the live `services` table.
7. Proposal Maker is not in full use yet (owner, 18 Nov 2026), so the link is built and tested against made-up
   proposals first, and clients are still added by hand in the OS.
