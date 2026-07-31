"""Sigma Computing ID generation and naming utilities.

Python port of the shared sigma-ids.ts module (metabase-to-sigma /
converter/sigma-ids.ts) — ported byte-for-byte on the display-name derivation
rule, since that rule must match Sigma's OWN internal derivation exactly or
cross-element formula refs compile to type "error" at POST time
(beads-sigma-c31q). No Hex-specific logic lives here; every sibling skill
that ports this converter for a new source tool should carry this file over
unchanged.
"""

from __future__ import annotations

import random
import re
import string

_SIGMA_CHARS = string.ascii_letters + string.digits

# Small words that Sigma keeps lowercase in display names (unless first/last word).
_SIGMA_LOWERCASE_WORDS = {
    "a", "an", "the", "and", "but", "or", "for", "nor", "so", "yet",
    "at", "by", "in", "of", "on", "to", "up", "as", "into", "via", "per",
}

_used_ids: set[str] = set()


def reset_ids() -> None:
    """Reset the ID registry — call at the start of each conversion run."""
    _used_ids.clear()


def sigma_short_id(length: int = 10) -> str:
    """Generate a unique short random id (base62)."""
    while True:
        candidate = "".join(random.choice(_SIGMA_CHARS) for _ in range(length))
        if candidate not in _used_ids:
            _used_ids.add(candidate)
            return candidate


def sigma_inode_id(identifier: str) -> str:
    """Column ids use Sigma's inode format: inode-{22-char base62}/{IDENTIFIER}."""
    return f"inode-{sigma_short_id(22)}/{identifier.upper()}"


_CAMEL_LOWER_UPPER = re.compile(r"([a-z])([A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
_LETTER_TO_DIGIT = re.compile(r"([A-Za-z])([0-9])")
_DIGIT_TO_LETTER = re.compile(r"([0-9])([A-Za-z])")
_SPLIT_WORDS = re.compile(r"[_\s]+")


def sigma_display_name(s: str | None) -> str:
    """SNAKE_CASE or camelCase -> "Title Case" display name.

    Matches Sigma's OWN derivation rule for warehouse column names (verified
    empirically against live DM readbacks): Sigma splits words at
    underscores, camelCase boundaries, AND every letter<->digit boundary in
    BOTH directions. E.g. CY_Q1_REVENUE -> "Cy Q 1 Revenue" (NOT "Cy Q1
    Revenue"), FY2024 -> "Fy 2024". Raw-column formula refs
    ([TABLE/Display Name]) must reproduce this exactly or the POST fails
    with "dependency not found".

    AP-style casing: FIRST and LAST words always capitalize; stopwords stay
    lowercase only mid-name. Cross-element refs are case-SENSITIVE, so this
    function must be idempotent (running it twice on its own output is a
    no-op) — formulas pass through translation more than once.
    """
    s = s or ""
    normalized = _CAMEL_LOWER_UPPER.sub(r"\1_\2", s)
    normalized = _ACRONYM_BOUNDARY.sub(r"\1_\2", normalized)
    normalized = _LETTER_TO_DIGIT.sub(r"\1_\2", normalized)
    normalized = _DIGIT_TO_LETTER.sub(r"\1_\2", normalized)
    words = [w for w in _SPLIT_WORDS.split(normalized.lower()) if w]
    out = []
    for i, w in enumerate(words):
        if i == 0 or i == len(words) - 1 or w not in _SIGMA_LOWERCASE_WORDS:
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


def sigma_col_formula(table_name: str, identifier: str) -> str:
    """Column formula: [TABLE_NAME/Display Name]."""
    return f"[{table_name}/{sigma_display_name(identifier)}]"


_AGG_FORMULAS = {
    "sum": "Sum([{dn}])",
    "avg": "Avg([{dn}])",
    "average": "Avg([{dn}])",
    "min": "Min([{dn}])",
    "max": "Max([{dn}])",
    "count": "CountIf(IsNotNull([{dn}]))",
    "count_distinct": "CountDistinct([{dn}])",
    "countdistinct": "CountDistinct([{dn}])",
    "median": "Median([{dn}])",
    "percentile": "Percentile([{dn}], 0.5)",
    "stddev": "StdDev([{dn}])",
    "variance": "Variance([{dn}])",
}


def sigma_agg_formula(agg: str | None, identifier: str) -> str:
    """Metric formula: aggregation referencing a column by display name (no
    table prefix — metrics live on the same element as their source column)."""
    dn = sigma_display_name(identifier)
    template = _AGG_FORMULAS.get((agg or "").lower(), "Sum([{dn}])")
    return template.format(dn=dn)


def infer_sigma_format(agg: str | None, hex_display_format: dict | None) -> dict | None:
    """Build a Sigma format object from Hex's own displayFormat, when present
    (METRIC cells and EXPLORE fields both carry one) — the PRIMARY format
    signal, mirroring the family convention of preferring the source's own
    format mask over name/formula heuristics (beads-sigma-4q7k)."""
    if not hex_display_format:
        return None
    fmt = hex_display_format.get("format")
    decimals = hex_display_format.get("numDecimalDigits")
    decimals = 2 if decimals is None or decimals < 0 else decimals
    if fmt == "CURRENCY":
        symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(
            hex_display_format.get("currency", "USD"), "$"
        )
        return {"kind": "number", "formatString": f"{symbol},.{decimals}f", "currencySymbol": symbol}
    if fmt == "PERCENT" or fmt == "PERCENTAGE":
        return {"kind": "number", "formatString": f",.{decimals}%"}
    if fmt == "NUMBER":
        return {"kind": "number", "formatString": f",.{decimals}f"}
    return None
