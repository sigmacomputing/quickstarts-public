#!/usr/bin/env python3
"""Extract a MicroStrategy dossier + its full semantic model into one JSON bundle.

Usage: python3 extract.py <dossierId> [out.json]

The bundle is the converter input: dossier definition (chapters/pages/vizzes),
each dataset report's template, and the schema objects they reference —
attributes (forms, expressions, lookup tables), facts, metrics (formula text),
and logical tables (physical table + namespace + datasource).
"""
import json
import sys
import mstr


def extract(s, dossier_id):
    bundle = {'dossier': s.get(f'/v2/dossiers/{dossier_id}/definition')}

    # datasets -> report definitions (template + data source)
    reports = {}
    for ds in bundle['dossier'].get('datasets', []):
        rid = ds['id']
        reports[rid] = s.get(
            f'/model/reports/{rid}?showExpressionAs=tokens')
    bundle['reports'] = reports

    # collect referenced attribute/metric ids from report templates
    attr_ids, metric_ids = set(), set()
    for r in reports.values():
        units = (r.get('dataSource', {}).get('dataTemplate', {})
                 .get('units', []))
        for u in units:
            if u.get('type') == 'attribute':
                attr_ids.add(u['id'])
            elif u.get('type') == 'metrics':
                for e in u.get('elements', []):
                    metric_ids.add(e['id'])

    bundle['attributes'] = {}
    table_ids = set()
    for aid in sorted(attr_ids):
        a = s.get(f'/model/attributes/{aid}?showExpressionAs=tokens')
        bundle['attributes'][aid] = a
        for f in a.get('forms', []):
            for ex in f.get('expressions', []):
                for t in ex.get('tables', []):
                    table_ids.add(t['objectId'])

    bundle['metrics'] = {}
    fact_ids = set()
    for mid in sorted(metric_ids):
        m = s.get(f'/model/metrics/{mid}?showExpressionAs=tokens')
        bundle['metrics'][mid] = m
        for tok in m.get('expression', {}).get('tokens', []):
            tgt = tok.get('target')
            if tgt and tgt.get('subType') == 'fact':
                fact_ids.add(tgt['objectId'])
            if tgt and tgt.get('subType') == 'metric':
                metric_ids.add(tgt['objectId'])  # compound metric base

    # second pass for compound-metric bases discovered above
    for mid in sorted(metric_ids):
        if mid not in bundle['metrics']:
            m = s.get(f'/model/metrics/{mid}?showExpressionAs=tokens')
            bundle['metrics'][mid] = m
            for tok in m.get('expression', {}).get('tokens', []):
                tgt = tok.get('target')
                if tgt and tgt.get('subType') == 'fact':
                    fact_ids.add(tgt['objectId'])

    bundle['facts'] = {}
    for fid in sorted(fact_ids):
        f = s.get(f'/model/facts/{fid}?showExpressionAs=tokens')
        bundle['facts'][fid] = f
        for ex in f.get('expressions', []):
            for t in ex.get('tables', []):
                table_ids.add(t['objectId'])

    bundle['tables'] = {}
    for tid in sorted(table_ids):
        bundle['tables'][tid] = s.get(f'/model/tables/{tid}')

    # attribute relationships (hierarchy) for join/topology hints
    bundle['relationships'] = {}
    for aid in sorted(attr_ids):
        try:
            rel = s.get(f'/model/systemHierarchy/attributes/{aid}/relationships')
            if rel.get('relationships'):
                bundle['relationships'][aid] = rel['relationships']
        except Exception:
            pass

    return bundle


if __name__ == '__main__':
    dossier_id = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'bundle.json'
    s = mstr.Session()
    b = extract(s, dossier_id)
    json.dump(b, open(out, 'w'), indent=1)
    print(f'wrote {out}: {len(b["reports"])} reports, '
          f'{len(b["attributes"])} attributes, {len(b["metrics"])} metrics, '
          f'{len(b["facts"])} facts, {len(b["tables"])} tables')
