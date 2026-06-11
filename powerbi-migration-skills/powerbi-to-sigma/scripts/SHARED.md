# Shared scripts (symlinked from tableau-to-sigma)

These are **symlinks** to `../../tableau-to-sigma/scripts/`, not copies — they are vendor-agnostic Sigma-side tooling reused verbatim by this skill. Editing one edits the shared source.

| Symlink | Reuse class | Notes |
|---|---|---|
| `get-token.sh`, `lib/` (`sigma_rest.rb`) | as-is | Sigma auth + 401-refresh |
| `post-and-readback.rb` | as-is | POST DM/workbook + `error`-column guard |
| `put-layout.rb` | as-is | Apply grid-XML layout |
| `find-or-pick-dm.rb` | as-is | DM reuse + `folderId`/`ownerId` harvest (our `tkd` workaround source) |
| `cleanup-orphan-workbooks.rb`, `assert-phase6-ran.rb` | as-is | Orphan prevention + Phase-6 hard gate |
| `validate-spec.rb` | as-is | Window-function / formula validation |
| `build-workbook-spec.rb`, `build-charts-from-signals.rb` | adapt | Chart-element shapes reused; input adapter is PBI-specific (visual bindings vs Tableau signals) |
| `verify-parity.rb` | as-is | Comparison engine; called by `phase6-parity-pbi.rb` |
| `phase6-parity.rb` | reference | Tableau two-pass parity flow; PBI uses `phase6-parity-pbi.rb` instead |

**Migration path:** when `sigma-conversion-core` (`beads-sigma-6k9`) is extracted, repoint these symlinks at the shared core package instead of `tableau-to-sigma`.

**Distribution:** these symlinks are DRY for repo work but break in a standalone download. Always ship via `../package.sh`, which dereferences them into real files (`dist/powerbi-to-sigma/` = 0 symlinks, self-contained).

PBI-native scripts (real files, not shared): `extract-pbir.py`, `convert-model.rb`, `build-workbook-from-pbir.rb`, `phase6-parity-pbi.rb`, `run.sh`, `fabric-extract.py`, `fabric-auth-check.py`.
