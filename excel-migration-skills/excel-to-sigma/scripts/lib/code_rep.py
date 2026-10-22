"""Shape adapter for Sigma's workbook code representation.

Current API (OpenAPI re-audited 2026-10):

* create / validate: ``POST /v2/workbooks`` with ``contents`` and optional
  ``dryRun: true``
* read: ``GET /v2/workbooks/{id}?includeContents=true``
* update: ``PUT /v2/workbooks/{id}/contents``

The deprecated ``/spec`` endpoints use the same inner shape under ``document``.
Readers stay tolerant of ``contents``, ``document``, and old flat artifacts.
This adapter is workbook-only. Data-model code representation is unchanged.
"""

# Workbook elements are flat document collections; `overlays` and `panels` live
# beside them. `settings` (theme/navigation) and `agents` belong inside
# `document` too. Omitting any of these sweeps it onto the metadata envelope,
# where it is invalid and silently dropped on write.
DOC_KEYS = (
    "schemaVersion", "pages", "elements", "overlays", "panels",
    "kind", "layout", "settings", "agents", "automatedActions",
)

# REMOVED from the API. The workbook theme is now settings.theme.name /
# settings.theme.overrides (published OpenAPI: createWorkbookSpec has zero
# occurrences of themeName/themeOverrides). The individual override keys are
# unchanged - only the container path moved. document() folds the legacy pair
# forward so specs and fixtures written before the move still produce a valid body.
LEGACY_THEME_KEYS = ("themeName", "themeOverrides")


def _fold_legacy_theme(doc, source):
    """themeName/themeOverrides -> settings.theme.{name,overrides}."""
    name = doc.get("themeName") or source.get("themeName")
    overrides = doc.get("themeOverrides") or source.get("themeOverrides")
    has_ov = isinstance(overrides, dict) and bool(overrides)
    if not name and not has_ov and not (set(LEGACY_THEME_KEYS) & set(doc)):
        return doc

    out = {k: v for k, v in doc.items() if k not in LEGACY_THEME_KEYS}
    settings = dict(out.get("settings") or {})
    theme = dict(settings.get("theme") or {})
    if name and not theme.get("name"):
        theme["name"] = name
    if has_ov:
        theme["overrides"] = {**(theme.get("overrides") or {}), **overrides}
    if not theme:
        return out
    settings["theme"] = theme
    out["settings"] = settings
    return out


def set_theme(doc, name=None, overrides=None):
    """Emitter helper - set the workbook theme in the CURRENT shape.

    Builders should call this instead of assigning the removed
    themeName/themeOverrides pair. Mutates and returns doc.
    """
    has_ov = isinstance(overrides, dict) and bool(overrides)
    if not name and not has_ov:
        return doc
    settings = doc.setdefault("settings", {})
    theme = settings.setdefault("theme", {})
    if name:
        theme["name"] = name
    if has_ov:
        theme["overrides"] = {**(theme.get("overrides") or {}), **overrides}
    return doc


def theme(spec):
    """Read the theme from either shape. Returns {"name":..., "overrides":{...}}."""
    t = (document(spec).get("settings") or {}).get("theme") or {}
    return {"name": t.get("name"), "overrides": t.get("overrides") or {}}


def document(response):
    """Return workbook contents from current, deprecated, or flat shapes."""
    if not isinstance(response, dict):
        return {}
    inner = response.get("contents")
    if not isinstance(inner, dict):
        inner = response.get("document")
    doc = inner if isinstance(inner, dict) else {
        k: v for k, v in response.items() if k in DOC_KEYS
    }
    return _fold_legacy_theme(doc, response)


def metadata(response):
    if not isinstance(response, dict):
        return {}
    return {
        k: v for k, v in response.items()
        if k not in ("contents", "document")
        and k not in DOC_KEYS
        and k not in LEGACY_THEME_KEYS
    }


def workbook_elements(spec):
    """Return flat elements, with read-only compatibility for old artifacts."""
    doc = document(spec)
    elements = doc.get("elements")
    if isinstance(elements, list):
        return [element for element in elements if isinstance(element, dict)]
    return [
        element
        for page in doc.get("pages", [])
        if isinstance(page, dict)
        for element in page.get("elements", [])
        if isinstance(element, dict)
    ]


def workbook_page_element_ids(spec):
    """Return {page_id: [element_id, ...]} derived from layout order."""
    import re

    result = {}
    layout = str(document(spec).get("layout") or "")
    for match in re.finditer(r'<Page\b[^>]*\bid="([^"]*)"[^>]*>(.*?)</Page>', layout, re.S):
        result[match.group(1)] = list(dict.fromkeys(
            re.findall(
                r'<(?:Element|Container|TabbedContainer|LayoutElement|GridContainer)\b'
                r'[^>]*\belementId="([^"]*)"',
                match.group(2),
            )
        ))
    return result


def workbook_page_by_element(spec):
    """Return {element_id: page_metadata}; layout is authoritative."""
    doc = document(spec)
    pages = [page for page in doc.get("pages", []) if isinstance(page, dict)]
    pages_by_id = {page["id"]: page for page in pages if page.get("id")}
    result = {}
    for page_id, element_ids in workbook_page_element_ids(doc).items():
        page = pages_by_id.get(page_id, {"id": page_id, "name": page_id})
        for element_id in element_ids:
            result.setdefault(element_id, page)
    return result


def workbook_elements_with_pages(spec):
    page_by_element = workbook_page_by_element(spec)
    return [
        (element, page_by_element.get(element.get("id") or element.get("elementId")))
        for element in workbook_elements(spec)
    ]


def _flatten_elements(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("pages"), list):
        return doc

    nested = []
    pages = []
    for page in doc["pages"]:
        page_copy = dict(page)
        nested.extend(page_copy.pop("elements", []) or [])
        pages.append(page_copy)

    elements = []
    seen = set()
    for element in list(doc.get("elements") or []) + nested:
        element_id = element.get("id") if isinstance(element, dict) else None
        if element_id and element_id in seen:
            continue
        if element_id:
            seen.add(element_id)
        elements.append(element)
    return {**doc, "pages": pages, "elements": elements}


def canonicalize_layout(layout_xml):
    """Map legacy layout aliases to the live-verified canonical tag names."""
    import re

    layout = str(layout_xml or "")
    layout = re.sub(r'<(/?)LayoutElement\b', r'<\1Element', layout)
    return re.sub(r'<(/?)GridContainer\b', r'<\1Container', layout)


def _canonical_document(doc):
    """Flatten nested elements and canonicalize layout tags."""
    flattened = _flatten_elements(doc)
    if isinstance(flattened, dict) and "layout" in flattened:
        flattened = {**flattened, "layout": canonicalize_layout(flattened["layout"])}
    return flattened


def wrap_contents(doc, extra=None):
    """Build a current request body with a ``contents`` envelope."""
    out = dict(extra or {})
    out["contents"] = _canonical_document(doc)
    return out


def wrap(doc, extra=None):
    """Build a deprecated ``document`` envelope for legacy artifact readers."""
    out = dict(extra or {})
    out["document"] = _canonical_document(doc)
    return out
