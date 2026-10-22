"""Current workbook wire helper for excel-to-sigma builders.

Builders still author the convenient nested `pages[].elements` draft shape.
Before ``POST /v2/workbooks`` (and when writing POST-ready artifacts), call
``wire_workbook(spec)`` so the body matches the current code representation:

  { name, folderId, contents: { schemaVersion, kind, pages, elements, layout } }

``code_rep.wrap_contents`` flattens nested elements and canonicalizes layout tags. This
helper invents a stacked notebook-flow `layout` when the draft lacks one —
layout is required on the live surface and owns page membership.
Data-model specs are unchanged — do not wrap /v2/dataModels/... payloads.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import code_rep  # noqa: E402

GRID_COLS = 24
DEFAULT_ROW_HEIGHT = 12
DEFAULT_PIVOT_ROW_HEIGHT = 50
CREATE_METADATA_KEYS = ("name", "folderId", "description", "ownerId")


def stack_layout(
    pages,
    row_height: int = DEFAULT_ROW_HEIGHT,
    pivot_row_height: int = DEFAULT_PIVOT_ROW_HEIGHT,
) -> str:
    """One full-width stacked tile per element, page order preserved."""
    blocks = []
    for page in pages or []:
        if not isinstance(page, dict) or not page.get("id"):
            continue
        pid = page["id"]
        els = [el for el in (page.get("elements") or []) if isinstance(el, dict) and el.get("id")]
        lines = [
            f'<Page type="grid" gridTemplateColumns="repeat({GRID_COLS}, 1fr)" '
            f'gridTemplateRows="auto" id="{pid}">'
        ]
        cursor = 1
        for el in els:
            height = pivot_row_height if el.get("kind") == "pivot-table" else row_height
            end = cursor + height
            lines.append(
                f'  <Element elementId="{el["id"]}" '
                f'gridColumn="1 / {GRID_COLS + 1}" gridRow="{cursor} / {end}"/>'
            )
            cursor = end
        lines.append("</Page>")
        blocks.append("\n".join(lines))
    return '<?xml version="1.0" encoding="utf-8"?>\n' + "\n".join(blocks)


def wire_workbook(spec: dict, *, dry_run: bool = False) -> dict:
    """Return a ``POST /v2/workbooks`` request with flat ``contents``."""
    if not isinstance(spec, dict):
        raise TypeError("workbook spec must be a dict")

    # Already wrapped — re-canonicalize through code_rep for safety.
    if isinstance(spec.get("contents"), dict) or isinstance(spec.get("document"), dict):
        doc = code_rep.document(spec)
        meta = {key: spec[key] for key in CREATE_METADATA_KEYS if key in spec}
    else:
        draft = dict(spec)
        draft.setdefault("schemaVersion", 1)
        draft.setdefault("kind", "workbook")
        pages = draft.get("pages")
        if "layout" not in draft and isinstance(pages, list):
            draft["layout"] = stack_layout(pages)
        meta = {key: draft[key] for key in CREATE_METADATA_KEYS if key in draft}
        doc = code_rep.document(draft)

    body = code_rep.wrap_contents(doc, extra=meta)
    if dry_run:
        body["dryRun"] = True
    return body


def dry_run_request(body: dict) -> dict:
    """Return a non-mutating validation request for an already-wired body."""
    if not isinstance(body, dict) or not isinstance(body.get("contents"), dict):
        raise TypeError("expected a wired workbook body with contents")
    return {**body, "dryRun": True}


def assert_dry_run_success(response: dict) -> list:
    """Validate the successful-200 dry-run response contract.

    Sigma does not return ``valid: true`` on success. A failed validation is an
    HTTP 400 with ``valid: false`` and errors, normally raised by the caller's
    HTTP helper before this function runs.
    """
    if not isinstance(response, dict) or response.get("dryRun") is not True:
        raise ValueError("Sigma workbook validation did not return dryRun=true")
    errors = response.get("errors") or []
    if response.get("valid") is False or errors:
        summaries = [
            item.get("summary", str(item)) if isinstance(item, dict) else str(item)
            for item in errors
        ]
        raise ValueError("Sigma workbook validation failed: " + "; ".join(summaries))
    return response.get("warnings") or []
