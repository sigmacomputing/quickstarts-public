# Source workbook inventory model

`scripts/source-workbook.py` creates a deterministic JSON inventory of an unchanged `.xlsx` or `.xlsm` source:

```bash
python3 scripts/source-workbook.py SOURCE.xlsx --out source-model.json
python3 scripts/source-workbook.py SOURCE.xlsx --out source-model.json --block-decisions reviewed-blocks.json
```

The CLI validates before replacing its output file. Python callers can use `build_source_model(source_path, *, block_decisions=None)` and `validate_source_model(model, source_path=None)` from `scripts/lib/source_workbook.py`.

The model records the source basename and SHA256, worksheet and chart-only sheet facts (`kind`, visibility, applicable protection and presentation counts), every populated cell with its original data type and number format, every available formula source expression, formal table boundaries and column provenance, defined names, and optional reviewed roles. Typed dates and datetimes use JSON type tags. Formula-looking strings with Excel string data type remain literals; an explicit inline empty string remains `""` rather than an absent cell. Array-formula source text is retained. Formula objects without scalar source text remain formula records with an explicit unresolved reason. Hashing and parsing use the same source-byte snapshot. The workbook is read without saving it; VBA is never run.

Cell and table IDs encode their sheet/name components as JSON arrays, so punctuation in a sheet name cannot collide with another identity. Formula dependencies point to source cell IDs. `targetKind: "blank"` identifies a referenced empty cell that need not appear among populated cells. Bounded ranges expand to each interior cell. Cycles remain as directed source edges.

The validator requires source type/format fields on cells and complete table header, body, totals, and per-column provenance fields. Chart-only sheets contribute to the chart total; their protection flag is true when the source protects chart content or objects. Source chart-sheet visibility comes from the OOXML workbook manifest, which retains hidden state when openpyxl does not.

The shared `excel_expression` parser supplies reference analysis. A formula with unsupported syntax, an unresolved name, a missing sheet, or an oversized range has `dependencyStatus: "unresolved"` and a reason in `unresolved`; its empty or partial `dependencies` list is **not** a verified no-dependency result. Defined names distinguish resolved single-cell references from unresolved constants, ranges, and unsupported expressions. Formula cached results are not entered data or live calculation evidence.

The CLI refuses an output path that is the source workbook, including symlink and hard-link aliases, before writing its temporary output.

Tables become unreviewed candidate blocks. Each body column lists literal, formula, and blank cell addresses; totals rows have a separate range and are excluded from body provenance. Every column starts with `intent: "ambiguous"`. Formula proportions do not decide whether users can edit it. To add reviewed role metadata, provide:

```json
{
  "sourceSha256": "<SHA256 of the exact source workbook>",
  "blocks": [{"sheet": "Inputs", "range": "A1:C10", "role": "input"}]
}
```

Roles are `input`, `calculation`, `reference`, and `scratch`. Reviewed ranges must be bounded, on an existing sheet, and nonoverlapping. They change only block metadata; no cell, formula, or dependency is excluded, including on hidden or scratch sheets.

This JSON is an inventory prerequisite for later source-specific construction. It does not approve a migration, translate unsupported formulas, prove parity, or bypass the audit, macro, and production-write gates in `refs/coverage-contract.md`.
