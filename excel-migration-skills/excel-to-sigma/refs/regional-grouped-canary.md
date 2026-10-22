# Regional01 B4 grouped native canary — offline operator packet

This packet covers **Summary!B4 only**, plus the shared 144-row
`tblSalesForecast[Revenue]` formula template. B4 is a Region/Q1 `SUMIFS`, with
the region read from editable `Summary!A4`; `Summary!B3` is the literal text
`Q1` and is not a formula input. B4's dates are formula constants
`DATE(2026,1,1)` and `EDATE(...,3)`. The source formula, AST, source hash, and
Excel result `1,544,984.02` are verified against the original workbook and the
independent Excel oracle. This packet is **offline candidate evidence** only.

Run `scripts/regional-grouped-canary.py` with the exact original workbook,
reviewed v2 input plan, native v2 plan, and independent Excel oracle JSONL.
It emits `candidate.json`, including all 144 Revenue source-cell mappings,
the distinct B4 five-lane mapping, complete B4 dependency list, the actual
source formula SHA, 3 logical elements, 30 formula columns, and unresolved
qualifications. The hard canary cap is 8 tables / 128 formula columns. The
source AST uses `table:tblSalesForecast:#data` with rows 2:145, so **appended
sales rows remain in scope**. The candidate cannot be interpreted as a closed
144-row SUMIFS range.

The logical construction is:

1. An ordinary editable sales input with 144 literal rows and five authored
   fields (`Region`, `Product Line`, `Month`, `Units`, `Avg Price`). Before
   staging the canary, add two metadata fields to each input row: immutable
   `Source Key = Forecast Input!row:N` and `Source Ordinal = N-1`. These are
   migration-owned **editable** metadata, not extra Excel literals or fake
   Sigma IDs; the SDK does not establish a column lock here. Reconcile
   all 144 physical row IDs after seed. A second ordinary input holds the four
   `Summary!A4:A7` Region labels, with exact source-cell lineage and physical
   row-ID reconciliation. New appended rows need a reviewed
   monotonic ordinal before error-order parity can be accepted.
2. A calculated table sourced from that input. The existing typed native
   compiler emits one shared Revenue row template with five public lanes
   (number, text, logical, kind, error), plus live Region/Year/Quarter/group
   keys, source key, and source ordinal. All 144 original `F2:F145` ASTs are checked
   row-relative against that template; matching formula text alone is not the
   proof. Group key uses `Lower(Region)`, `DatePart("year", Month)`, and
   `DatePart("quarter", Month)`.
3. A single grouping by that composite key. It computes `Sum(Revenue Number)`
   and `Min(First Error Ordinal)`; `Grouping.to_source()` provides a flat source.
   The B4 summary table is sourced from the four source-bound region labels and
   looks up key `Lower(A4)|2026|1`, coalescing a missing numeric group to zero.
   Its error lane follows the lowest applicable ordinal to the originating
   row's Revenue Error. No source result is copied as a Sigma formula.

## Minimal staging sequence and exact contracts

1. Generate and review `canary-inputs.json` with
   `scripts/regional-canary-inputs.py`. Its source-hash-bound projection has
   status `CANARY_QUALIFICATION_ONLY`: two input tables, 144 sales rows,
   four Summary region rows, and exact source-cell mappings. It records the
   other three source inputs as omitted and all 214 source formulas as pending.
   This isolated fixture cannot satisfy the full five-input staging gate or
   authorize production promotion. Take a fresh full document GET and layout
   backup. For each fixture input call `prepare_input_create_program`, execute
   its SDK code, GET assigned element/column IDs, bind the actual row-ID system
   column, and query the empty input. Call `prepare_input_seed_program`, seed,
   then query all physical rows and run `reconcile_input_rows`. It checks every
   authored value and metadata value against its original source cell, and
   records each assigned physical row ID. Query the actual row-ID column alias
   after each REST build; a virtual alias may normalize to `ID`. Actual Sigma
   source serialization may expose the physical system column only as
   `{"id":"ID"}` without a name or type. Keep that physical ID separate from
   the observed query column ID (`rowIdQueryColumnId`, such as the ID alias in
   describe-element DDL); the query row label is `ID`. Both IDs and the query
   alias must be reconciled, and a foreign name/ID fails closed.
   The complete candidate and complete fixture are pinned to independently
   reviewed digests in code; recomputing a packet's own hash cannot authorize
   changed formulas, source mappings, claims, or input rows.
2. Call `prepare_scaffold_program(candidate, element_kind="calculated-table",
   page_id=<observed>, source_element_id=<observed sales input>, grid_row=<free>,
   current=<fresh document>, source_path=..., base_input_plan=...,
   canary_input_plan=..., observed_inputs=<fresh two-input receipts>)`.
   It emits one documented `get_page` / `add_table(source.element(...))` /
   `add_column(..., const_num(0))` SDK program. Execute only in a disposable
   staging document. Read back its actual element ID and every column ID, and
   check the full document/layout for foreign changes. After every native
   structural edit, query both ordinary inputs again and call
   `confirm_phase_input_stability` with pre/post documents and receipts. It
   rejects any change to their 148 original authored/metadata values, row IDs,
   input element/column IDs, or reused query snapshots. Repeat this check
   after grouping, each scaffold, and each REST formula patch. During deliberate
   value-edit tests, inspect the edited field and metadata/row IDs; restore the
   authored field before using this original-source reconciliation again.
3. Build an assigned receipt with `sourceSha256`, `canaryInputPlanHash`,
   `documentId`, `documentVersion`, scaffold element/column IDs, and namespace
   element IDs, names, and column IDs/names taken from fresh full-document
   readback. Include both reconciled input bindings and queries. Run
   `prepare_contents_patch(candidate, fresh_document, receipt,
   element_kind="calculated-table", source_path=..., base_input_plan=...,
   canary_input_plan=..., observed_inputs=...)`. Its `contents` is a
   full-document PUT body; use `ifMatchDocumentVersion`, then GET and
   `confirm_contents_patch`. The preparer checks complete input rowsets,
   namespace/source-column lineage, scaffold source, placeholders, and
   formula references. The confirmer checks exact saved full contents.
4. Call `prepare_grouping_program` with the confirmed row-patch readback,
   observed row element/page IDs, free grid row, and fresh two-input receipts.
   The emitted SDK program
   calls `set_groupings([[group_key_column]])`,
   `grouping.set_calculation("Revenue Sum", sigma.formula.sum(revenue_number))`,
   `grouping.set_calculation("First Error Ordinal", sigma.formula.min(error_ordinal))`,
   then `grouping.to_source()` and adds one flat grouped table. Both `sum` and
   `min` constructors are present in the cached SDK `formula.py`. GET the saved
   grouping, actual grouped element/column IDs, and query grouped rows.
   Verify year/quarter date semantics, `Sum`, `Min`, and source edit propagation.
5. Use `prepare_scaffold_program(..., element_kind="summary-table",
   source_element_id=<observed summary-regions input>, ...)`, read back IDs,
   then patch from a fresh document with namespaces for `Summary Regions`,
   `Grouped`, and `Rows`. The `Grouped` namespace must resolve `Group Key`,
   `Revenue Sum`, and `First Error Ordinal`; `Rows` resolves `Revenue Error`
   and `Source Ordinal`. Patch every formula with an exact version guard and
   confirm saved full contents. Bind B4 to the first summary-regions source
   row through its reconciled physical row ID; other summary rows are outside
   this formula-cell canary. Run `observe_b4_query` on a fresh output query;
   it requires fresh post-patch two-input receipts and checks that output Source
   Key and Source Row ID resolve `Summary!A4`
   exactly, then returns five lanes as `B4_QUERY_OBSERVED_UNVERIFIED`.
6. Query B4 number/text/logical/kind/error baseline and compare with Excel.
   Edit one ordinary sales `Units`, `Avg Price`, `Month`, and `Region`; query
   after each edit and reopen. Check zero, blank, no-match A4, duplicate group
   membership, and a test-only error path if a typed error can be injected
   without altering source meaning. Restore every input and confirm B4 again.
   Keep before/after document, row, grouping, and query receipts. The offline
   graph interpreter has already checked baseline, edits, zero, null,
   no-match, and synthetic first-error ordering, but cannot stand in for this
   live sequence.

The exact source labels and calendar constants are preserved. B4's full
Excel `SUMIFS` semantics still require proof for case-insensitive and wildcard
criteria, blank/error criteria, duplicate rows, date/time zone boundaries,
and newly appended error rows. If any fails, leave this formula blocked and
retain its source mapping. The other 51 Regional `SUMIFS`, four source
`VLOOKUP` `#NAME?` errors, charts, and full-workbook promotion are outside
this canary.

Cached SDK references: `work/native-grouped-docs-20261020/grouping.md`,
`levelTable.md`, `source.md`, `tables-skill.md`, and `formula.py`. The saved
grouped-source representation and formula runtime still require live
qualification; the binder fails closed if row lineage is absent. Sigma formula references:
[DatePart](https://help.sigmacomputing.com/docs/datepart),
[Concat](https://help.sigmacomputing.com/docs/concat),
[Min](https://help.sigmacomputing.com/docs/min).
