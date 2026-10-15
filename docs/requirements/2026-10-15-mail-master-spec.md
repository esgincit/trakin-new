# MYTRAKIN IMPLEMENTATION MASTER SPECIFICATION

You are a senior solution architect, lead developer, database architect, backend engineer, and business analyst.

Your task is to analyze the existing MyTrakin codebase and implement the complete approved business workflow while preserving compatibility with existing functionality wherever possible.

====================================================
PROJECT OBJECTIVE
====================================================

Implement the finalized MyTrakin business process and prepare the platform for internal rollout.

Priority Order:

1. Business Logic
2. Database Schema
3. APIs
4. Validation Rules
5. Test Coverage
6. UI/UX Improvements

Business logic takes precedence over UI enhancements.

====================================================
TARGET DELIVERY GOALS
====================================================

Internal Release Target:
- 25 Oct 2026

Internal Go Live:
- 30 Oct 2026

====================================================
CURRENT BUSINESS UNDERSTANDING
====================================================

The current system flow appears to be:

Register
→ Verify
→ MSA
→ Project
→ Acceptance
→ Contract
→ Acceptance
→ Timesheets
→ Invoicing

The new approved workflow must become:

Register
→ Verify
→ NDA
→ MSA
→ Project
→ SOW
→ Acceptance
→ Resource Contract
→ Acceptance
→ Timesheet
→ Invoice
→ Payment
→ Payment Confirmation

====================================================
CORE REQUIREMENTS
====================================================

Requirement #1
MULTI RESOURCE SUPPORT

A single project SOW must support multiple resources.

Example:

Project ABC

SOW-001

├── Resource 1
│    ├── Contract
│    ├── Acceptance
│    ├── Timesheets
│    ├── Invoices
│    ├── Payments
│    └── Payment Confirmation
│
├── Resource 2
│    ├── Contract
│    ├── Acceptance
│    ├── Timesheets
│    ├── Invoices
│    ├── Payments
│    └── Payment Confirmation
│
└── Resource N

Business Rules:

- One Project can contain multiple SOWs
- One SOW can contain multiple resources
- Each resource must have its own contract lifecycle
- Each resource must have independent invoicing and payment tracking

====================================================
Requirement #2
SINGLE RESOURCE SUPPORT
====================================================

The same workflow must also support:

Project

└── SOW

     └── Resource

          ├── Contract
          ├── Acceptance
          ├── Timesheet
          ├── Invoice
          ├── Payment
          └── Payment Confirmation

System should support both Single Resource and Multi Resource models using the same architecture.

====================================================
Requirement #3
NDA SUPPORT
====================================================

Introduce NDA into workflow.

Flow:

Verify
→ NDA
→ MSA

Rules:

- NDA may be required or optional
- Must support configuration-driven enforcement
- NDA must be auditable
- NDA acceptance history must be stored

====================================================
Requirement #4
MSA SUPPORT
====================================================

MSA must exist before Project creation unless bypassed through configuration.

Rules:

- Multiple MSAs can exist across customers
- Track effective dates
- Track status
- Track approvals

====================================================
Requirement #5
CONFIGURATION DRIVEN VALIDATIONS
====================================================

Company Admin must have ability to bypass mandatory checks.

Create Company/Tenant Configuration:

{
  "requireNDA": true,
  "requireMSA": true,
  "requireAcceptance": true,
  "requireContract": true
}

Examples:

Scenario A

requireNDA = true

User cannot create project until NDA completed

Scenario B

requireNDA = false

User can continue without NDA

All validations should be configuration driven.

Avoid hardcoded logic.

====================================================
Requirement #6
ENGAGEMENT MODE SUPPORT
====================================================

System must support:

- C2C
- E2E
- 1099

Design architecture so future contract types can be added without schema redesign.

Suggested:

ContractType

Id
Code
Name
IsActive

Examples:

C2C
E2E
1099

====================================================
Requirement #7
DYNAMIC NAMING ENGINE
====================================================

Create runtime naming engine.

Administrators should configure naming templates from database.

Examples:

Project:
PROJ-{YEAR}-{SEQ}

MSA:
MSA-{CLIENT}-{SEQ}

SOW:
SOW-{PROJECT}-{SEQ}

Invoice:
INV-{YYYYMM}-{SEQ}

Contract:
CON-{YEAR}-{SEQ}

Rules:

- Runtime generated
- Database configurable
- Support custom placeholders
- Support future entity types

====================================================
DATABASE ARCHITECTURE
====================================================

Analyze existing schema before modifying.

Introduce/refactor entities for:

Project

- Id
- ProjectCode
- Name
- Status
- ClientId
- CreatedDate

----------------------------------------------------

SOW

- Id
- SOWNumber
- ProjectId
- Status
- Description

----------------------------------------------------

SOWResource

- Id
- SOWId
- ResourceId
- ContractTypeId
- Status

----------------------------------------------------

NDA

- Id
- CustomerId
- Status
- EffectiveDate
- SignedDate

----------------------------------------------------

MSA

- Id
- CustomerId
- Status
- EffectiveDate
- SignedDate

----------------------------------------------------

Contract

- Id
- ResourceAssignmentId
- Status
- ContractTypeId
- EffectiveDate

----------------------------------------------------

Acceptance

- Id
- EntityType
- EntityId
- AcceptedBy
- AcceptedDate

----------------------------------------------------

Timesheet

- Id
- ResourceAssignmentId
- WeekStartDate
- Status

----------------------------------------------------

Invoice

- Id
- ResourceAssignmentId
- InvoiceNumber
- Amount
- Status

----------------------------------------------------

Payment

- Id
- InvoiceId
- Amount
- Status

----------------------------------------------------

PaymentConfirmation

- Id
- PaymentId
- ConfirmedBy
- ConfirmedOn

====================================================
RECOMMENDED STATUS MODELS
====================================================

Project

Draft
Active
Closed

----------------------------------------------------

SOW

Draft
PendingAcceptance
Accepted
Closed

----------------------------------------------------

Contract

Draft
Issued
Accepted
Completed

----------------------------------------------------

Invoice

Draft
Submitted
Approved
Paid

----------------------------------------------------

Payment

Pending
Processing
Completed
Confirmed

====================================================
API REQUIREMENTS
====================================================

Analyze existing APIs.

Implement/refactor endpoints as required.

Suggested APIs:

POST /projects

GET /projects

GET /projects/{id}

PUT /projects/{id}

----------------------------------------------------

POST /projects/{id}/sows

GET /sows/{id}

----------------------------------------------------

POST /sows/{id}/resources

GET /sows/{id}/resources

----------------------------------------------------

POST /contracts

GET /contracts/{id}

----------------------------------------------------

POST /acceptances

----------------------------------------------------

POST /timesheets

----------------------------------------------------

POST /invoices

----------------------------------------------------

POST /payments

----------------------------------------------------

POST /payment-confirmations

====================================================
WORKFLOW RULES
====================================================

Rule 1

Project cannot be activated until:
- NDA requirements satisfied
- MSA requirements satisfied

Unless bypassed via configuration.

----------------------------------------------------

Rule 2

SOW must belong to Project.

----------------------------------------------------

Rule 3

Resources belong to SOW.

----------------------------------------------------

Rule 4

Contracts belong to Resource Assignments.

----------------------------------------------------

Rule 5

Invoices derive from approved timesheets.

----------------------------------------------------

Rule 6

Payments derive from approved invoices.

----------------------------------------------------

Rule 7

Payment Confirmation finalizes financial lifecycle.

====================================================
AUDIT REQUIREMENTS
====================================================

Track:

CreatedBy
CreatedDate

ModifiedBy
ModifiedDate

StatusHistory

ApprovalHistory

AcceptanceHistory

PaymentHistory

For all major entities.

====================================================
MIGRATION REQUIREMENTS
====================================================

Analyze existing codebase.

Before introducing changes:

1. Identify current entities
2. Identify current business rules
3. Identify existing relationships
4. Produce migration strategy
5. Preserve existing data
6. Avoid breaking production flows
7. Introduce migrations incrementally

====================================================
TESTING REQUIREMENTS
====================================================

Create:

Unit Tests

Integration Tests

Workflow Tests

Regression Tests

Coverage must validate:

✓ Single Resource SOW

✓ Multi Resource SOW

✓ NDA Enabled

✓ NDA Disabled

✓ MSA Enabled

✓ MSA Disabled

✓ C2C Contracts

✓ E2E Contracts

✓ 1099 Contracts

✓ Invoice Generation

✓ Payment Lifecycle

✓ Payment Confirmation

✓ Dynamic Naming Templates

====================================================
UI REQUIREMENTS
====================================================

Review supplied HTML UX and align existing UI wherever possible.

However:

Business functionality is higher priority than UI redesign.

If delivery schedule is impacted:

Implement business logic first
UI enhancements afterward

====================================================
EXPECTED DELIVERABLES
====================================================

1. Architecture Review
2. Current vs Future Gap Analysis
3. Database Changes
4. Entity Relationship Diagram
5. API Changes
6. Migration Plan
7. Implementation Tasks
8. Code Changes
9. Tests
10. Deployment Notes
11. Rollback Strategy
12. Documentation

====================================================
SUCCESS CRITERIA
====================================================

The implementation is considered complete when:

✓ Register → Payment Confirmation works end-to-end

✓ NDA enforcement is configurable

✓ MSA enforcement is configurable

✓ One SOW supports multiple resources

✓ One SOW supports single resource

✓ Resource-specific contracts work

✓ Acceptance tracking works

✓ Timesheets generate invoices

✓ Invoices generate payments

✓ Payments support confirmation

✓ Dynamic naming engine works

✓ C2C, E2E, and 1099 workflows work

✓ Existing system remains stable

Start by analyzing the repository structure, database schema, domain models, services, APIs, and workflow implementation. Produce a gap analysis before making code changes.