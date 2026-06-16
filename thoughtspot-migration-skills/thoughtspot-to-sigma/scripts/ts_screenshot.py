#!/usr/bin/env python3
"""Per-visualization PNG export from ThoughtSpot — for visual parity against the
migrated Sigma workbook elements.

ThoughtSpot side (this script): POST /api/rest/2.0/report/liveboard with
file_format PNG + visualization_identifiers → PNG bytes (per viz).
Sigma side (counterpart): POST /v2/workbooks/{id}/export {elementId, format:{type:png,
pixelWidth,pixelHeight}} → poll GET /v2/query/{queryId}/download). Render both, compare side by side.

Blank-render guard: when the Liveboard's warehouse connection is down,
ThoughtSpot still returns HTTP 200 with a near-uniform placeholder PNG (or an
error body). Those are reported as ✗ failures (exit 1), never ✓.

Usage:
  python3 ts_screenshot.py <LIVEBOARD_ID> [outdir]      # all viz in the liveboard
  python3 ts_screenshot.py <LIVEBOARD_ID> --viz <guid>  # one viz
Env: TS_HOST, TS_TOKEN, TS_WORKDIR (default outdir = <TS_WORKDIR or ./ts-migration>/png).
"""
import os, sys, json, ssl, struct, urllib.request, urllib.error, re, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml, ts_lib
yaml.SafeLoader.add_constructor("tag:yaml.org,2002:value", lambda l, n: l.construct_scalar(n))
_SSL = ssl._create_unverified_context()

def png_health(data):
    """Heuristic blank/placeholder detection without PIL. Returns (ok, reason).
    A connection-error placeholder renders as a (near-)uniform image: its PNG
    filter output is almost all zero bytes after decompression. An error body
    (JSON/HTML returned with HTTP 200) isn't a PNG at all."""
    if len(data) < 1000:
        return False, f"suspiciously small response ({len(data)} bytes)"
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        head = data[:120].decode("utf-8", "replace")
        return False, "not a PNG (error body?): " + re.sub(r"\s+", " ", head)
    pos, idat, w, h = 8, b"", 0, 0
    while pos + 8 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h = struct.unpack(">II", chunk[:8])
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        return False, "corrupt PNG (IDAT does not decompress)"
    if not raw:
        return False, "empty PNG payload"
    zero_frac = raw.count(0) / len(raw)
    if zero_frac > 0.995:
        return False, f"near-uniform render ({zero_frac:.1%} blank) — likely a connection-error placeholder"
    return True, f"{w}x{h}, {zero_frac:.0%} blank"

def viz_png(lb_id, viz_guid, out_path):
    body = json.dumps({"metadata_identifier": lb_id, "file_format": "PNG",
                       "visualization_identifiers": [viz_guid]}).encode()
    req = urllib.request.Request(f"{ts_lib.HOST}/api/rest/2.0/report/liveboard",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {ts_lib.TOKEN}", "Content-Type": "application/json"})
    data = urllib.request.urlopen(req, context=_SSL).read()
    ok, reason = png_health(data)
    if not ok:
        raise RuntimeError(reason)
    open(out_path, "wb").write(data)
    return len(data)

def liveboard_vizzes(lb_id):
    edoc, err = ts_lib.export_tml(lb_id, "LIVEBOARD")
    if err:
        raise RuntimeError("export failed: " + err)
    lb = yaml.safe_load(edoc)["liveboard"]
    out = []
    for v in lb.get("visualizations", []):
        if v.get("answer"):
            out.append((v.get("viz_guid") or v.get("id"), v["answer"].get("name", v.get("id"))))
    return out

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    lb_id = sys.argv[1]
    default_dir = os.path.join(os.environ.get("TS_WORKDIR") or os.path.join(os.getcwd(), "ts-migration"), "png")
    outdir = next((a for a in sys.argv[2:] if not a.startswith("--")), default_dir)
    os.makedirs(outdir, exist_ok=True)
    if "--viz" in sys.argv:
        vizzes = [(sys.argv[sys.argv.index("--viz") + 1], "viz")]
    else:
        vizzes = liveboard_vizzes(lb_id)
    failed = 0
    for guid, name in vizzes:
        safe = re.sub(r"[^\w.-]+", "_", name)[:40]
        path = os.path.join(outdir, f"{safe}.png")
        try:
            n = viz_png(lb_id, guid, path); print(f"  ✓ {name[:40]:40s} {n} bytes -> {path}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {name[:40]:40s} {e}")
    if failed:
        sys.exit(f"\n{failed}/{len(vizzes)} renders FAILED (blank/placeholder renders count as failures)")

if __name__ == "__main__":
    main()
