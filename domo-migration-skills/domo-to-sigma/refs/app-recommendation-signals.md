<!-- Shared Phase E — vendored into every converter skill. -->

# App recommendation signals

Phase E recommends a **primary archetype plus optional modules**. It is not a
keyword classifier.

## Evidence hierarchy

Strongest to weakest:

1. dimension members from exported rows;
2. field/formula structure;
3. stable-key readiness;
4. source-tool actions/parameters/reference marks (when present in workdir);
5. semantic vocabulary.

Vocabulary alone never qualifies an operational app.

## Archetypes

| Archetype | Structural evidence |
|---|---|
| Scenario planning | Actual + Forecast/Plan members, time grain, driver/assumption fields |
| Allocation/capacity | Budget/Target, Actual/Baseline, allocatable dimension, capacity/cost measure |
| Approval workflow | stable entity key, multiple decision states, pending, aging/policy/tier |
| Exception command center | stable entity key, risk/exception member, threshold/coverage/reorder signal |

The detector returns scores, confidence, evidence items, prerequisites, and
modules. Multiple archetypes may qualify. The highest score is primary;
others contribute optional modules.

Example:

```json
{
  "primary": "scenario-planning",
  "qualified": ["scenario-planning", "approval-workflow"],
  "modules": [
    "scenario-library",
    "writeback-grid",
    "scenario-comparison",
    "impact-bridge",
    "status-lifecycle",
    "audit-log",
    "workbook-agent"
  ]
}
```

## False-positive guards

- One field/member containing “Forecast” does not prove a planning model.
- Active/Inactive status does not prove an approval workflow.
- A variance measure alone does not prove exception triage.
- “Budget” in prose does not prove allocation; it needs a baseline and an
  allocatable dimension.
- No writeback recommendation is build-ready without a stable key and a
  write-enabled connection.

## Readiness

Every app option reports:

- stable key/composite-key candidates;
- missing write connection;
- manual published-data-entry permission;
- relevant build recipe;
- verification gates.

Parameter-driven calculations must stay in the workbook document with their
workbook controls. A workbook cannot drive a control owned by a separate data
model document merely by reusing the same `controlId`.

## Interview

Ask one primary choice from scored options, quoting evidence. Then ask only:

1. what users edit (`drivers`, `line-values`, `both`, `none`);
2. whether approvals are required;
3. whether multiple scenarios coexist;
4. agent authority (`analyze`, `recommend`, `write-after-approval`, `none`);
5. unit of work (defaults from the archetype grain — make it explicit);
6. write mode (`append` default; `overwrite` only when destructive updates are intentional).

**STOP:** confirm the resulting `app-plan.json` with the human before any
writeback authoring.

**Rails before agents.** Refuse `write-after-approval` without L1 readiness
(stable key + write-enabled connection). Soft-warn on `recommend` without L1.

Record answers in `app-plan.json` before authoring the enhanced clone.

If the human wants a greenfield process design (not a migration uplift), hand
off to the separate **sigma-app-design** / BUILD Design Pack skill.
