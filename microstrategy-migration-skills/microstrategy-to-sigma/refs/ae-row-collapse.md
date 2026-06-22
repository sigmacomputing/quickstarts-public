# Analytical-Engine row collapse — why `resolve_ae_winners.py` exists

## The behavior

When an attribute's **key (ID) form is non-unique in its lookup table**,
MicroStrategy's Analytical Engine does something no clean SQL GROUP BY
reproduces: it collapses the per-(parent, key) result to **one
arbitrary-but-stable representative row per key element** and cross-tabs that
row's label + metric values across the parent attribute.

Fixture example: `Month.key = MONTH_NUMBER` while `DATE_DIM` carries multiple
`MONTH_NAME` spellings and repeats month numbers across years. The grid shows
one `MONTH_NAME` spelling per month number — which one is a **hash artifact of
the engine**. It cannot be derived from the model bundle, only observed.

A report is **affected** when one of its attribute units has a DESC form
distinct from its grouping key (`convert.py` → `attribute_unit_cols`). Reports
without such attributes produce clean grids — no resolution needed.

## The resolution workflow (`scripts/resolve_ae_winners.py`)

1. **Re-execute** each affected report via
   `POST /api/v2/reports/{id}/instances?limit=N` — the MSTR grid is ground
   truth for which representative won.
2. Compute the **clean** per-(parents, key) aggregates from the warehouse —
   the same SQL MicroStrategy generated (`Bundle.build_clean_group_sql`) — via
   a temporary Sigma workbook with a `sql` element (deleted afterward).
3. **Match** each key's MSTR-reported label + metric values to the unique
   clean row. Ambiguity is a hard error, never a guess.
4. Emit `ae_winners.json`
   (`{report: {quirkKeyCol, quirkDescCol, parentKeyCols, winners[]}}`) for
   `convert.py --ae-winners`.

`convert.py` then emits a **SQL element** per affected report
(`Bundle.build_ae_sql`): a CTE of the clean groups self-joined so every
parent-key row takes the pinned winner row's label + metric values — exactly
reproducing the AE grid, deterministic and parity-verifiable.

## Related converter patterns (clean reports)

- **Grouping by key, labeling by DESC**: MSTR grids group by the attribute's
  KEY form and render the DESC form; when they differ, the converter emits the
  key as the grouping column and `Max([DESC])` as the rendered label.
- **Inner-join semantics**: MicroStrategy inner-joins lookup tables, so fact
  rows with no matching dim row never appear in its grid. The converted Sigma
  DM join is left-outer (other consumers need all fact rows) — so the
  converter adds a per-element `exclude [null]` list filter on each dim-keyed
  grouping column to mirror MSTR.
