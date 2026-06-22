#!/usr/bin/env python3
"""Extract the complete 'Orders Data Model' definition -> datamodel_definition.json.

Reads every dataModels sub-resource (model + tables + attributes + factMetrics
+ metrics + links + hierarchy) with token+tree expression forms where the API
supports showExpressionAs. GETs work without a changeset (read from metadata).
Output is the converter input for MicroStrategy DataModel -> Sigma.
"""
import json

import mstr

s = mstr.Session()
state = json.load(open('datamodel_ids.json'))
dm = state['dataModelId']


def get(path, **kw):
    try:
        return s.get(path, **kw)
    except RuntimeError as e:
        return {'_error': str(e)[:500]}


out = {
    'dataModelId': dm,
    'dataModel': get(f'/model/dataModels/{dm}'),
    'tables': get(f'/model/dataModels/{dm}/tables'
                  '?showExpressionAs=tokens&showDerivedColumns=true'
                  '&showDerivedForms=true'),
    'attributes': get(f'/model/dataModels/{dm}/attributes'
                      '?showExpressionAs=tokens&showDerivedForms=true'),
    'factMetrics': get(f'/model/dataModels/{dm}/factMetrics'
                       '?showExpressionAs=tokens'),
    'metrics': get(f'/model/dataModels/{dm}/metrics'
                   '?showExpressionAs=tokens&showFilterTokens=true'),
    'links': None,  # filled below — GET /links requires a changeset header
    'hierarchy': get(f'/model/dataModels/{dm}/hierarchy'),
    'attributeRelationships': {},
}
for name, aid in state['attributes'].items():
    out['attributeRelationships'][name] = get(
        f'/model/dataModels/{dm}/attributes/{aid}/relationships')

# GET /links is changeset-scoped (unlike every other GET here); use a
# throwaway non-schema changeset and abort it immediately.
cs = s.changeset(schema_edit=False)
try:
    out['links'] = get(f'/model/dataModels/{dm}/links',
                       headers={'X-MSTR-MS-Changeset': cs})
finally:
    s.abort(cs)

json.dump(out, open('datamodel_definition.json', 'w'), indent=1)
print('wrote datamodel_definition.json')
for k, v in out.items():
    if isinstance(v, dict):
        err = v.get('_error')
        n = v.get('total', '')
        print(f'  {k}: {"ERR " + err if err else ("total=" + str(n) if n != "" else "ok")}')
