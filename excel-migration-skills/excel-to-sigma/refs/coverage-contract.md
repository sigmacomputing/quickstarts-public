# Complex-workbook coverage contract

“Any Excel file” is not a technically honest promise. Excel can contain an
arbitrary cell program, VBA, Power Query, external applications, COM/ActiveX,
embedded binaries, and credentials. This skill instead promises:

1. inventory every material workbook feature before build;
2. migrate supported behavior with data, formula, interaction, and render parity;
3. route representable-but-not-yet-automatic behavior to a named Sigma primitive;
4. block completion when no faithful route has been implemented;
5. never silently drop workbook behavior.

Run the hard gate first:

```bash
python scripts/audit-xlsx.py model.xlsx --out migration-audit.json
python scripts/macro-classify.py --json model.xlsm > macro-audit.json
python scripts/audit-openapi.py --out sigma-code-rep-audit.json
```

`audit-xlsx.py` exits `0` for `AUTO` and for `REVIEW_REQUIRED` (the issues are
reported, not fatal, so local work is never blocked by a review gate), and `2` for
`BLOCKED`. `--strict` exits `1` for `REVIEW_REQUIRED`; use it in a production gate.
(`--allow-review` is a hidden no-op alias kept for older CI.) A zero exit is not a
disposition: no customer migration is complete while a review issue lacks a verified
disposition.

`scripts/migrate.py plan <file> --out-dir <workdir>` runs this audit with discovery
and writes `review.template.json`, a source-bound skeleton for the file below.

The whole-workbook migration paths (`infer-canonical-formulas.py`,
`batch-convert.py`, `build-research-workbook.py`, and the source-bound forecast
and research plan builders) enforce the audit again. For production (`--post`, and
`batch-convert.py`), `REVIEW_REQUIRED` can proceed only with
`--review-dispositions <file.json>` containing:

```json
{
  "sourceSha256": "<SHA256 of the exact source workbook>",
  "issues": [
    {
      "code": "DATA_VALIDATION_PRESENT",
      "owner": "Named owner",
      "disposition": "Implemented list validation and tested valid/invalid input",
      "verified": true
    }
  ]
}
```

The record must cover every reported code with nonempty `owner` and
`disposition` and literal `verified: true`. A missing, stale, or tampered source
fails the gate. `BLOCKED` is never overrideable. Inferred plans also require
`sourcePath` (or CLI `--source`) and `sourceSha256`; the bytes must still match.
Research plans add `CACHED_FORMULA_FALLBACK` when any formula cell is frozen to
an Excel cached value, and `INFERENCE_REVIEW_REQUIRED` when inferred lines remain
unresolved; forecast plans from `draft-forecast-plan.py` add `FLAT_CARRY_POLICY` for
`=prior` forecast lines. These need explicit dispositions and must not be described as
full live-formula migration. Builds without `--post` run in draft mode and only report
these codes as pending (`DRAFT MODE: review pending for ...`).

## Coverage

| Excel surface | Route | Completion gate |
|---|---|---|
| Formal Tables / typed data | input table or data-model table | row/grain + aggregate parity |
| Common formulas | Sigma formulas / data-model calculations | cell or aggregate parity |
| Unsupported formulas / dynamic arrays | rewritten grain, SQL, or Python | explicit formula manifest + parity |
| Charts | matching Sigma chart kind | encoding/filter/aggregation + screenshot review |
| Pivots | Sigma pivot table | rows/columns/values/sorts/subtotals + query parity |
| Slicers/timelines | controls and target filters | interaction test |
| Data validation | input-column `values`, `valuesFrom`, `range`, or file constraints | invalid/valid input test |
| Conditional formatting | Sigma formatting rules | render review |
| Editable cells | input tables and actions | draft/published permission + writeback test |
| VBA writeback/API/navigation | element actions | runtime side-effect test |
| VBA stored procedure | `call-stored-procedure` action | signature/arguments/transaction review |
| VBA/Python integration | `code` + `code-output` + `run-python-element` | package/runtime/output parity |
| Scheduled/webhook automation | document `automatedActions` where supported | owner/failure/retry review |
| Power Query / connections | governed warehouse, DM, or API source | source and refresh parity |
| External workbook links | land as governed sources | source ownership + parity |
| Protection | Sigma sharing plus RLS/CLS policy where required | security review |
| `.xls` / `.xlsb`, add-ins, ActiveX, embedded binaries | convert/extract or external workflow | blocked until dispositioned |

## Hard completion gates

A migration is not complete until:

- all audit and inference issues have a source-bound owner, disposition, and verified result;
- all workbook creates pass `POST /v2/workbooks` with `dryRun: true`;
- server-assigned data-model ids are read back before workbook wiring;
- editable inputs work in the intended draft/published mode;
- formulas and aggregate outputs meet the agreed parity target;
- actions, Python, procedures, source refresh, and writeback are runtime-tested;
- chart/pivot/control behavior and layout are visually reviewed;
- security and unsupported/external behavior are explicitly signed off.
