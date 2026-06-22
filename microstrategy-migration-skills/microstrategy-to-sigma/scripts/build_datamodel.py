#!/usr/bin/env python3
"""Build + validate a Strategy One Data Model ("Orders Data Model") via REST.

Flow (all learned by probing; see final report):
  Phase A  dataServer workspace -> per-table pipelines (this is the ONLY way to
           bind a data-model table to a datasource; classic physical tables are
           rejected with "not from pipeline").
  Phase B  one changeset: create DM (connect_live) + 4 tables + attributes
           (+ hierarchy relationships) + factMetrics, then commit.  An EMPTY
           data model cannot be committed, so DM + tables share a changeset.
  Phase C  second changeset: /metrics (token text resolves committed names).
  Phase D  publish (instances -> publish -> poll publishStatus).
  Phase E  query validation via /api/v2/cubes/{id}/instances (revenue by region).

State in datamodel_ids.json; re-running skips completed phases.
NOTE: /links is cross-data-model only — in-model joins come from shared
multi-table key attributes (Store/Product/Day below).
"""
import json
import sys
import time

import mstr, os

DS = os.environ['MSTR_DATASOURCE_ID']  # Snowflake datasource (GET /api/datasources)
TABLES = ['ORDER_FACT', 'PRODUCT_DIM', 'STORE_DIM', 'DATE_DIM']
STATE_PATH = 'datamodel_ids.json'

s = mstr.Session()
try:
    state = json.load(open(STATE_PATH))
except FileNotFoundError:
    state = {'tables': {}, 'attributes': {}, 'factMetrics': {}, 'metrics': {}}


def save():
    json.dump(state, open(STATE_PATH, 'w'), indent=1)


# ---------- Phase A: pipelines ----------
def make_pipelines():
    wid = s.post('/dataServer/workspaces', {})['id']
    pipelines = {}
    for t in TABLES:
        p = s.post(f'/dataServer/workspaces/{wid}/pipelines', {})
        pid = p['id']
        s.post(f'/dataServer/workspaces/{wid}/pipelines/{pid}/tables',
               {'type': 'source', 'name': t,
                'importSource': {'type': 'single_table', 'dataSourceId': DS,
                                 'namespace': 'TJ', 'tableName': t}})
        pipelines[t] = s.get(f'/dataServer/workspaces/{wid}/pipelines/{pid}')
        print('pipeline', t, 'ok')
    return pipelines


# ---------- Phase B: DM + tables + attributes + factMetrics ----------
def tref(name):
    return {'objectId': state['tables'][name], 'subType': 'logical_table',
            'name': name}


def aref(name):
    return {'objectId': state['attributes'][name], 'subType': 'attribute',
            'name': name}


def form(name, fmt, exprs, lookup, category=None):
    """exprs: list of (column, table)."""
    f = {'name': name, 'displayFormat': fmt, 'lookupTable': tref(lookup),
         'expressions': [{'expression': {'tokens': [{'value': col}]},
                          'tables': [tref(t)]} for col, t in exprs]}
    if category:
        f['category'] = category
    return f


def build_core(cs):
    pipelines = make_pipelines()
    # destinationFolderId is REQUIRED at commit time ("The destination folder
    # is not provided"), even though POST succeeds without it.
    reports_folder = json.load(open('folder_ids.json'))['reports']
    r = s.cs_post('/model/dataModels',
                  {'information': {'name': 'Orders Data Model',
                                   'destinationFolderId': reports_folder},
                   'dataServeMode': 'connect_live'}, cs)
    state['dataModelId'] = r['information']['objectId']
    state['schemaFolderId'] = r.get('schemaFolderId')
    dm = state['dataModelId']
    print('dataModel:', dm)

    for t in TABLES:
        rt = s.cs_post(f'/model/dataModels/{dm}/tables',
                       {'information': {'name': t},
                        'physicalTable': {'pipeline': json.dumps(pipelines[t])}},
                       cs)
        state['tables'][t] = rt['information']['objectId']
        print('table', t, '->', state['tables'][t])

    # (name, lookup, forms, display form, parent-or-None)
    attrs = [
        ('Region', 'STORE_DIM',
         [form('ID', 'text', [('REGION', 'STORE_DIM')], 'STORE_DIM', 'ID')],
         'ID', None),
        ('Category', 'PRODUCT_DIM',
         [form('ID', 'text', [('CATEGORY', 'PRODUCT_DIM')], 'PRODUCT_DIM', 'ID')],
         'ID', None),
        ('Year', 'DATE_DIM',
         [form('ID', 'number', [('YEAR', 'DATE_DIM')], 'DATE_DIM', 'ID')],
         'ID', None),
        ('Month', 'DATE_DIM',
         [form('ID', 'number', [('MONTH_NUMBER', 'DATE_DIM')], 'DATE_DIM', 'ID'),
          form('DESC', 'text', [('MONTH_NAME', 'DATE_DIM')], 'DATE_DIM', 'DESC')],
         'DESC', 'Year'),
        # multi-table key attributes below carry the star joins
        ('Store', 'STORE_DIM',
         [form('ID', 'number', [('STORE_KEY', 'STORE_DIM'),
                                ('ORDER_STORE_KEY', 'ORDER_FACT')],
               'STORE_DIM', 'ID'),
          form('DESC', 'text', [('STORE_NAME', 'STORE_DIM')], 'STORE_DIM', 'DESC')],
         'DESC', 'Region'),
        ('Product', 'PRODUCT_DIM',
         [form('ID', 'number', [('PRODUCT_KEY', 'PRODUCT_DIM'),
                                ('PRODUCT_KEY', 'ORDER_FACT')],
               'PRODUCT_DIM', 'ID'),
          form('DESC', 'text', [('PRODUCT_NAME', 'PRODUCT_DIM')], 'PRODUCT_DIM',
               'DESC')],
         'DESC', 'Category'),
        ('Day', 'DATE_DIM',
         [form('ID', 'number', [('DATE_KEY', 'DATE_DIM'),
                                ('ORDER_DATE_KEY', 'ORDER_FACT')],
               'DATE_DIM', 'ID'),
          form('DESC', 'date', [('FULL_DATE', 'DATE_DIM')], 'DATE_DIM', 'DESC')],
         'DESC', 'Month'),
        ('Order Channel', 'ORDER_FACT',
         [form('ID', 'text', [('ORDER_CHANNEL', 'ORDER_FACT')], 'ORDER_FACT',
               'ID')],
         'ID', None),
    ]
    rels = []
    for name, lookup, forms, disp, parent in attrs:
        body = {'information': {'name': name}, 'forms': forms,
                'attributeLookupTable': tref(lookup),
                'keyForm': {'name': forms[0]['name']},
                'displays': {'reportDisplays': [{'name': disp}],
                             'browseDisplays': [{'name': disp}]}}
        ra = s.cs_post(f'/model/dataModels/{dm}/attributes', body, cs)
        state['attributes'][name] = ra['information']['objectId']
        print('attribute', name, '->', state['attributes'][name])
        if parent:
            rels.append((name, parent, lookup))

    for child, parent, table in rels:
        body = {'relationships': [{'parent': aref(parent), 'child': aref(child),
                                   'relationshipTable': tref(table),
                                   'relationshipType': 'one_to_many'}]}
        s.put(f'/model/dataModels/{dm}/attributes/'
              f'{state["attributes"][child]}/relationships',
              body, headers={'X-MSTR-MS-Changeset': cs})
        print('relationship', parent, '>', child)

    fms = [
        ('NET_REVENUE', 'NET_REVENUE', 'sum',
         {'type': 'double', 'precision': 8, 'scale': 2}, None),
        ('GROSS_PROFIT', 'GROSS_PROFIT', 'sum',
         {'type': 'double', 'precision': 8, 'scale': 2}, None),
        ('QUANTITY_ORDERED', 'QUANTITY_ORDERED', 'sum',
         {'type': 'int64', 'precision': 8, 'scale': 0}, None),
        ('ORDER_ID', 'ORDER_ID', 'count',
         {'type': 'utf8_char', 'precision': 20, 'scale': 0},
         [{'name': 'Distinct', 'value': {'type': 'boolean', 'value': 'true'}}]),
    ]
    for name, col, fn, dt, props in fms:
        body = {'information': {'name': name},
                'fact': {'dataType': dt,
                         'expressions': [{'expression': {'tokens': [{'value': col}]},
                                          'tables': [tref('ORDER_FACT')]}]},
                'function': fn}
        if props:
            body['functionProperties'] = props
        try:
            rf = s.cs_post(f'/model/dataModels/{dm}/factMetrics', body, cs)
        except RuntimeError as e:
            if props:
                print('factMetric', name, 'with Distinct failed:', str(e)[:200])
                body.pop('functionProperties')
                rf = s.cs_post(f'/model/dataModels/{dm}/factMetrics', body, cs)
            else:
                raise
        state['factMetrics'][name] = rf['information']['objectId']
        print('factMetric', name, '->', state['factMetrics'][name])


# ---------- Phase C: metrics ----------
def build_metrics(cs):
    dm = state['dataModelId']
    metrics = [
        ('Total Net Revenue', ['Sum([NET_REVENUE]) {~}',
                               '[NET_REVENUE]']),
        ('Total Gross Profit', ['Sum([GROSS_PROFIT]) {~}',
                                '[GROSS_PROFIT]']),
        ('Order Count', ['Count<Distinct=True>([ORDER_ID]) {~}',
                         '[ORDER_ID]']),
    ]
    for name, variants in metrics:
        if name in state['metrics']:
            continue
        last = None
        for v in variants:
            body = {'information': {'name': name},
                    'expression': {'tokens': [{'value': v}]}}
            try:
                rm = s.cs_post(f'/model/dataModels/{dm}/metrics', body, cs)
                state['metrics'][name] = rm['information']['objectId']
                print('metric', name, '->', state['metrics'][name],
                      'formula:', v)
                last = None
                break
            except RuntimeError as e:
                last = e
                print('metric', name, 'variant failed:', v, '|', str(e)[:200])
        if last:
            raise last


# ---------- Phase D: publish ----------
def publish():
    dm = state['dataModelId']
    s.post(f'/dataModels/{dm}/instances')
    inst = (s.last_headers.get('x-mstr-ms-instance')
            or s.last_headers.get('x-mstr-datamodelinstanceid'))
    print('instance:', inst, {k: v for k, v in s.last_headers.items()
                              if 'mstr' in k})
    body = {'tables': [{'id': tid, 'refreshPolicy': 'replace'}
                       for tid in state['tables'].values()]}
    try:
        s.post(f'/dataModels/{dm}/publish', body,
               headers={'X-MSTR-DataModelInstanceId': inst})
    except RuntimeError as e:
        if 'no publish workflow' in str(e):
            # connect_live data models are live — nothing to publish
            print('publish skipped:', str(e)[:120])
            state['published'] = 'skipped (connect_live has no publish workflow)'
            return
    for _ in range(60):
        st = s.get(f'/dataModels/{dm}/publishStatus')
        print('publishStatus:', json.dumps(st)[:200])
        if st.get('status') == 1:   # DssXmlStatusResult = ready
            break
        time.sleep(2)
    state['published'] = True


# ---------- Phase E: query validation ----------
def query():
    dm = state['dataModelId']
    body = {'requestedObjects': {
        'attributes': [{'id': state['attributes']['Region']}],
        'metrics': [{'id': state['metrics']['Total Net Revenue']},
                    {'id': state['metrics']['Order Count']}]}}
    out = s.post(f'/v2/cubes/{dm}/instances', body)
    # connect_live executes synchronously: status==1 with data inline.
    # (GET /v2/cubes/{id}/instances/{iid}/status 500s "Catastrophic failure"
    # for these instances — do not poll.)
    iid = out['instanceId']
    for _ in range(30):
        if out.get('status') == 1 and 'data' in out:
            break
        time.sleep(1)
        out = s.get(f'/v2/cubes/{dm}/instances/{iid}')
    json.dump(out, open('query_validation.json', 'w'), indent=1)
    rows = out['data']['headers']['rows']
    attr_el = out['definition']['grid']['rows'][0]['elements']
    vals = out['data']['metricValues']['raw']
    print('\nRevenue by Region (live Snowflake via data model):')
    for i, hr in enumerate(rows):
        region = attr_el[hr[0]]['formValues'][0]
        print(f'  {region:10s}  net_rev={vals[i][0]:>10}  orders={vals[i][1]}')
    return out


if __name__ == '__main__':
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if 'dataModelId' not in state and step in ('all', 'core'):
        cs = s.changeset(schema_edit=False)
        try:
            build_core(cs)
        except Exception:
            s.abort(cs)
            state.pop('dataModelId', None)
            state['tables'].clear(); state['attributes'].clear()
            state['factMetrics'].clear()
            raise
        s.commit(cs)
        save()
        print('core committed')
    if step in ('all', 'metrics') and len(state['metrics']) < 3:
        cs = s.changeset(schema_edit=False)
        try:
            build_metrics(cs)
        except Exception:
            s.abort(cs)
            raise
        s.commit(cs)
        save()
        print('metrics committed')
    if step in ('all', 'publish') and not state.get('published'):
        publish()
        save()
    if step in ('all', 'query'):
        query()
