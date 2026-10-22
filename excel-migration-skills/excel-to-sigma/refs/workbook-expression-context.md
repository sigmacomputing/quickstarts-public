# Source-bound workbook expressions

`scripts/lib/workbook_expression.py` binds the shared `excel_expression` AST to
one `.xlsx` or `.xlsm` source. It reads formula text with `data_only=False` and
never evaluates from cached formula values, saves the source, opens external
workbooks, or runs VBA. Its source SHA-256 identifies the exact bytes used.

```python
context = WorkbookContext.from_path(source_path, external_inputs={
    ("FY26 Corporate Allocations.xlsx", "Alloc", "C4"): 61000,
})
bound = context.bind_formula("=SUM(tblOrders[Amount])", sheet="Summary", address="B2")
value = context.evaluate_cell("Summary", "B2", overrides={("Inputs", "B3"): 5})
report = context.formula_report()
```

`external_inputs` uses exact `(workbook, sheet, address)` identities. Missing
bindings remain unresolved. `overrides` replaces typed source literals only;
formula cells cannot be replaced. `indirect_bindings` can supply a finite,
reviewed map for one `(sheet, formula_address)`:

```python
{("Cash", "A1"): {"Coll_Base": "Inputs!$B$4",
                   "Coll_Downside": "Inputs!$B$5"}}
```

For `INDIRECT("Coll_"&Scenario)`, the binder also recognizes the finite set of
source-defined names with that literal prefix. It retains the selector and every
alternative's source dependencies. Other dynamic locators require review.

`formula_report` accounts for every formula. `verified` means the local
source-derived evaluator returned a value; it does not establish independent
Excel or native Sigma parity. Each record has `verified`, `unresolved`, `error`,
or `cycle` status, a value or reason, cell dependencies,
and `dependencyStatus`. `incomplete` marks a binding failure or a dynamic range
whose full dependencies cannot be known. Whole-column references retain their
Excel declared domain and the bounded active source domain. `COUNTIFS` criteria
that could count omitted blank rows remain unresolved even when `INDEX` or
grouping wraps a whole-column reference. `COUNTIFS` using a bounded whole-column
domain conservatively reports incomplete dependencies. Empty table data bodies
contain no header cells.
Circular defined names are reported as formula cycles. A bound range over
100,000 cells remains unresolved to avoid an unsafe expansion. Workbook
1900/1904 date epochs and scoped names are preserved.

The old `parse_expression` mode and `emit_sigma` remain for the existing
converter. Workbook parsing is opt-in with `workbook_mode=True`. Native Sigma
emission of newly bound table/range/indirect constructs needs its own qualified
lowering; the old emitter raises `UnsupportedExpression` for them. Statistical
and dynamic array functions remain explicit unresolved work.
