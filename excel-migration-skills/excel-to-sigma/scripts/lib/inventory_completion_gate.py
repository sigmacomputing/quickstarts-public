"""Narrow evidence precheck for an intentionally empty Inventory append log.

This does not override the general migration completion gate or attest that
supplied evidence is authentic. Independent live verification remains required.
"""
from __future__ import annotations

import re

SOURCE = '461bee7b71f30822ea4d263ef529723d89dc9f11e7365e6434cefe89619c2f7e'
SCHEMA = 'SIGMA_WRITE_DB.SIGMA_MIGRATION8_INV_TEST'
GATES = ('sourceAudit','inputBinding','actionBinding','published','persistence','roleSessions','restoration')


class InventoryCompletionError(ValueError):
    pass


def _need(condition, code):
    if not condition:
        raise InventoryCompletionError(code)


def assess_empty_snapshot_log(evidence):
    _need(isinstance(evidence,dict), 'EVIDENCE_REQUIRED')
    _need(evidence.get('kind') == 'inventory-empty-append-log' and
        evidence.get('role') == 'append-only-snapshots' and evidence.get('schema') == SCHEMA,
        'NARROW_APPEND_LOG_SCOPE_REQUIRED')
    _need(evidence.get('sourceSha256') == SOURCE, 'SOURCE_MISMATCH')
    for field in ('documentId','version','elementId','rowIdColumnId','publishedButtonId'):
        _need(isinstance(evidence.get(field),str) and bool(evidence[field]), 'PHYSICAL_BINDING_REQUIRED')
    _need(re.fullmatch(r'[0-9a-f]{64}',str(evidence.get('bindingHash',''))) is not None,
        'EXACT_BINDING_HASH_REQUIRED')
    cols=evidence.get('columnIds')
    _need(isinstance(cols,dict) and {'Operation ID','Source Row','SKU','Forecast Units','Week Start'}<=set(cols)
        and all(isinstance(v,str) and v for v in cols.values()) and len(set(cols.values()))==len(cols),
        'EXACT_PHYSICAL_COLUMNS_REQUIRED')
    captures=evidence.get('captures')
    names=('baseline','first','sameIntentRetry','newIntent','restored')
    _need(isinstance(captures,dict) and set(captures)==set(names), 'COMPLETE_APPEND_SEQUENCE_REQUIRED')
    counts=(0,72,72,144,0)
    seen=set()
    for name,count in zip(names,counts):
        item=captures[name]
        _need(isinstance(item,dict) and item.get('origin')=='sigma-query' and
            type(item.get('count')) is int and item['count']==count,
            'ACTUAL_APPEND_ROW_COUNTS_REQUIRED')
        _need(all(item.get(k)==evidence[k] for k in ('documentId','version','elementId','bindingHash','rowIdColumnId')),
            'CAPTURE_BINDING_MISMATCH')
        _need(isinstance(item.get('evidenceId'),str) and item['evidenceId'] not in seen,
            'DISTINCT_QUERY_EVIDENCE_REQUIRED')
        seen.add(item['evidenceId'])
        _need(re.fullmatch(r'[0-9a-f]{64}',str(item.get('rowFingerprint',''))) is not None,
            'ROW_FINGERPRINT_REQUIRED')
        if name not in ('baseline','restored'):
            _need(all(isinstance(item.get(k),str) and item[k] for k in
                ('publishedActionExecutionId','writeEvidenceId')),
                'ACTUAL_PUBLISHED_WRITE_EVIDENCE_REQUIRED')
    _need(captures['baseline']['rowFingerprint']==captures['restored']['rowFingerprint'] and
        captures['first']['rowFingerprint']==captures['sameIntentRetry']['rowFingerprint'] and
        captures['newIntent']['rowFingerprint'] != captures['first']['rowFingerprint'],
        'RETRY_OR_RESTORATION_NOT_PROVEN')
    intents=evidence.get('intentIds',{})
    _need(all(isinstance(intents.get(k),str) and intents[k] for k in ('first','retry','new')) and
        intents['first']==intents['retry'] and intents['new']!=intents['first'],
        'INTENT_ID_SEQUENCE_REQUIRED')
    roles=evidence.get('roles',{})
    _need(isinstance(roles,dict) and set(roles)=={'planner','viewer'} and
        type(roles['planner'].get('writeCount')) is int and roles['planner']['writeCount']==144 and
        roles['viewer'].get('writeCount')==0 and
        all(isinstance(roles[r].get('evidenceId'),str) and roles[r]['evidenceId'] for r in roles),
        'ROLE_SESSION_EVIDENCE_REQUIRED')
    screenshots=evidence.get('screenshots')
    _need(isinstance(screenshots,list) and len(screenshots)>=3 and
        all(isinstance(x,str) and x for x in screenshots), 'PUBLISHED_SCREENSHOTS_REQUIRED')
    gates=evidence.get('productionGates',{})
    _need(isinstance(gates,dict) and set(gates)==set(GATES) and all(gates[k] is True for k in GATES),
        'PRODUCTION_GATES_REQUIRED')
    return {'status':'NARROW_EMPTY_LOG_EVIDENCE_REVIEW_ELIGIBLE',
        'sourceSha256':SOURCE,'documentId':evidence['documentId'],
        'productionStatus':'BLOCKED_PENDING_INDEPENDENT_LIVE_VERIFICATION'}
