"""Fail-closed checks for native GridFramed page-body programs (1-based)."""
from __future__ import annotations
import ast
import re
import xml.etree.ElementTree as ET

def _require(ok, message):
    if not ok:
        raise ValueError('BLOCKED native grid frame: ' + message)

def validate_grid_frame(x, y, width, height, *, grid_width=24):
    """Validate SDK inclusive grid coordinates, not pixel/report coordinates."""
    frame = [x, y, width, height]
    _require(type(grid_width) is int and grid_width > 0 and
             all(type(value) is int and value > 0 for value in frame),
             'positive integer coordinates/spans/grid width required')
    _require(x + width - 1 <= grid_width, 'frame extends beyond the actual grid width')
    return frame

def _overlaps(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and
            a[1] < b[1] + b[3] and b[1] < a[1] + a[3])

def _page_frames(current, page_id, ignore_element_ids):
    text = current.get('contents', {}).get('layout')
    _require(isinstance(text, str) and text.strip(), 'fresh full page layout required')
    text = re.sub(r'^<\?xml[^>]*\?>\s*', '', text.strip(), count=1)
    try:
        root = ET.fromstring('<Root>' + text + '</Root>')
    except ET.ParseError as exc:
        raise ValueError('BLOCKED native grid frame: malformed layout XML') from exc
    pages = [node for node in root if node.tag == 'Page' and node.get('id') == page_id]
    _require(len(pages) == 1 and pages[0].get('type') == 'grid', 'exact grid page required')
    match = re.fullmatch(r'repeat\(\s*([1-9][0-9]*)\s*,\s*1fr\s*\)',
                         pages[0].get('gridTemplateColumns', ''))
    _require(match is not None, 'actual page grid width is not explicit')
    grid_width = int(match[1])
    frames = []
    ids = set()
    for node in pages[0]:
        element_id = node.get('elementId')
        _require(node.tag == 'Element' and element_id and element_id not in ids and len(node) == 0,
                 'direct page layout must have unique leaf element placements')
        ids.add(element_id)
        spans = [re.fullmatch(r'([1-9][0-9]*)\s*/\s*([1-9][0-9]*)', node.get(key, ''))
                 for key in ('gridColumn', 'gridRow')]
        _require(all(spans), 'actual element grid ranges required')
        x, end_x = map(int, spans[0].groups())
        y, end_y = map(int, spans[1].groups())
        frame = validate_grid_frame(x, y, end_x - x, end_y - y, grid_width=grid_width)
        if element_id not in ignore_element_ids:
            frames.append(frame)
    _require(set(ignore_element_ids) <= ids, 'ignored update target is absent from actual page')
    return grid_width, frames

def validate_native_grid_program(program, *, grid_width=24, current=None, page_id=None,
                                 ignore_element_ids=()):
    """Check all literal set_frame calls, including those under literal False.

    Supply current/page_id for overlap checks on a fresh saved grid page.
    Updates may explicitly ignore their own separately verified element IDs.
    Native table-construction generators use the default of ignoring nothing.
    """
    try:
        parsed = ast.parse(program)
    except (SyntaxError, TypeError) as exc:
        raise ValueError('BLOCKED native grid frame: invalid program') from exc
    if current is not None:
        _require(isinstance(page_id, str) and page_id, 'actual page ID required')
        grid_width, occupied = _page_frames(current, page_id, ignore_element_ids)
    else:
        _require(page_id is None and not ignore_element_ids, 'source layout needed for page/update targets')
        occupied = []
    frames = []
    for call in ast.walk(parsed):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and
                call.func.attr == 'set_frame'):
            continue
        _require(len(call.args) == 4 and not call.keywords, 'four literal grid frame arguments required')
        try:
            values = [ast.literal_eval(arg) for arg in call.args]
        except (ValueError, TypeError) as exc:
            raise ValueError('BLOCKED native grid frame: literal frame values required') from exc
        frame = validate_grid_frame(*values, grid_width=grid_width)
        _require(not any(_overlaps(frame, other) for other in occupied + frames),
                 'proposed frame overlaps an existing or proposed element')
        frames.append(frame)
    return frames
