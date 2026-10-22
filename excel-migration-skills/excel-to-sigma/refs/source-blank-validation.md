# Source blank-validation contract, version 2

This contract supersedes the prior blanket `allowBlank=False → REJECTED_NO_WRITE`
source assumption. It retains every validation branch and the strict acceptance
gate. `scripts/lib/source_validation.py` pins the machine-readable policy version,
hash, primary documentation sections, and review date (2026-10-20).

Each extracted rule carries the exact base SpreadsheetML namespace and worksheet
part, all authored XML attributes, presence and raw values for `allowBlank`,
`showErrorMessage`, and `errorStyle`, formulas, source hash, and rule hash.
All 15 supplied fixture declarations omit these three attributes. The exact
base-namespace XSD edition and defaults were unavailable to the source review;
the Office 2010 extension namespace defaults are **not** substituted for them.

The declared blank class is one of `ALLOW_BLANK`,
`SATISFIES_NUMERIC_RULE_AS_ZERO`, `VIOLATES_NUMERIC_RULE_AS_ZERO`, or
`UNRESOLVED`. The numeric classes apply the authored operator to literal typed
bounds with zero as the comparison value. They do not turn a typed NULL attempt
into a numeric-zero attempt or determine what Excel saves. Lists, custom
formulas, and referenced bounds remain unresolved without a separate review.
The 25 existing blank attempts stay typed `{"type":"null","value":null}`.

The source application's edit-to-empty route, validation alert, and stored
NULL/empty/numeric representation are separate facts. Until an independent
source route review is bound, each blank branch has
`UNRESOLVED_SOURCE_ROUTE`; a native capture cannot choose its own expected
outcome or pass that branch. A qualified review must be supplied outside the
capture as `sourceBlankReviews[branchId]` on the target before matrix creation.
Its reviewed record binds the exact source hash, XML rule hash, policy hash,
branch ID, `edit-to-empty-commit` route, reviewer, date, decision ID,
source-evidence ID, rationale, qualified basis, expected `SAVED` or
`REJECTED_NO_WRITE` result, and record hash. Production recomputation checks
all bindings. A review decision establishes only that named route; Delete,
Clear Contents, and paste-blank need separately named evidence before their
outcomes can be asserted.

An unsupported custom/list rule or referenced numeric bound has a separate
`unresolvedDomains` entry for its nonblank constraint. A qualified blank-route
review leaves that entry intact. Native validation case admission and the
production matrix remain blocked until a separately reviewed implementation
and complete domain coverage resolve it.

Even with a reviewed outcome, the native branch requires browser execution,
source/plan/target/session receipts, physical row-ID inventory, before/after/
reopen/restoration readbacks, typed value, and full vector equality. It cannot
be passed by a classification or by a record of a source review alone. The
existing invalid and Cancel branches stay mandatory. Source enforcement,
native runtime parity, and the Research NULL arithmetic/chart defect remain
open until actual evidence resolves them.

The source review behind this policy was completed on 2026-10-20. Its primary
documents and sections are pinned in the policy, which travels with this skill.
