"""Source-bound Forecast Save-scenario completion proposals.

No function invokes Sigma, executes an action, or treats a local fixture as
published evidence. Save's Excel source appends before asking for a name; an
empty or whitespace-only InputBox result is a legitimate name.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import copy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from .native_actions import validate_native_action_plan
except ImportError:
    from native_actions import validate_native_action_plan


PHYSICAL_ID = re.compile(r"[0-9A-Fa-f]{32}\Z")
UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\.\d{1,6}(?:Z|\+00:00)?\Z")
TERMINAL = ("CONFIRMED", "ABANDONED")
BLANK_NAME_POLICY = {"version":1,"field":"Scenario Name",
                     "rawOmittedOrNullAs":"","controlNullAs":"",
                     "basis":"reviewed SaveScenario_Click InputBox has no blank/cancel guard"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or PHYSICAL_ID.fullmatch(value) is None:
        raise ValueError("actual 32-hex physical row ID required")
    return value


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("source-bound SHA256 required")
    return value


def _number(value):
    if type(value) not in (int, float, Decimal):
        raise ValueError("finite typed numeric growth required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("finite typed numeric growth required") from exc
    if not result.is_finite():
        raise ValueError("finite typed numeric growth required")
    return result


def _time(value):
    if not isinstance(value, str) or UTC_TIME.fullmatch(value) is None:
        raise ValueError("strict UTC timestamp with source precision required")
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("valid UTC timestamp required") from exc
    if parsed.tzinfo is not None and parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("UTC timestamp required")
    return parsed


def _name(value, definition):
    if value is None and definition["sourceSemantics"]["blankNamePolicy"] == BLANK_NAME_POLICY:
        return ""
    if isinstance(value,str):
        return value
    raise ValueError("reviewed nullable Scenario Name must be text or null")


def _audit_fields(fields):
    operations={"Workflow":"text","Scenario Name":"text","Context":"text",
                "Source Hash":"text","Plan Hash":"text","Source Procedure Hash":"text",
                "State":"text","Created At":"datetime"}
    saved={"Operation ID":"text","Scenario Name":"text","Saved At":"datetime",
           "Source Hash":"text","Plan Hash":"text","Source Procedure Hash":"text"}
    for field in fields:
        label=field["savedField"].removesuffix(" Growth")
        operations.update({label+" Input Row ID":"text",field["beforeField"]:"number",
                           field["targetField"]:"number"})
        saved[field["savedField"]]="number"
    if len(operations)!=14 or len(saved)!=8:
        raise ValueError("reviewed 14/8-field Save audit schema required")
    return {"operations":operations,"saved":saved}


def _audit_contract(mapping, fields, source_hash, plan_hash, target):
    if (not isinstance(mapping,dict) or mapping.get("version")!=1
            or mapping.get("sourceHash")!=source_hash or mapping.get("planHash")!=plan_hash
            or mapping.get("target")!=target
            or mapping.get("mappingHash")!=digest({k:v for k,v in mapping.items() if k!="mappingHash"})):
        raise ValueError("reviewed hash-bound Save audit schema mapping required")
    required=_audit_fields(fields)
    result={}
    for role,types in required.items():
        entry=mapping.get("tables",{}).get(role)
        if not isinstance(entry,dict) or not isinstance(entry.get("columns"),list):
            raise ValueError("complete reviewed Save audit schema required: "+role)
        columns=entry["columns"]
        native=[c for c in columns if c.get("class")=="InputTableIDColumn" and c.get("kind")=="row_id"]
        names=[c.get("name") for c in columns]
        ids=[c.get("id") for c in columns]
        if (len(native)!=1 or native[0].get("name")!="ID"
                or native[0].get("id")!=entry.get("rowIdColumnId")
                or not isinstance(entry.get("elementId"),str) or not entry["elementId"]
                or len(set(names))!=len(names) or len(set(ids))!=len(ids)
                or not set(types)<=set(names)):
            raise ValueError("complete unique reviewed Save audit columns required: "+role)
        approved={}
        for name,typ in types.items():
            col=next(c for c in columns if c.get("name")==name)
            if (not isinstance(col.get("id"),str) or not col["id"]
                    or col.get("class")!="LiteralEditableColumn" or col.get("type")!=typ):
                raise ValueError("reviewed Save audit column ID/class/type required: "+name)
            approved[name]={"id":col["id"],"type":typ,"class":"LiteralEditableColumn"}
        result[role]={"elementId":entry["elementId"],"rowIdColumnId":native[0]["id"],
                      "columns":approved}
    return result


def build_save_definition(manifest, action_binding, audit_mapping):
    """Derive the exact Save contract from approved native action mapping/IDs.

    The binding is the assigned native-action target produced from complete
    primary input readback. The source/plan/procedure hashes are never caller
    literals. A changed source module or logical plan fails validation.
    """
    validate_native_action_plan(manifest)
    workflow = manifest["planProjection"]["nativeActionArchitecture"]["workflows"].get("saveScenario")
    if not isinstance(workflow, dict) or workflow.get("status") != "STAGED_CANDIDATE":
        raise ValueError("approved Save-scenario mapping required")
    modules=manifest["planProjection"]["nativeActionArchitecture"].get("sourceModules",[])
    procedures=[proc for module in modules for proc in module.get("procedures",[])
                if proc.get("procedureId")==workflow.get("procedureId")]
    if len(procedures)!=1 or procedures[0].get("procedureSha256")!=workflow.get("procedureSha256"):
        raise ValueError("one exact reviewed Save procedure required")
    proc=procedures[0]
    body=proc.get("sourceBody","")
    statements=[r'Set\s+newRow\s*=\s*t\.ListRows\.Add',
                r'newRow\.Range\(1,\s*1\)\.Value\s*=\s*InputBox\("Scenario name\?"\)',
                r'newRow\.Range\(1,\s*2\)\.Value\s*=\s*Sheets\("Assumptions"\)\.Range\("B5"\)\.Value',
                r'newRow\.Range\(1,\s*3\)\.Value\s*=\s*Sheets\("Assumptions"\)\.Range\("B6"\)\.Value']
    positions=[re.search(pattern,body,re.IGNORECASE) for pattern in statements]
    if (any(match is None for match in positions)
            or [match.start() for match in positions]!=sorted(match.start() for match in positions)
            or proc.get("guards") or re.search(r'\b(?:Trim|If|Exit\s+Sub)\b',body,re.IGNORECASE)):
        raise ValueError("reviewed append-before-InputBox Save semantics changed")
    decision = workflow["decision"]
    if (not isinstance(action_binding, dict) or action_binding.get("sourceHash") != manifest["sourceHash"]
            or action_binding.get("planHash") != manifest["planHash"]
            or action_binding.get("bindingHash") != digest({k:v for k,v in action_binding.items() if k != "bindingHash"})):
        raise ValueError("actual hash-bound native action binding required")
    if (action_binding.get("target")!=manifest.get("target")
            or not isinstance(action_binding["target"],dict)
            or not isinstance(action_binding["target"].get("documentId"),str)
            or not action_binding["target"]["documentId"].strip()
            or type(action_binding["target"].get("version")) is not int
            or action_binding["target"]["version"]<1):
        raise ValueError("reviewed binding and manifest authoring target/document must match")
    _hash(action_binding.get("contentsHash"))
    assumptions = sorted(decision["assumptions"], key=lambda item: item["sourceCell"])
    if [item["sourceCell"] for item in assumptions] != ["Assumptions!B5", "Assumptions!B6"]:
        raise ValueError("reviewed B5/B6 Save mapping required")
    if len({item["feature"] for item in assumptions}) != 1:
        raise ValueError("Save source must use one reviewed primary input")
    feature = assumptions[0]["feature"]
    bound = action_binding.get("tables", {}).get(feature)
    if not isinstance(bound, dict):
        raise ValueError("reviewed primary input binding required")
    primary = bound.get("target", {})
    identities = bound.get("identities")
    if (not isinstance(identities, list) or not identities
            or not isinstance(primary.get("elementId"), str)
            or not isinstance(primary.get("pageId"), str)
            or not isinstance(primary.get("columnIds"), dict)
            or not isinstance(bound.get("systemColumn"), dict)):
        raise ValueError("complete assigned primary identity binding required")
    row_id_column = bound["systemColumn"].get("id")
    if not isinstance(row_id_column, str) or not row_id_column:
        raise ValueError("assigned primary ID column required")
    expected_ids = []
    for identity in identities:
        expected_ids.append(_id(identity.get("rowId")))
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("duplicate primary physical identity")
    fields = []
    for item in assumptions:
        matches = [identity for identity in identities if identity.get("key", {}).get(item["keyColumn"]) == item["key"]]
        if len(matches) != 1:
            raise ValueError("source assumption identity missing or ambiguous")
        if item["valueColumn"] not in primary["columnIds"] or item["keyColumn"] not in primary["columnIds"]:
            raise ValueError("reviewed source columns are not bound")
        label = item["key"].removesuffix(" Revenue")
        if not label or not isinstance(label, str):
            raise ValueError("reviewed assumption label required")
        fields.append({"sourceCell": item["sourceCell"], "feature":feature,
                       "keyColumn":item["keyColumn"], "key":item["key"],
                       "valueColumn":item["valueColumn"], "rowId":matches[0]["rowId"],
                       "beforeField":"Before "+label+" Growth",
                       "targetField":"Target "+label+" Growth",
                       "savedField":label+" Growth"})
    if len({name for field in fields for name in (field["beforeField"],field["targetField"],field["savedField"])}) != 6:
        raise ValueError("distinct reviewed growth fields required")
    audit=_audit_contract(audit_mapping,fields,manifest["sourceHash"],manifest["planHash"],
                          action_binding["target"])
    result = {"version":1,"workflow":"saveScenario","context":decision["page"],
              "sourceHash":_hash(manifest["sourceHash"]),"planHash":_hash(manifest["planHash"]),
              "procedureHash":_hash(workflow["procedureSha256"]),"decisionId":decision["decisionId"],
              "sourceSemantics":{"appendBeforeNamePrompt":True,"allowBlankName":True,"allowWhitespaceName":True,
                                 "growthSources":["Assumptions!B5","Assumptions!B6"],
                                 "blankNamePolicy":copy.deepcopy(BLANK_NAME_POLICY)},
              "authoringTarget":{"documentId":action_binding["target"]["documentId"],
                                 "version":action_binding["target"]["version"],
                                 "contentsHash":action_binding["contentsHash"]},
              "primary":{"elementId":primary["elementId"],"pageId":primary["pageId"],
                         "rowIdColumnId":row_id_column,"expectedRowIds":sorted(expected_ids),
                         "columnIds":copy.deepcopy(primary["columnIds"]),
                         "identityReadbackHash":bound["readbackHash"]},
              "fields":fields,"audit":audit,"auditMappingHash":audit_mapping["mappingHash"],
              "bindingHash":action_binding["bindingHash"],
              "productionStatus":"BLOCKED"}
    result["definitionHash"] = digest(result)
    return result


def _definition(definition):
    if (not isinstance(definition, dict) or definition.get("version") != 1
            or definition.get("productionStatus") != "BLOCKED"
            or definition.get("definitionHash") != digest({k:v for k,v in definition.items() if k != "definitionHash"})
            or definition.get("workflow") != "saveScenario"
            or [field.get("sourceCell") for field in definition.get("fields", [])] != ["Assumptions!B5", "Assumptions!B6"]):
        raise ValueError("exact source-bound Save definition required")
    for name in ("sourceHash", "planHash", "procedureHash"):
        _hash(definition[name])
    if (definition.get("sourceSemantics")!={"appendBeforeNamePrompt":True,"allowBlankName":True,
            "allowWhitespaceName":True,"growthSources":["Assumptions!B5","Assumptions!B6"],
            "blankNamePolicy":BLANK_NAME_POLICY}):
        raise ValueError("reviewed versioned blank-name policy required")
    authoring=definition.get("authoringTarget")
    if (not isinstance(authoring,dict) or not isinstance(authoring.get("documentId"),str)
            or not authoring["documentId"].strip() or type(authoring.get("version")) is not int
            or authoring["version"]<1):
        raise ValueError("source-bound authoring document/version required")
    _hash(authoring.get("contentsHash"))
    ids = definition["primary"]["expectedRowIds"]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("complete primary identity contract required")
    for row_id in ids:
        _id(row_id)
    expected=_audit_fields(definition["fields"])
    audit=definition.get("audit")
    if not isinstance(audit,dict) or set(audit)!=set(expected):
        raise ValueError("reviewed Save audit schema required in definition")
    for role,types in expected.items():
        entry=audit[role]
        if (not isinstance(entry,dict) or not isinstance(entry.get("elementId"),str)
                or not isinstance(entry.get("rowIdColumnId"),str)
                or not isinstance(entry.get("columns"),dict)
                or set(entry["columns"])!=set(types)):
            raise ValueError("complete reviewed Save audit schema required")
        ids=[entry["rowIdColumnId"]]+[c.get("id") for c in entry["columns"].values()]
        if any(not isinstance(cid,str) or not cid for cid in ids) or len(set(ids))!=len(ids):
            raise ValueError("unique reviewed Save audit column IDs required")
        for name,typ in types.items():
            if entry["columns"][name].get("type")!=typ or entry["columns"][name].get("class")!="LiteralEditableColumn":
                raise ValueError("reviewed Save audit column type/class required")
    _hash(definition.get("auditMappingHash"))


def _target(definition,target):
    authoring=definition["authoringTarget"]
    if (not isinstance(target,dict) or target.get("documentId")!=authoring["documentId"]
            or type(target.get("version")) is not int or target["version"]<authoring["version"]):
        raise ValueError("actual target must be same reviewed document at authoring or later version")


def _evidence_file(path):
    source = Path(path)
    if not source.is_absolute() or not source.is_file():
        raise ValueError("retained absolute actual evidence file required")
    raw = source.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("UTF-8 JSON evidence required") from exc
    return value, {"path":str(source),"sha256":hashlib.sha256(raw).hexdigest()}


def _source_bracket(target, before, after):
    if (not isinstance(before, dict) or before != after
            or before.get("workbookId") != target["documentId"]
            or before.get("documentVersion") != target["version"]
            or not isinstance(before.get("contents"), dict)):
        raise ValueError("identical same-version saved source GET bracket required")
    return digest(before["contents"])


def adapt_save_rest_capture(definition, *, role, target, bindings_path, request_path, job_path,
                            download_request_path, request_provenance_path, rows_path,
                            timezone_path, source_before_path, source_after_path):
    """Normalize a retained, actual hidden-table REST JSON export.

    Raw requests/results and their invocation provenance remain explicit files.
    This checks file consistency; the controller must review actual origin.
    """
    _definition(definition)
    _target(definition,target)
    if role not in ("operations", "saved"):
        raise ValueError("hidden Save role required")
    paths={"bindings":bindings_path,"request":request_path,"job":job_path,
           "downloadRequest":download_request_path,"requestProvenance":request_provenance_path,
           "rows":rows_path,"timezone":timezone_path,"sourceBefore":source_before_path,
           "sourceAfter":source_after_path}
    data={};files={}
    for name,path in paths.items():
        data[name],files[name]=_evidence_file(path)
    source_hash=_source_bracket(target,data["sourceBefore"],data["sourceAfter"])
    binding=data["bindings"].get(role) if isinstance(data["bindings"],dict) else None
    columns=binding.get("columns") if isinstance(binding,dict) else None
    source=next((item for item in data["sourceBefore"]["contents"].get("elements",[])
                 if item.get("id")==target[role+"ElementId"]),None)
    if (not isinstance(columns,list) or not columns or binding.get("elementId")!=target[role+"ElementId"]
            or not isinstance(source,dict) or source.get("kind")!="input-table"):
        raise ValueError("assigned hidden input schema/source required")
    approved=definition["audit"][role]
    if (binding["elementId"]!=approved["elementId"]
            or target[role+"RowIdColumnId"]!=approved["rowIdColumnId"]):
        raise ValueError("actual audit table differs from reviewed mapping")
    native=[c for c in columns if c.get("class")=="InputTableIDColumn" and c.get("kind")=="row_id"]
    names={c.get("name") for c in columns}
    public_columns=source.get("columns",[])
    if (not isinstance(public_columns,list) or len({c.get("id") for c in public_columns})!=len(public_columns)
            or len({c.get("name") for c in public_columns})!=len(public_columns)):
        raise ValueError("unique declared public audit schema columns required")
    public={c.get("id"):c for c in public_columns}
    if (len(native)!=1 or native[0].get("id")!=target[role+"RowIdColumnId"]
            or native[0].get("name")!="ID" or len(names)!=len(columns)
            or set(public)!={c.get("id") for c in columns if c not in native}|{"ID"}):
        raise ValueError("exact assigned native ID/full schema required")
    for col in columns:
        pub=public.get("ID" if col in native else col["id"],{})
        if any(pub.get(k)!=col.get(k) for k in ("name","type") if k in pub):
            raise ValueError("assigned public/SDK schema differs")
    for field,spec in approved["columns"].items():
        matches=[col for col in columns if col.get("name")==field]
        if len(matches)!=1 or any(matches[0].get(k)!=v for k,v in spec.items()):
            raise ValueError("required reviewed audit column differs: "+field)
        pub=public.get(spec["id"])
        if not isinstance(pub,dict) or pub.get("name")!=field or pub.get("type")!=spec["type"]:
            raise ValueError("required public audit schema differs: "+field)
    request=data["request"];job=data["job"];download=data["downloadRequest"]
    expected_path="/v2/workbooks/"+target["documentId"]+"/export"
    if (not isinstance(request,dict) or set(request)!={"method","path","body"}
            or request.get("method")!="POST" or request.get("path")!=expected_path
            or not isinstance(request.get("body"),dict)
            or set(request["body"])!={"elementId","format","rowLimit"}
            or request["body"].get("elementId")!=binding["elementId"]
            or request["body"].get("format")!={"type":"json"}
            or type(request["body"].get("rowLimit")) is not int or request["body"]["rowLimit"]<1):
        raise ValueError("actual exact unfiltered JSON export request required")
    query_id=job.get("queryId") if isinstance(job,dict) else None
    provenance=data["requestProvenance"]
    entry=provenance.get(role) if isinstance(provenance,dict) else None
    if (not isinstance(query_id,str) or not query_id.strip()
            or type(job.get("jobComplete")) is not bool
            or download!={"method":"GET","path":"/v2/query/"+query_id+"/download"}
            or not isinstance(entry,dict) or entry.get("queryId")!=query_id
            or any(not isinstance(entry.get(k),str) or not entry[k].strip()
                   for k in ("actualExportInvocation","actualDownloadInvocation"))
            or not isinstance(provenance.get("qualification"),str)
            or not provenance["qualification"].strip()):
        raise ValueError("matching job/download/actual invocation provenance required")
    if data["timezone"]!={"timezone":"UTC"}:
        raise ValueError("actual UTC organization setting required")
    raw_rows=data["rows"]
    if not isinstance(raw_rows,list) or len(raw_rows)>=request["body"]["rowLimit"]:
        raise ValueError("complete below-limit JSON export rows required")
    payload={"Operation ID","Scenario Name","Saved At","Source Hash","Plan Hash",
             "Source Procedure Hash"}|{field["savedField"] for field in definition["fields"]}
    frozen={"Workflow","Scenario Name","Context","Source Hash","Plan Hash",
            "Source Procedure Hash","State","Created At"}|{key for field in definition["fields"]
              for key in (field["beforeField"],field["targetField"],
                          field["savedField"].removesuffix(" Growth")+" Input Row ID")}
    required={"ID"}|((payload if role=="saved" else frozen)-{"Scenario Name"})
    normalized=[];seen=set();name_normalization=[]
    for row in raw_rows:
        if (not isinstance(row,dict) or not required<=set(row) or not set(row)<=names
                or role=="saved" and set(row) not in (required,required|{"Scenario Name"})):
            raise ValueError("missing/foreign raw export fields")
        row_id=_id(row["ID"])
        if row_id in seen:
            raise ValueError("duplicate exported physical ID")
        seen.add(row_id)
        timestamp="Created At" if role=="operations" else "Saved At"
        _time(row[timestamp])
        if not isinstance(row[timestamp],str) or "T" in row[timestamp] or row[timestamp].endswith(("Z","+00:00")):
            raise ValueError("lossless raw UTC-naive export timestamp required")
        result={k:v for k,v in row.items() if k!="ID"}
        result["nativeRowId"]=row_id
        result[timestamp]=row[timestamp].replace(" ","T")+"+00:00"
        result["Scenario Name"]=_name(row.get("Scenario Name"),definition)
        name_normalization.append({"nativeRowId":row_id,"rawForm":
            "omitted" if "Scenario Name" not in row else "null" if row["Scenario Name"] is None else "text"})
        normalized.append(result)
    evidence={"files":files,"queryId":query_id,"sourceContentsHash":source_hash,
              "request":{"elementId":binding["elementId"],"rowLimit":request["body"]["rowLimit"]},
              "actualExportInvocation":entry["actualExportInvocation"],
              "actualDownloadInvocation":entry["actualDownloadInvocation"],
              "qualification":provenance["qualification"],
              "blankNamePolicy":copy.deepcopy(BLANK_NAME_POLICY),
              "nameNormalization":name_normalization}
    return {"origin":"sigma-rest-json-export","documentId":target["documentId"],
            "version":target["version"],"sourceHash":definition["sourceHash"],
            "planHash":definition["planHash"],"complete":True,"rowCount":len(normalized),
            "evidenceId":digest(evidence),"executionId":query_id,
            "elementId":binding["elementId"],"rowIdColumnId":native[0]["id"],
            "rows":normalized,"restEvidence":evidence}


def adapt_save_primary_capture(definition, *, target, binding_path, query_path,
                               source_before_path, source_after_path):
    """Normalize one retained complete Sigma workbook query of primary input."""
    _definition(definition)
    _target(definition,target)
    paths={"binding":binding_path,"query":query_path,
           "sourceBefore":source_before_path,"sourceAfter":source_after_path}
    data={};files={}
    for name,path in paths.items():
        data[name],files[name]=_evidence_file(path)
    source_hash=_source_bracket(target,data["sourceBefore"],data["sourceAfter"])
    binding=data["binding"]
    if (not isinstance(binding,dict) or binding.get("elementId")!=target["primaryElementId"]
            or binding.get("rowIdColumnId")!=target["primaryRowIdColumnId"]
            or not isinstance(binding.get("columns"),list)):
        raise ValueError("assigned primary Sigma query binding required")
    source=next((item for item in data["sourceBefore"]["contents"].get("elements",[])
                 if item.get("id")==target["primaryElementId"]),None)
    if not isinstance(source,dict) or source.get("kind")!="input-table":
        raise ValueError("primary input missing from saved source")
    columns=binding["columns"]
    if (not columns or len({c.get("id") for c in columns})!=len(columns)
            or {c.get("id") for c in columns}!={c.get("id") for c in source.get("columns",[])}) :
        raise ValueError("complete assigned primary query schema required")
    public={c["id"]:c for c in source["columns"]}
    if any(any(public[col["id"]].get(key)!=col.get(key) for key in ("name","type","formula")
               if key in public[col["id"]]) for col in columns):
        raise ValueError("assigned primary query/public schema differs")
    names={c["id"]:c["name"] for c in columns}
    if len(set(names.values()))!=len(names) or names.get(target["primaryRowIdColumnId"])!="ID":
        raise ValueError("unique primary labels and actual ID required")
    approved=definition["primary"]["columnIds"]
    if (not isinstance(approved,dict) or not approved
            or any(not isinstance(name,str) or not isinstance(cid,str)
                   or names.get(cid)!=name for name,cid in approved.items())):
        raise ValueError("primary query differs from definition reviewed column IDs")
    query=data["query"]
    query_ids=[c["id"] for c in columns]
    sql='SELECT '+', '.join('"'+cid+'"' for cid in query_ids)+' FROM "workbook"."'+target["primaryElementId"]+'"'
    request={"type":"workbook","workbookId":target["documentId"],"sql":sql}
    result=query.get("result") if isinstance(query,dict) else None
    content=result.get("structuredContent") if isinstance(result,dict) else None
    try:
        textual=json.loads(result["content"][0]["text"])
    except (TypeError,KeyError,IndexError,ValueError) as exc:
        raise ValueError("retained Sigma query result required") from exc
    if (not isinstance(query,dict) or query.get("request")!=request or not isinstance(query.get("executionId"),str)
            or not query["executionId"] or not isinstance(query.get("actualInvocation"),str)
            or not query["actualInvocation"].strip() or not isinstance(content,dict)
            or content!=textual or content.get("columns")!=query_ids
            or not isinstance(content.get("rows"),list)):
        raise ValueError("exact actual complete Sigma query request/result required")
    rows=[]
    for raw in content["rows"]:
        if not isinstance(raw,list) or len(raw)!=len(query_ids):
            raise ValueError("primary Sigma query row width differs")
        row={names[cid]:value for cid,value in zip(query_ids,raw)}
        row["nativeRowId"]=_id(row.pop("ID"))
        rows.append(row)
    if len(rows)!=len(definition["primary"]["expectedRowIds"]):
        raise ValueError("complete reviewed primary row count required")
    evidence={"files":files,"executionId":query["executionId"],
              "actualInvocation":query["actualInvocation"],"sourceContentsHash":source_hash,
              "query":request}
    return {"origin":"sigma-query","documentId":target["documentId"],
            "version":target["version"],"sourceHash":definition["sourceHash"],
            "planHash":definition["planHash"],"complete":True,"rowCount":len(rows),
            "evidenceId":digest(evidence),"executionId":query["executionId"],
            "elementId":target["primaryElementId"],"rowIdColumnId":target["primaryRowIdColumnId"],
            "rows":rows,"queryEvidence":evidence}


def _capture(definition, role, capture, target):
    if not isinstance(capture, dict):
        raise ValueError("actual bound capture required: "+role)
    expected_origin = "sigma-query" if role == "primary" else "sigma-rest-json-export"
    if (capture.get("origin") != expected_origin or capture.get("complete") is not True
            or capture.get("sourceHash") != definition["sourceHash"]
            or capture.get("planHash") != definition["planHash"]
            or any(capture.get(k) != target.get(k) for k in ("documentId", "version"))
            or capture.get("elementId") != target.get(role+"ElementId")
            or capture.get("rowIdColumnId") != target.get(role+"RowIdColumnId")
            or not isinstance(capture.get("executionId"), str) or not capture["executionId"]
            or not isinstance(capture.get("evidenceId"), str) or not capture["evidenceId"]
            or type(capture.get("rowCount")) is not int
            or not isinstance(capture.get("rows"), list)
            or capture["rowCount"] != len(capture["rows"])):
        raise ValueError("fresh complete actual source/plan/target-bound "+role+" capture required")
    if role != "primary":
        evidence = capture.get("restEvidence")
        if (not isinstance(evidence, dict) or evidence.get("queryId") != capture["executionId"]
                or not isinstance(evidence.get("actualExportInvocation"), str)
                or not evidence["actualExportInvocation"].strip()
                or not isinstance(evidence.get("actualDownloadInvocation"), str)
                or not evidence["actualDownloadInvocation"].strip()
                or not isinstance(evidence.get("request"), dict)
                or evidence["request"].get("rowLimit", 0) <= len(capture["rows"])):
            raise ValueError("actual REST request/job/download provenance required")
        files=evidence.get("files")
        if not isinstance(files,dict) or set(files)!={"bindings","request","job","downloadRequest",
                "requestProvenance","rows","timezone","sourceBefore","sourceAfter"}:
            raise ValueError("retained complete REST provenance files required")
        try:
            rebuilt=adapt_save_rest_capture(definition,role=role,target=target,
                **{name+"_path":files[key]["path"] for name,key in (
                    ("bindings","bindings"),("request","request"),("job","job"),
                    ("download_request","downloadRequest"),("request_provenance","requestProvenance"),
                    ("rows","rows"),("timezone","timezone"),("source_before","sourceBefore"),
                    ("source_after","sourceAfter"))})
        except (KeyError,TypeError,FileNotFoundError) as exc:
            raise ValueError("invalid retained REST provenance") from exc
        if capture!=rebuilt:
            raise ValueError("REST capture differs from retained actual evidence")
    else:
        evidence = capture.get("queryEvidence")
        if not isinstance(evidence, dict) or evidence.get("executionId") != capture["executionId"]:
            raise ValueError("actual primary Sigma query provenance required")
        files=evidence.get("files")
        if not isinstance(files,dict) or set(files)!={"binding","query","sourceBefore","sourceAfter"}:
            raise ValueError("retained complete Sigma query provenance files required")
        try:
            rebuilt=adapt_save_primary_capture(definition,target=target,
                **{name+"_path":files[key]["path"] for name,key in
                   (("binding","binding"),("query","query"),
                    ("source_before","sourceBefore"),("source_after","sourceAfter"))})
        except (KeyError,TypeError,FileNotFoundError) as exc:
            raise ValueError("invalid retained query provenance") from exc
        if capture!=rebuilt:
            raise ValueError("primary capture differs from retained actual query")
    ids=[]
    for row in capture["rows"]:
        if not isinstance(row, dict):
            raise ValueError("complete typed readback row required")
        ids.append(_id(row.get("nativeRowId")))
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate physical IDs in capture")
    return capture["rows"]


def plan_save_completion(definition, operation_id, operations, saved, primary, target, *, name_control, control_value):
    """Propose Mark/Clear only after exact complete actual row readback.

    Every capture must carry its true origin and request/query provenance.
    The controller must independently verify that evidence and the same-view
    controls before submitting a disabled native candidate.
    """
    _definition(definition)
    _target(definition,target)
    _id(operation_id)
    observed_name=name_control
    name_control=_name(name_control,definition)
    if not isinstance(control_value, str):
        raise ValueError("typed exact operation control required")
    required = ("documentId", "operationsElementId", "operationsRowIdColumnId",
                "savedElementId", "savedRowIdColumnId", "primaryElementId", "primaryRowIdColumnId",
                "controlId", "nameControlId")
    if (not isinstance(target, dict) or any(not isinstance(target.get(k), str) or not target[k].strip() for k in required)
            or type(target.get("version")) is not int or target["version"] < 1
            or target["primaryElementId"] != definition["primary"]["elementId"]
            or target["primaryRowIdColumnId"] != definition["primary"]["rowIdColumnId"]):
        raise ValueError("exact assigned document/version/element/native ID/control target required")
    op_rows = _capture(definition, "operations", operations, target)
    saved_rows = _capture(definition, "saved", saved, target)
    primary_rows = _capture(definition, "primary", primary, target)
    physical_ids=[row["nativeRowId"] for row in op_rows+saved_rows+primary_rows]
    if len(physical_ids)!=len(set(physical_ids)):
        raise ValueError("distinct physical IDs required across Operations, Saved, and primary")
    if operations["executionId"] == saved["executionId"]:
        raise ValueError("distinct Operations and Saved export jobs required")
    if len({operations["executionId"],saved["executionId"],primary["executionId"]})!=3:
        raise ValueError("all three actual readback executions must be distinct")
    if (operations["restEvidence"]["sourceContentsHash"]!=saved["restEvidence"]["sourceContentsHash"]
            or operations["restEvidence"]["sourceContentsHash"]!=primary["queryEvidence"]["sourceContentsHash"]):
        raise ValueError("all three captures require one bracketed saved source")
    bracket_hash=operations["restEvidence"]["sourceContentsHash"]
    if (target["version"]==definition["authoringTarget"]["version"]
            and bracket_hash!=definition["authoringTarget"]["contentsHash"]):
        raise ValueError("same-version source differs from reviewed authoring binding")
    matching = [row for row in op_rows if row["nativeRowId"] == operation_id]
    if len(matching) != 1:
        raise ValueError("exactly one owned operation physical row required")
    op = matching[0]
    base = {"Workflow":definition["workflow"],"Context":definition["context"],
            "Source Hash":definition["sourceHash"],"Plan Hash":definition["planHash"],
            "Source Procedure Hash":definition["procedureHash"]}
    fields = definition["fields"]
    required_op = {"nativeRowId","Workflow","Scenario Name","Context",
                   "Source Hash","Plan Hash","Source Procedure Hash","State","Created At"}
    required_op |= {key for field in fields for key in (field["beforeField"],field["targetField"])}
    required_op |= {field["savedField"].removesuffix(" Growth")+" Input Row ID" for field in fields}
    if not required_op <= set(op) or any(op[k] != value for k,value in base.items()):
        raise ValueError("complete source/plan/procedure-bound frozen operation required")
    if op["Scenario Name"] != name_control or op["State"] not in ("PREPARED", *TERMINAL):
        raise ValueError("exact name/state frozen operation required")
    _time(op["Created At"])
    for row in op_rows:
        if (row["nativeRowId"] != operation_id and row.get("Workflow") == definition["workflow"]
                and row.get("Context") == definition["context"] and row.get("Source Hash") == definition["sourceHash"]
                and row.get("Plan Hash") == definition["planHash"]
                and row.get("Source Procedure Hash") == definition["procedureHash"]
                and row.get("State") == "PREPARED"):
            raise ValueError("competing prepared Save intent")
    by_id = {row["nativeRowId"]:row for row in primary_rows}
    if set(by_id) != set(definition["primary"]["expectedRowIds"]):
        raise ValueError("complete original primary physical row coverage required")
    for field in fields:
        row = by_id[field["rowId"]]
        label = field["savedField"].removesuffix(" Growth")
        if (op[label+" Input Row ID"] != field["rowId"]
                or row.get(field["keyColumn"]) != field["key"] or row.get("Method") != "growth"):
            raise ValueError("reviewed live primary identity/method changed")
        before = _number(op[field["beforeField"]]); target_growth = _number(op[field["targetField"]])
        if before != target_growth or before != _number(row.get(field["valueColumn"])):
            raise ValueError("frozen target/before or current source growth mismatch")
    matching_saved = [row for row in saved_rows if row.get("Operation ID") == operation_id]
    if len(matching_saved) != 1:
        raise ValueError("exactly one persisted Saved row for operation required")
    saved_row = matching_saved[0]
    required_saved = {"nativeRowId","Operation ID","Scenario Name","Saved At","Source Hash",
                      "Plan Hash","Source Procedure Hash"}|{field["savedField"] for field in fields}
    if set(saved_row) != required_saved:
        raise ValueError("exact eight-field Saved payload plus physical ID required")
    expected = {"Operation ID":operation_id,"Scenario Name":name_control,"Saved At":op["Created At"],
                "Source Hash":definition["sourceHash"],"Plan Hash":definition["planHash"],
                "Source Procedure Hash":definition["procedureHash"]}
    if any(saved_row[k] != value for k,value in expected.items()):
        raise ValueError("Saved row differs from frozen operation/provenance/time")
    _time(saved_row["Saved At"])
    for field in fields:
        if _number(saved_row[field["savedField"]]) != _number(op[field["beforeField"]]):
            raise ValueError("Saved numeric growth differs from frozen source")
    if op["State"] == "PREPARED":
        if control_value != operation_id:
            raise ValueError("prepared operation must match same-view control")
        next_action = "MARK_CONFIRMED"
    elif control_value == operation_id:
        next_action = "CLEAR_CONTROL"
    elif control_value == "":
        next_action = "NONE"
    else:
        raise ValueError("terminal operation control belongs to another intent")
    result = {"status":"COMPONENT_COMPLETION_PLAN_ONLY","productionStatus":"BLOCKED",
              "nextAction":next_action,"operationId":operation_id,"savedPhysicalRowId":saved_row["nativeRowId"],
              "observedOperationState":op["State"],"controlValue":control_value,"nameControl":name_control,
              "nameControlObserved":observed_name,"sourceContentsHash":bracket_hash,
              "frozenCreatedAt":op["Created At"],"definitionHash":definition["definitionHash"],
              "sourceHash":definition["sourceHash"],"planHash":definition["planHash"],
              "procedureHash":definition["procedureHash"],"target":copy.deepcopy(target),
              "operationHash":digest(op),"savedHash":digest(saved_row),"primaryHash":digest(primary_rows),
              "operationReadbackHash":digest(operations),"savedReadbackHash":digest(saved),
              "primaryReadbackHash":digest(primary)}
    result["completionPlanHash"] = digest(result)
    return result


def _and(parts):
    if not parts:
        raise ValueError("guard cannot be empty")
    if len(parts) == 1:
        return parts[0]
    mid = len(parts)//2
    return "and_("+_and(parts[:mid])+", "+_and(parts[mid:])+")"


def render_save_completion_candidate(definition, current, bindings, completion_plan, *,
                                     operations, saved, primary, phase):
    """Render a disabled SDK construction program for one Mark or Clear step.

    The caller must submit only after a fresh exact source precondition check
    and independent review of the actual capture origins. The constructor
    never clicks or enables the sequence; runtime outcome needs new readback.
    """
    _definition(definition)
    if phase not in ("mark", "clear") or not isinstance(completion_plan, dict):
        raise ValueError("explicit Save completion phase/plan required")
    target = completion_plan.get("target")
    expected = plan_save_completion(definition, completion_plan.get("operationId"),
        operations, saved, primary, target, name_control=completion_plan.get("nameControlObserved"),
        control_value=completion_plan.get("controlValue"))
    if expected != completion_plan or completion_plan["nextAction"] != ("MARK_CONFIRMED" if phase == "mark" else "CLEAR_CONTROL"):
        raise ValueError("fresh exact complete Save completion plan required")
    if (not isinstance(current, dict) or current.get("workbookId") != target["documentId"]
            or current.get("documentVersion") != target["version"]
            or not isinstance(current.get("contents"), dict)
            or not isinstance(bindings, dict) or set(bindings) != {"primary", "operations", "saved"}):
        raise ValueError("exact current document/version and three assigned SDK bindings required")
    contents = current["contents"]
    if digest(contents)!=completion_plan["sourceContentsHash"]:
        raise ValueError("current source contents differ from bracketed completion captures")
    elements = {item["id"]:item for item in contents.get("elements", [])}
    pages = {item["id"]:item for item in contents.get("pages", [])}
    layout = ET.fromstring("<Layout>"+re.sub(r"<\?xml[^?]*\?>", "", contents["layout"])+"</Layout>")
    owners = {}
    for page in layout:
        for node in page.iter("Element"):
            eid = node.get("elementId") or node.get("id")
            if eid in owners:
                raise ValueError("ambiguous assigned layout")
            owners[eid] = page.get("id")
    required_ops = {"Workflow":"text","Scenario Name":"text","Context":"text",
        "Source Hash":"text","Plan Hash":"text","Source Procedure Hash":"text",
        "State":"text","Created At":"datetime"}
    required_saved = {"Operation ID":"text","Scenario Name":"text","Saved At":"datetime",
        "Source Hash":"text","Plan Hash":"text","Source Procedure Hash":"text"}
    for field in definition["fields"]:
        label = field["savedField"].removesuffix(" Growth")
        required_ops.update({label+" Input Row ID":"text",field["beforeField"]:"number",
                             field["targetField"]:"number"})
        required_saved[field["savedField"]] = "number"
    required = {"operations":required_ops,"saved":required_saved,
                "primary":{"ID":None,"Method":"text",**{field["keyColumn"]:"text" for field in definition["fields"]},
                           **{field["valueColumn"]:"number" for field in definition["fields"]}}}
    lines = ["# DISABLED Forecast Save completion candidate; productionStatus=BLOCKED",
        "# Controller must verify fresh source and actual capture provenance before submit.",
        "from sigma.page import Page", "from sigma.framing import GridFramed",
        "from sigma.inputTable import InputTable, LiteralEditableColumn, SingleSelectEditableColumn, InputTableIDColumn",
        "from sigma.column import FormulaColumn", "from sigma.controlHandle import TextControl",
        "from sigma.action.inputTableEffects import update_rows",
        "from sigma.action.setControlValueEffect import set_control_value",
        "from sigma.formula import const_text, const_num, const_date, eq, neq, and_, or_, is_not_null, count_if, coalesce, as_num, as_text, lookup"]
    handles = {}
    for role in ("primary", "operations", "saved"):
        b = bindings[role]
        e = elements.get(b.get("elementId"), {})
        schema = b.get("columns")
        if (not isinstance(schema, list) or not schema or e.get("kind") != "input-table"
                or e.get("name") != b.get("name") or b.get("pageId") not in pages
                or owners.get(b.get("elementId")) != b.get("pageId")
                or b.get("elementId") != target[role+"ElementId"]):
            raise ValueError("complete assigned input binding required: "+role)
        if role != "primary" and pages[b["pageId"]].get("visibility") != "hidden":
            raise ValueError("Save audit table must have hidden host")
        if role != "primary" and (b["elementId"]!=definition["audit"][role]["elementId"]
                or target[role+"RowIdColumnId"]!=definition["audit"][role]["rowIdColumnId"]):
            raise ValueError("current audit table differs from reviewed mapping")
        if role == "primary" and b["pageId"] != definition["primary"]["pageId"]:
            raise ValueError("reviewed primary page differs")
        by_name = {c.get("name"):c for c in schema}
        by_id = {c.get("id"):c for c in schema}
        public_columns=e.get("columns", [])
        if (not isinstance(public_columns,list)
                or len({c.get("id") for c in public_columns})!=len(public_columns)
                or len({c.get("name") for c in public_columns})!=len(public_columns)):
            raise ValueError("unique current public schema columns required")
        public = {c.get("id"):c for c in public_columns}
        if (len(by_name) != len(schema) or len(by_id) != len(schema)
                or not set(required[role]) <= set(by_name)):
            raise ValueError("complete unique assigned SDK columns required")
        natives = [c for c in schema if c.get("class") == "InputTableIDColumn" and c.get("kind") == "row_id"]
        if role != "primary":
            if len(natives) != 1 or natives[0]["id"] != target[role+"RowIdColumnId"]:
                raise ValueError("actual native audit physical ID column required")
            if public.get("ID") == {"id":"ID"}:
                public.pop("ID");public[natives[0]["id"]] = {"id":natives[0]["id"]}
        elif by_name["ID"].get("id") != target["primaryRowIdColumnId"]:
            raise ValueError("actual primary physical ID binding required")
        if set(public) != set(by_id):
            raise ValueError("public/assigned SDK schema differs")
        for name, typ in required[role].items():
            col = by_name[name]
            if typ is not None and col.get("type") != typ:
                raise ValueError("assigned SDK column type differs: "+name)
            if role != "primary" and col.get("class") != "LiteralEditableColumn":
                raise ValueError("audit payload requires literal editable columns")
            if role != "primary" and col.get("id") != definition["audit"][role]["columns"][name]["id"]:
                raise ValueError("current audit column differs from reviewed mapping: "+name)
        for col in schema:
            pub = public[col["id"]]
            if any(pub.get(k) != col.get(k) for k in ("name", "type") if k in pub):
                raise ValueError("public/SDK column identity differs")
        pv="p_"+role; tv="t_"+role
        lines += [f"{pv} = sigma.workbook.get_page({b['pageId']!r})",
                  f'if not isinstance({pv}, Page): raise RuntimeError("page type")',
                  f"{tv} = {pv}.get_element({b['elementId']!r})",
                  f'if not isinstance({tv}, InputTable): raise RuntimeError("table type")',
                  f"if {tv}.name() != {b['name']!r} or {tv}.edit_mode() != 'published-explore': raise RuntimeError('table identity/mode')"]
        # The full assigned/public schema is checked above. Runtime handles are
        # needed only for fields used by this guard or effect; sparse audit
        # tables may have hundreds of unrelated nullable columns.
        runtime_columns=[col for col in schema if col["name"] in required[role] or col["name"]=="ID"]
        for index,col in enumerate(runtime_columns):
            name="c_"+role+"_"+str(index)
            handles[(role,col["name"])] = name
            klass=col["class"]
            if klass not in ("LiteralEditableColumn", "SingleSelectEditableColumn", "InputTableIDColumn", "FormulaColumn"):
                raise ValueError("unsupported assigned SDK column class")
            if klass == "SingleSelectEditableColumn":
                values=col.get("allowedValues")
                if (role != "primary" or col.get("type")!="text" or not isinstance(values,list)
                        or not values or any(not isinstance(value,str) for value in values)
                        or len(set(values))!=len(values)):
                    raise ValueError("primary text select requires exact assigned allowed values")
            lines += [f"{name} = {tv}.get_column({col['id']!r})",
                      f'if not isinstance({name}, {klass}): raise RuntimeError("column class")',
                      f"if {name}.id() != {col['id']!r} or {name}.element_id() != {b['elementId']!r}: raise RuntimeError('column identity')"]
            if klass == "LiteralEditableColumn":
                lines += [f"if {name}.name() != {col['name']!r} or {name}.type() != {col['type']!r}: raise RuntimeError('column type')"]
            elif klass == "SingleSelectEditableColumn":
                lines += [f"if {name}.name() != {col['name']!r} or {name}.type() != {col['type']!r}: raise RuntimeError('select column type')",
                          f"if {name}.allowed_values() != {col['allowedValues']!r}: raise RuntimeError('select allowed values')"]
            elif klass == "InputTableIDColumn":
                lines += [f"if {name}.name() != 'ID' or {name}.kind() != 'row_id': raise RuntimeError('physical ID kind')"]
            else:
                lines += [f"if {name}.name() != {col['name']!r} or {name}.formula() != {col['formula']!r}: raise RuntimeError('source ID formula')"]
    control = elements.get(target["controlId"], {})
    name_control = elements.get(target["nameControlId"], {})
    if (control.get("kind") != "control" or control.get("controlType") != "text"
            or name_control.get("kind") != "control" or name_control.get("controlType") != "text"
            or owners.get(target["controlId"]) != bindings["operations"]["pageId"]
            or owners.get(target["nameControlId"]) != bindings["primary"]["pageId"]):
        raise ValueError("actual assigned native operation/name controls required")
    lines += [f"op = p_operations.get_element({target['controlId']!r})",
              'if not isinstance(op, TextControl): raise RuntimeError("operation control type")',
              f"name = p_primary.get_element({target['nameControlId']!r})",
              'if not isinstance(name, TextControl): raise RuntimeError("name control type")']
    if control.get("controlId"):
        lines += [f"if op.variable_name() != {control['controlId']!r}: raise RuntimeError('operation control variable')"]
    if name_control.get("controlId"):
        lines += [f"if name.variable_name() != {name_control['controlId']!r}: raise RuntimeError('name control variable')"]
    c=lambda role,field:handles[(role,field)]
    rid=c("operations","ID"); saved_id=c("saved","ID"); primary_id=c("primary","ID")
    op_lookup=lambda field:f"lookup({c('operations',field)}, op, {rid})"
    saved_lookup=lambda field:f"lookup({c('saved',field)}, op, {c('saved','Operation ID')})"
    nullable_name=lambda expression:f"as_text(coalesce({expression}, const_text('')))"
    op_id=completion_plan["operationId"]
    guards=[f"eq(op, const_text({op_id!r}))",
            f"eq({nullable_name('name')}, const_text({completion_plan['nameControl']!r}))",
            f"eq(count_if(eq({rid}, op)), const_num(1))",
            f"eq(count_if(eq({c('saved','Operation ID')}, op)), const_num(1))",
            f"eq({saved_lookup('ID')}, const_text({completion_plan['savedPhysicalRowId']!r}))",
            f"eq(count_if(is_not_null({primary_id})), const_num({len(definition['primary']['expectedRowIds'])}))"]
    metadata={"Workflow":definition["workflow"],"Context":definition["context"],
              "Source Hash":definition["sourceHash"],
              "Plan Hash":definition["planHash"],"Source Procedure Hash":definition["procedureHash"]}
    guards += [f"eq({nullable_name(op_lookup('Scenario Name'))}, const_text({completion_plan['nameControl']!r}))",
               f"eq({nullable_name(saved_lookup('Scenario Name'))}, const_text({completion_plan['nameControl']!r}))"]
    for field,value in metadata.items():
        guards.append(f"eq({op_lookup(field)}, const_text({value!r}))")
        if field in ("Source Hash", "Plan Hash", "Source Procedure Hash"):
            guards.append(f"eq({saved_lookup(field)}, const_text({value!r}))")
    guards += [f"eq({saved_lookup('Operation ID')}, op)",
               f"eq({op_lookup('Created At')}, const_date({completion_plan['frozenCreatedAt']!r}))",
               f"eq({saved_lookup('Saved At')}, const_date({completion_plan['frozenCreatedAt']!r}))",
               f"eq({saved_lookup('Saved At')}, {op_lookup('Created At')})"]
    state=completion_plan["observedOperationState"]
    if phase == "mark":
        guards.append(f"eq({op_lookup('State')}, const_text('PREPARED'))")
    else:
        terminal=f"or_(eq({op_lookup('State')}, const_text('CONFIRMED')), eq({op_lookup('State')}, const_text('ABANDONED')))"
        guards += [terminal,f"eq({op_lookup('State')}, const_text({state!r}))"]
    op_row=next(row for row in operations["rows"] if row["nativeRowId"]==op_id)
    for field in definition["fields"]:
        label=field["savedField"].removesuffix(" Growth")
        value=op_row[field["beforeField"]]
        numeric=f"const_num({str(_number(value))})"
        guards += [f"eq({op_lookup(label+' Input Row ID')}, const_text({field['rowId']!r}))",
                   f"eq({op_lookup(field['beforeField'])}, {numeric})",
                   f"eq({op_lookup(field['targetField'])}, {numeric})",
                   f"eq({saved_lookup(field['savedField'])}, {numeric})",
                   f"eq(count_if(and_(eq({primary_id}, const_text({field['rowId']!r})), eq({c('primary',field['keyColumn'])}, const_text({field['key']!r})))), const_num(1))",
                   f"eq(lookup({c('primary',field['valueColumn'])}, const_text({field['rowId']!r}), {primary_id}), {numeric})",
                   f"eq(lookup({c('primary','Method')}, const_text({field['rowId']!r}), {primary_id}), const_text('growth'))"]
    for row_id in definition["primary"]["expectedRowIds"]:
        guards.append(f"eq(count_if(eq({primary_id}, const_text({row_id!r}))), const_num(1))")
    lines += ["cursor = 1", "for existing in p_primary.list_elements(flat=False):",
              "    if isinstance(existing, GridFramed): cursor = max(cursor, existing.y() + existing.height())",
              "button = p_primary.add_button("+repr("Mark saved scenario confirmed" if phase=="mark" else "Clear completed save intent")+")",
              "button.set_frame(1, cursor, min(24, button.parent_grid_width()), 2)"]
    if phase == "mark":
        lines.append("sequence = button.on_click('Mark exact Save operation confirmed', [update_rows(t_operations, {"+rid+": op}, {"+c("operations","State")+": const_text('CONFIRMED')})])")
    else:
        lines.append("sequence = button.on_click('Clear exact terminal Save control', [set_control_value(op, '')])")
    lines += ["sequence.set_disabled(True)","sequence.set_condition("+_and(guards)+")",
              "sequence.remove_success_toast()","sequence.set_disabled(True)",
              "if not sequence.is_disabled(): raise RuntimeError('disabled')",
              "print({'saveCompletionPhase': "+repr(phase)+", 'buttonId': button.id(), 'sequenceId': sequence.id(), 'enabled': False})"]
    program="\n".join(lines)+"\n"
    compile(program,"save-completion-"+phase,"exec")
    return {"phase":phase,"program":program,"programHash":hashlib.sha256(program.encode()).hexdigest(),
            "controllerPrecondition":{"documentId":current["workbookId"],"version":current["documentVersion"],
                                      "contentsHash":digest(contents)},
            "definitionHash":definition["definitionHash"],"completionPlanHash":completion_plan["completionPlanHash"],
            "status":"DISABLED_COMPONENT_CANDIDATE","productionStatus":"BLOCKED",
            "limitations":["actual source/control and export/query provenance need controller review",
                           "native condition/physical-ID selector and persisted transition need live admission",
                           "blank InputBox text versus native null control/row mapping remains unqualified",
                           "no version CAS or transaction; published role/recovery/concurrency gates remain"]}
