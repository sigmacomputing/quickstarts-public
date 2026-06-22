#!/usr/bin/env python3
"""Build the orders-star fixture schema in a MicroStrategy project.

This is the FIXTURE BUILDER (not part of a customer migration): it recreates
the schema objects behind fixtures/bundle.json in a fresh Strategy One
project so the converter's validated end-to-end loop can be rehearsed on a
trial env. Logical tables must exist first (create via the modeling UI or
POST /api/model/tables) and two small sidecar files describe them:

  table_ids.json  — {"ORDER_FACT": "<logical table objectId>", ...}
  folder_ids.json — {"attributes": "<folderId>", "facts": ..., "metrics": ...}

Creates attributes, hierarchy relationships, facts, and metrics; reloads the
schema at the end. Progress is checkpointed to object_ids.json. Idempotence
beyond that checkpoint: not attempted — run against a clean project.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'scripts'))
import mstr

s = mstr.Session()
T = json.load(open('table_ids.json'))
F = json.load(open('folder_ids.json'))
state_path = 'object_ids.json'
try:
    state = json.load(open(state_path))
except FileNotFoundError:
    state = {'attributes': {}, 'facts': {}, 'metrics': {}}


def tbl(name):
    return {'objectId': T[name], 'subType': 'logical_table', 'name': name}


def save():
    json.dump(state, open(state_path, 'w'), indent=1)


def form(category, display, column, tables, name=None):
    f = {'category': category, 'displayFormat': display,
         'expressions': [{'expression': {'tokens': [{'value': column}]},
                          'tables': [tbl(t) for t in tables]}]}
    if name:
        f['name'] = name
    return f


# (name, lookup table, forms, report/browse display form)
ATTRIBUTES = [
    ('Customer', 'CUSTOMER_DIM',
     [form('ID', 'number', 'CUSTOMER_KEY', ['CUSTOMER_DIM', 'ORDER_FACT']),
      form('DESC', 'text', 'CUSTOMER_ID', ['CUSTOMER_DIM'])], 'DESC'),
    ('Customer Segment', 'CUSTOMER_DIM',
     [form('ID', 'text', 'CUSTOMER_SEGMENT', ['CUSTOMER_DIM'])], 'ID'),
    ('Region', 'STORE_DIM',
     [form('ID', 'text', 'REGION', ['STORE_DIM'])], 'ID'),
    ('Store', 'STORE_DIM',
     [{'category': 'ID', 'displayFormat': 'number',
       'expressions': [
           {'expression': {'tokens': [{'value': 'STORE_KEY'}]},
            'tables': [tbl('STORE_DIM')]},
           {'expression': {'tokens': [{'value': 'ORDER_STORE_KEY'}]},
            'tables': [tbl('ORDER_FACT')]},
       ]},
      form('DESC', 'text', 'STORE_NAME', ['STORE_DIM'])], 'DESC'),
    ('Category', 'PRODUCT_DIM',
     [form('ID', 'text', 'CATEGORY', ['PRODUCT_DIM'])], 'ID'),
    ('Product', 'PRODUCT_DIM',
     [form('ID', 'number', 'PRODUCT_KEY', ['PRODUCT_DIM', 'ORDER_FACT']),
      form('DESC', 'text', 'PRODUCT_NAME', ['PRODUCT_DIM'])], 'DESC'),
    ('Year', 'DATE_DIM',
     [form('ID', 'number', 'YEAR', ['DATE_DIM'])], 'ID'),
    ('Month', 'DATE_DIM',
     [form('ID', 'number', 'MONTH_NUMBER', ['DATE_DIM']),
      form('DESC', 'text', 'MONTH_NAME', ['DATE_DIM'])], 'DESC'),
    ('Day', 'DATE_DIM',
     [{'category': 'ID', 'displayFormat': 'number',
       'expressions': [
           {'expression': {'tokens': [{'value': 'DATE_KEY'}]},
            'tables': [tbl('DATE_DIM')]},
           {'expression': {'tokens': [{'value': 'ORDER_DATE_KEY'}]},
            'tables': [tbl('ORDER_FACT')]},
       ]},
      form('DESC', 'date', 'FULL_DATE', ['DATE_DIM'])], 'DESC'),
    ('Order Channel', 'ORDER_FACT',
     [form('ID', 'text', 'ORDER_CHANNEL', ['ORDER_FACT'])], 'ID'),
    ('Order Status', 'ORDER_FACT',
     [form('ID', 'text', 'ORDER_STATUS', ['ORDER_FACT'])], 'ID'),
]

# child -> (parent, relationship table)
RELATIONSHIPS = {
    'Customer': ('Customer Segment', 'CUSTOMER_DIM'),
    'Store': ('Region', 'STORE_DIM'),
    'Product': ('Category', 'PRODUCT_DIM'),
    'Month': ('Year', 'DATE_DIM'),
    'Day': ('Month', 'DATE_DIM'),
}

FACTS = [
    ('Net Revenue', 'NET_REVENUE'),
    ('Gross Profit', 'GROSS_PROFIT'),
    ('Quantity', 'QUANTITY_ORDERED'),
    ('Discount', 'DISCOUNT_AMOUNT'),
    ('Order Id Fact', 'ORDER_ID'),
]

METRICS = [
    ('Total Net Revenue', 'Sum([Net Revenue]) {~}'),
    ('Total Gross Profit', 'Sum([Gross Profit]) {~}'),
    ('Units Sold', 'Sum([Quantity]) {~}'),
    ('Order Count', 'Count<Distinct=True>([Order Id Fact]) {~}'),
    ('Profit Margin Pct', '([Total Gross Profit] / [Total Net Revenue])'),
]


def create_attributes(cs):
    for name, lookup, forms, disp in ATTRIBUTES:
        if name in state['attributes']:
            continue
        body = {
            'information': {'name': name, 'subType': 'attribute',
                            'destinationFolderId': F['attributes']},
            'forms': forms,
            'attributeLookupTable': tbl(lookup),
            'keyForm': {'name': 'ID'},
            'displays': {'reportDisplays': [{'name': disp}],
                         'browseDisplays': [{'name': disp}]},
        }
        r = s.cs_post('/model/attributes', body, cs)
        state['attributes'][name] = r['information']['objectId']
        print('attribute', name, '->', state['attributes'][name])
        save()


def create_relationships(cs):
    for child, (parent, table) in RELATIONSHIPS.items():
        child_id = state['attributes'][child]
        body = {'relationships': [{
            'parent': {'objectId': state['attributes'][parent],
                       'subType': 'attribute', 'name': parent},
            'child': {'objectId': child_id,
                      'subType': 'attribute', 'name': child},
            'relationshipTable': tbl(table),
            'relationshipType': 'one_to_many',
        }]}
        s.put(f'/model/systemHierarchy/attributes/{child_id}/relationships',
              body, headers={'X-MSTR-MS-Changeset': cs})
        print('relationship', parent, '>', child)


def create_facts(cs):
    for name, column in FACTS:
        if name in state['facts']:
            continue
        body = {
            'information': {'name': name, 'subType': 'fact',
                            'destinationFolderId': F['facts']},
            'expressions': [{'expression': {'tokens': [{'value': column}]},
                             'tables': [tbl('ORDER_FACT')]}],
        }
        r = s.cs_post('/model/facts', body, cs)
        state['facts'][name] = r['information']['objectId']
        print('fact', name, '->', state['facts'][name])
        save()


def create_metrics(cs):
    for name, formula in METRICS:
        if name in state['metrics']:
            continue
        body = {
            'information': {'name': name, 'subType': 'metric',
                            'destinationFolderId': F['metrics']},
            'expression': {'tokens': [{'value': formula}]},
        }
        r = s.cs_post('/model/metrics', body, cs)
        state['metrics'][name] = r['information']['objectId']
        print('metric', name, '->', state['metrics'][name])
        save()


if __name__ == '__main__':
    s.schema_edit(create_attributes)
    s.schema_edit(create_relationships)
    s.schema_edit(create_facts)
    s.schema_edit(create_metrics)
    s.post('/model/schema/reload')
    print('schema reloaded')
