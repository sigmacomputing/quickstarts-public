"""Complete SDK action captures and strict known-artifact recovery boundaries.

REST GET can omit native action sequences. Formula has no public expression
getter in the current SDK. This module never decompiles opaque repr strings.
The controller supplies complete getter observations plus independently reviewed
construction/restoration artifacts and actual isolated restoration proof.
"""
import copy
import hashlib
import json
import re


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def empty_action_capture(document,*,evidence_id):
    """Test/controller shape helper only; NEVER infer absence from REST contents.

    The caller must fill this from actual SDK inspection, including every element
    with no actions. This helper is deliberately labeled a template, not evidence.
    """
    return {'documentId':document['workbookId'],'version':document['documentVersion'],'evidenceId':evidence_id,
        'origin':'TEMPLATE_NOT_RUNTIME','complete':False,'elements':{e['id']:{'elementId':e['id'],'complete':False,'sequences':[]} for e in document['contents']['elements']}}


def configuration(element):
    # SDK assigns new sequence IDs on reconstruction. Retain every observable
    # semantic/configuration field and only exclude that assigned sequence ID.
    return {'sequences':[{k:copy.deepcopy(v) for k,v in seq.items() if k!='id'} for seq in element['sequences']]}


def _block(block):
    required={'InsertRowEffect':{'tableId','values','returns'},'UpdateRowsEffect':{'tableId','whichRows','values'},
        'DeleteRowsEffect':{'tableId','whichRows'},'TextSetControlValueEffect':{'controlId','value'},
        'FloatSetControlValueEffect':{'controlId','value'},'BooleanSetControlValueEffect':{'controlId','value'},
        'DateSetControlValueEffect':{'controlId','value'},'NavigateAction':{'targetPageId'},
        'RunPythonElement':{'codeElementId','name'},'CallStoredProcedure':{'connectionId','path','signature','arguments','name'},
        'IfElseAction':{'branches','elseEffects'}}
    if not isinstance(block,dict) or block.get('kind') not in required or not isinstance(block.get('fields'),dict) or not required[block['kind']]<=set(block['fields']):
        raise ValueError('unsupported/incomplete SDK action block; exact known-artifact adapter required')
    fields=block['fields']
    if block['kind']=='IfElseAction':
        for branch in fields['branches']:
            if not {'condition','effects'}<=set(branch):raise ValueError('incomplete action branch')
            for child in branch['effects']:_block(child)
        for child in fields['elseEffects']:_block(child)


def validate_action_inventory(capture,document,*,require_recovery=False):
    if (not isinstance(capture,dict) or capture.get('documentId')!=document.get('workbookId') or capture.get('version')!=document.get('documentVersion')
        or capture.get('origin')!='sigma-sdk-readonly' or capture.get('complete') is not True or not capture.get('evidenceId')):
        raise ValueError('complete fresh SDK action inventory required; REST absence is not proof')
    expected={e['id'] for e in document['contents']['elements']};elements=capture.get('elements',{})
    if set(elements)!=expected:raise ValueError('SDK action inventory must cover every document element')
    unresolved=[]
    for eid,element in elements.items():
        if element.get('elementId')!=eid or element.get('complete') is not True or element.get('inspection') not in {'list_action_sequences','sdk-type-no-action-events'} or not isinstance(element.get('sequences'),list):
            raise ValueError('complete SDK event observation required for '+eid)
        sequences=element['sequences'];ids=[s.get('id') for s in sequences]
        if any(not identity for identity in ids) or len(ids)!=len(set(ids)):raise ValueError('actual ordered sequence IDs required')
        for seq in sequences:
            if not {'id','name','trigger','disabled','condition','blocks','successToast'}<=set(seq) or type(seq['disabled']) is not bool or not isinstance(seq['blocks'],list):raise ValueError('SDK sequence capture omits condition/trigger/ordered blocks/toast')
            if seq['successToast'] is not None and not {'title','message','formulas'}<=set(seq['successToast']):raise ValueError('complete SDK toast observation required')
            for block in seq['blocks']:_block(block)
        if sequences:
            artifact=element.get('restorationArtifact') or {};proof=artifact.get('restoreProof') or {}
            observation={k:v for k,v in element.items() if k!='restorationArtifact'}
            if (element.get('semanticHash')!=digest(configuration(element)) or not artifact.get('reviewer') or artifact.get('elementId')!=eid
                or artifact.get('documentId')!=capture['documentId'] or artifact.get('sourceObservationHash')!=digest(observation)
                or artifact.get('semanticHash')!=element['semanticHash'] or not isinstance(artifact.get('program'),str)
                or artifact.get('programHash')!=hashlib.sha256(artifact['program'].encode()).hexdigest()
                or artifact.get('constructionArtifactHash') is None or artifact.get('bindingHash') is None
                or proof.get('status')!='PASSED_ISOLATED_RESTORATION' or not proof.get('evidenceId') or not proof.get('documentId')
                or proof.get('semanticHash')!=element['semanticHash'] or not proof.get('sdkReadbackEvidenceId')
                or proof.get('programHash')!=artifact.get('programHash') or proof.get('bindingHash')!=artifact.get('bindingHash')
                or proof.get('beforeMissingSequences') is not True
                or artifact.get('guardPolicy')!='missing-sequences-only; exact-current-target-and-bindings; no-constructor-replay'):
                unresolved.append(eid)
    if require_recovery and unresolved:raise ValueError('SDK actions lack reviewed exact restoration artifacts/proof: '+', '.join(unresolved))
    return {'status':'READY' if not unresolved else 'BLOCKED_ACTION_RESTORATION','unresolved':unresolved,'inventoryHash':digest(capture)}


def action_semantics(element):
    if not element['sequences']:return {'sequences':[]}
    if element.get('semanticHash')!=digest(configuration(element)):raise ValueError('SDK action configuration hash stale; opaque semantics need known-artifact review')
    return configuration(element)


def verify_action_preservation(before,after,after_document,*,allowed_changes=None):
    """Post-REST SDK proof is mandatory even if the REST JSON is unchanged."""
    validate_action_inventory(after,after_document)
    changes=allowed_changes or {}
    if before['documentId']!=after['documentId']:raise ValueError('action inventory document changed')
    for eid,old in before['elements'].items():
        new=after['elements'].get(eid)
        if new is None:raise ValueError('old SDK action element disappeared')
        expected=changes.get(eid,action_semantics(old))
        if action_semantics(new)!=expected:raise ValueError('SDK action semantics missing/changed after REST: '+eid)
    return {'status':'VERIFIED_SDK_ACTION_SEMANTICS','beforeHash':digest(before),'afterHash':digest(after),
        'evidenceId':after['evidenceId'],'limitations':['Reconstructed SDK sequence IDs may differ; exact reviewed semantic/configuration bindings and actual proof are required.']}


def action_restore_programs(capture):
    return {eid:copy.deepcopy(element['restorationArtifact']) for eid,element in capture['elements'].items() if element['sequences']}


def qualify_public_selection_capture(capture,document,fragment_bundle,review):
    """Bind ONLY known on-select CountDistinct Selection literals across SDK gaps.

    A caller records getter unavailability as a structured sentinel, never a
    Missing-node repr. Exact REST constructor + actual SDK block/control + named
    published 0/1/multi/clear proof authorizes the one canonical literal. Authority
    provenance is outside sequence configuration and cannot alter semantics.
    This does not provide restoration proof or authenticate runtime sessions.
    """
    return _qualify_public_selection(capture,document,fragment_bundle,review,published=True)


def qualify_public_selection_construction(capture,document,fragment_bundle,review):
    """Known REST literal + typed SDK binding only; NEVER published count proof.

    This permits inspection of disabled construction and the control-only probe
    before any business effect is enabled. It grants no runtime authority.
    """
    return _qualify_public_selection(capture,document,fragment_bundle,review,published=False)


def _qualify_public_selection(capture,document,fragment_bundle,review,*,published):
    try:
        from .input_sync import _digest
    except ImportError:
        from input_sync import _digest
    if fragment_bundle.get('fragmentHash')!=_digest({k:v for k,v in fragment_bundle.items() if k!='fragmentHash'}):raise ValueError('Selection source fragment hash stale')
    validate_action_inventory(capture,document)
    required={'documentId':document['workbookId'],'version':document['documentVersion'],'contentsHash':_digest(document['contents']),
        'captureHash':digest(capture),'fragmentHash':fragment_bundle['fragmentHash'],
        **{k:fragment_bundle[k] for k in ('sourceHash','planHash','bindingHash')}}
    evidence=review.get('publishedSelectionEvidence') or {}
    authorities=fragment_bundle.get('selectionAuthorities',[])
    expected_keys={a['hostElementId']+':'+a['controlElementId'] for a in authorities}
    owner=str(review.get('owner') or '').strip()
    if (review.get('status')!='APPROVED_STAGING' or not owner or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',owner)
            or any(review.get(k)!=v for k,v in required.items()) or not expected_keys or (published and set(evidence)!=expected_keys)):
        raise ValueError('exact reviewed actual published Selection authority required')
    for authority in authorities if published else []:
        cases=evidence[authority['hostElementId']+':'+authority['controlElementId']]
        if not isinstance(cases,dict) or set(cases)!={'zero','one','multiple','clear'}:raise ValueError('every source-host/count-control requires actual published 0/1/2/clear observations')
        for name,count in [('zero',0),('one',1),('multiple',2),('clear',0)]:
            record=cases[name]
            if (not isinstance(record,dict) or record.get('origin')!='sigma-browser' or record.get('published') is not True
                    or record.get('hostElementId')!=authority['hostElementId'] or record.get('controlElementId')!=authority['controlElementId']
                    or record.get('documentId')!=document['workbookId'] or record.get('version')!=document['documentVersion']
                    or record.get('adminBypass') is not False or type(record.get('actualCount')) is not int or record['actualCount']!=count
                    or any(not isinstance(record.get(k),str) or not record[k].strip() or re.match(r'(?i)^(pending|todo|tbd|unknown)\b',record[k]) for k in ('evidenceId','memberId','identityEvidenceId'))):
                raise ValueError('actual published source-bound 0/1/2/clear observations and session identity required')
    result=copy.deepcopy(capture);elements={e['id']:e for e in document['contents']['elements']};touched=set()
    sentinel={'type':'unavailable','reason':'SDK_SELECTION_NAMESPACE_NO_GETTER'}
    for authority in fragment_bundle.get('selectionAuthorities',[]):
        eid=authority['hostElementId'];host=elements.get(eid,{})
        if _digest({k:v for k,v in host.items() if k!='actions'})!=authority['hostWithoutActionsHash']:raise ValueError('Selection source schema/assigned host changed')
        column=authority['sourceColumn'];formula='CountDistinct([Selection/'+column['name']+'])'
        if authority['formula']!=formula or column['elementId']!=eid or authority['trigger']!='on-select':raise ValueError('foreign Selection source/trigger/expression')
        actions=[a for a in host.get('actions',[]) if a['id']==authority['sequenceId']]
        if len(actions)!=1 or actions[0]['trigger']!='on-select':raise ValueError('exact public Selection event missing')
        if published and actions[0].get('state')!='enabled':raise ValueError('published Selection proof requires an enabled control-only probe')
        index=authority['effectIndex'];effects=actions[0]['effects']
        if not isinstance(index,int) or not 0<=index<len(effects):raise ValueError('Selection effect pointer stale')
        expected={'effect':'set-control-value','control':authority['controlId'],'value':{'type':'formula','formula':formula}}
        if effects[index]!=expected:raise ValueError('public Selection literal/control/effect differs')
        element=result['elements'][eid];sequences=[s for s in element['sequences'] if s['id']==authority['sequenceId']]
        if len(sequences)!=1 or sequences[0]['trigger']!='on-select' or index>=len(sequences[0]['blocks']):raise ValueError('actual SDK Selection event/sequence/block missing')
        if published and sequences[0]['disabled'] is not False:raise ValueError('published Selection proof requires actual enabled SDK event')
        block=sequences[0]['blocks'][index]
        if block['kind']!='FloatSetControlValueEffect' or block['fields'].get('controlId')!=authority['controlId'] or block['fields'].get('controlElementId')!=authority['controlElementId'] or block['fields'].get('value') not in (sentinel,expected['value']):
            raise ValueError('arbitrary opaque SDK value cannot become Selection authority')
        block['fields']['value']=copy.deepcopy(expected['value'])
        element.setdefault('publicSelectionAuthority' if published else 'publicSelectionConstruction',[]).append({'authority':copy.deepcopy(authority),'review':copy.deepcopy(review)})
        element.pop('restorationArtifact',None)  # Old observation hash is no longer current; never carry stale proof.
        element['semanticHash']=digest(configuration(element));touched.add(eid)
    if not touched:raise ValueError('no exact known Selection literals to qualify')
    validate_action_inventory(result,document)
    return result
