# Atlas Platform Expansion Plan

This plan sequences all requested upgrades into safe delivery phases.

## Phase 0: Stabilization (Completed in this pass)
- Universal in-page `Back to Dashboard` button injection for role tool pages.
- Existing smoke tests pass after integration.

## Phase 1: Access Control + Data Safety Foundation
- Centralize authorization checks into a single policy layer for role + ownership enforcement.
- Add DB-backed permission matrix (replace hardcoded matrix for enforcement and UI).
- Add optimistic locking/version checks on mutable records.
- Add soft-delete/restore scaffolding for critical entities.
- Add migration version table and structured migration runner.

Acceptance:
- One policy check helper is used by all protected write routes.
- Role-matrix automated tests validate allow/deny permutations.

## Phase 2: Tenant Sync Lifecycle + Reliability
- Invite lifecycle controls:
  - expiry
  - resend cooldown
  - revoke reason
  - stale pending auto-cleanup job
- Advanced tenant matching (email + phone + invite token).
- Add background job runner for reminder/escalation tasks.
- Add API rate limits for login/inquiry/apply/invite endpoints.

Acceptance:
- Invite state transitions are fully auditable.
- Expired invites cannot be accepted.

## Phase 3: Core Financials and Ledger
- Tenant ledger model:
  - charges
  - payments
  - late fees
  - running balance
  - statement periods
- Monthly statement generation + downloadable receipts.
- Auto-pay toggle and payment method vault integration points.
- Bill splitting support.

Acceptance:
- Ledger balance equals sum(charges + fees - payments) for each tenant.
- Statements reconcile with payment history.

## Phase 4: Communications + Messaging
- Replace placeholder messages with full threads:
  - participants
  - linked entities (listing/property/lease/maintenance)
  - read states
  - attachments
- Communications automation (email/SMS):
  - invites
  - lease events
  - payment due/status
  - maintenance updates
  - application updates
- Attachment file verification and malware scan hook.

Acceptance:
- Every event notification maps to a message/alert event record.

## Phase 5: Leasing + Operations Workflow
- Lease workflow end-to-end:
  - template upload
  - merge fields
  - e-sign integration
  - renewal reminders
  - termination checklist
- Unit turnover workflow:
  - move-out inspection
  - deposit deductions
  - make-ready tasks
  - listing-ready state
- Maintenance SLA engine:
  - response/resolve targets
  - overdue flags
  - escalation chain
  - SLA reports

Acceptance:
- Lease/turnover/maintenance states are deterministic and reportable.

## Phase 6: Application + Admin Workflow Hardening
- Screening pipeline for applications:
  - scoring rubric
  - document verification
  - reason codes
  - internal notes history
- Strong admin listing workflow:
  - required review checklist
  - structured reject reasons
  - resubmission flow
  - change history diff
  - undo-safe action model for admins

Acceptance:
- All admin approval/rejection actions require checklist completion and are auditable.

## Phase 7: Reporting, Performance, and Observability
- Pagination/search/sort on heavy views (payments, audits, submissions, invites, etc.).
- Cross-role reporting with filters and CSV export by:
  - date range
  - property
  - unit
  - status
  - user
- Query/index tuning and N+1 query reduction.
- Response-time and route performance logging.
- Webhook/event pipeline for critical domain events.
- Tamper-evident audit log chain.

Acceptance:
- Dashboard/report endpoints remain performant with large datasets.

## Phase 8: Platform Operations and Release Management
- Nightly backup + restore tooling + integrity checks.
- Staging config and seed-data reset command.
- Changelog screen.
- Role-based dashboard personalization (top 5-7 KPIs/actions per role).
- Role-specific onboarding tours/checklists.
- Per-property timezone handling.
- Bulk CSV import with validation preview.

Acceptance:
- Backup restore drill succeeds.
- Staging reset reproducibly returns to known baseline.

## Cross-Cutting Test Strategy
- Expand automated role-matrix tests:
  - tenant
  - landlord
  - manager
  - admin
- Add regression tests for ownership boundaries and policy checks.
- Add lifecycle tests for invites, leases, payments, maintenance, and submissions.

