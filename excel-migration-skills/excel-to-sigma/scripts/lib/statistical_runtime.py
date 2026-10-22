"""Offline source-bound Sigma Python preview emitter, with no REST mutation.

The caller must supply reviewed, actual element titles and paired Snowpark column
identifier/Row.as_dict keys. Output remains blocked pending an Excel-qualified ETS
provider, actual Sigma execution and the repository's phased output guards.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


REQUIRED = {
    "history": ("Month", "SKU", "Demand"),
    "parameters": ("Key", "Value"),
    "targets": ("Period", "Month"),
}
CANDIDATE_REQUIRED = {**REQUIRED,
                      "parameters": ("Scope", "SelectedSKU", "Seasonality",
                                     "ServiceLevel", "LeadTime")}
FIELDS = (("Status", "STRING"), ("ReadyToPublish", "BOOLEAN"),
          ("ErrorCode", "STRING"), ("InputHash", "STRING"),
          ("SourceHash", "STRING"), ("Month", "STRING"), ("SKU", "STRING"),
          ("ETS", "DOUBLE"), ("Linear", "DOUBLE"),
          ("SelectedSKUTrend", "DOUBLE"), ("Selected3MMA", "DOUBLE"),
          ("FY26ETSTotal", "DOUBLE"), ("StdDev36M", "DOUBLE"),
          ("SafetyStock", "DOUBLE"), ("ReorderPoint", "DOUBLE"),
          ("IntendedSequenceDescending", "INTEGER"))
OUTPUT_NAME = "StatisticalForecastPreview"
CANDIDATE_MODEL = "statsmodels 0.15.0 ETSModel(add,add,add; estimated initial states)"
CANDIDATE_FIELDS = (("ModelIdentity", "STRING"), ("FitDiagnostics", "STRING"),
                    ("RuntimePackages", "STRING"), ("PreviewRunId", "STRING"),
                    ("SourceBindingHash", "STRING"))


def _binding(binding, required=REQUIRED):
    if not isinstance(binding, dict) or set(binding) != set(required):
        raise ValueError("exact history/parameters/targets bindings required")
    titles = []
    for role, fields in required.items():
        entry = binding[role]
        if not isinstance(entry, dict) or set(entry) != {"title", "columns"}:
            raise ValueError("reviewed title and column map required")
        title, columns = entry["title"], entry["columns"]
        if not isinstance(title, str) or not title or not isinstance(columns, dict) or set(columns) != set(fields):
            raise ValueError("exact runtime source columns required")
        titles.append(title)
        identifiers, row_keys = [], []
        for name in fields:
            pair = columns[name]
            if (not isinstance(pair, dict) or set(pair) != {"identifier", "rowKey"}
                    or any(not isinstance(v, str) or not v for v in pair.values())):
                raise ValueError("observed identifier and rowKey pair required")
            identifiers.append(pair["identifier"])
            row_keys.append(pair["rowKey"])
        if len(set(identifiers)) != len(fields) or len(set(row_keys)) != len(fields):
            raise ValueError("ambiguous runtime column map")
    if len(set(titles)) != len(titles):
        raise ValueError("ambiguous input element titles")
    return binding


def emit_preview_program(binding, *, candidate_ets=False, source_identity=None):
    """Return a reviewable program, never a production-ready port."""
    if type(candidate_ets) is not bool:
        raise ValueError("candidate_ets must be a boolean opt-in")
    binding = _binding(binding, CANDIDATE_REQUIRED if candidate_ets else REQUIRED)
    if candidate_ets:
        if (not isinstance(source_identity, dict)
                or not isinstance(source_identity.get("workbookId"), str)
                or not source_identity["workbookId"]
                or not isinstance(source_identity.get("workbookVersion"), int)
                or isinstance(source_identity["workbookVersion"], bool)
                or not isinstance(source_identity.get("pageId"), str)
                or not source_identity["pageId"]
                or not isinstance(source_identity.get("sourceSnapshotId"), str)
                or not source_identity["sourceSnapshotId"]
                or not isinstance(source_identity.get("sourceSnapshotHash"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", source_identity["sourceSnapshotHash"])
                or not isinstance(source_identity.get("sourcePacketHash"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", source_identity["sourcePacketHash"])
                or not isinstance(source_identity.get("roles"), dict)
                or set(source_identity["roles"]) != set(CANDIDATE_REQUIRED)):
            raise ValueError("OBSERVED_SOURCE_IDENTITY_REQUIRED")
        ids = []
        for role in CANDIDATE_REQUIRED:
            item = source_identity["roles"][role]
            if (not isinstance(item, dict) or not item.get("elementId")
                    or item.get("title") != binding[role]["title"]
                    or item.get("columns") != binding[role]["columns"]):
                raise ValueError("OBSERVED_SOURCE_IDENTITY_MISMATCH:" + role)
            ids.append(item["elementId"])
        if len(set(ids)) != len(ids):
            raise ValueError("AMBIGUOUS_SOURCE_ELEMENTS")
    elif source_identity is not None:
        raise ValueError("UNQUALIFIED_PREVIEW_HAS_NO_IDENTITY_OVERRIDE")
    binding_hash = hashlib.sha256(json.dumps({"binding": binding, "sourceIdentity": source_identity},
                                              sort_keys=True).encode()).hexdigest() if candidate_ets else hashlib.sha256(
                                                  json.dumps(binding, sort_keys=True).encode()).hexdigest()
    kernel = Path(__file__).with_name("statistical_forecast.py").read_text()
    provider = (Path(__file__).with_name("statistical_ets_candidate.py").read_text()
                .replace("from __future__ import annotations\n", "")
                if candidate_ets else "")
    fields = FIELDS + CANDIDATE_FIELDS if candidate_ets else FIELDS
    # Sigma's Python dependency parser requires literal source names. Resolve
    # frames again before the second collection so input drift remains guarded.
    frame_bindings = "\n".join(
        f"        {role!r}: sigma.get_element({binding[role]['title']!r})," for role in REQUIRED)
    code = kernel + "\n" + provider + "\n" + '''
import hashlib
import json
import uuid

SOURCE_BINDING = ''' + repr(binding) + '''
SOURCE_IDENTITY = ''' + repr(source_identity) + '''
SOURCE_BINDING_HASH = ''' + repr(binding_hash) + '''
OUTPUT_COLUMNS = ''' + repr([name for name, _ in fields]) + '''
OUTPUT_TYPES = ''' + repr(dict(fields)) + '''
CANDIDATE_ETS = ''' + repr(candidate_ets) + '''
MODEL_IDENTITY = ''' + repr(CANDIDATE_MODEL if candidate_ets else "NONE") + '''


def read_bound_frames():
    return {
''' + frame_bindings + '''
    }


def read_bound_rows(role, frame):
    spec = SOURCE_BINDING[role]
    observed = list(frame.columns)
    columns = spec['columns']
    if any(observed.count(pair['identifier']) != 1 for pair in columns.values()):
        raise StatisticalPortError('RUNTIME_COLUMN_MISMATCH')
    rows = []
    for record in frame.collect():
        raw = record.as_dict()
        if any(pair['rowKey'] not in raw for pair in columns.values()):
            raise StatisticalPortError('RUNTIME_ROW_KEY_MISMATCH')
        rows.append({name: raw[pair['rowKey']] for name, pair in columns.items()})
    return rows


input_hash = None
run_id = str(uuid.uuid4())
fit_diagnostics = {}
runtime_packages = {}
try:
    frames = read_bound_frames()
    session = frames['history'].session
    history = read_bound_rows('history', frames['history'])
    parameters = read_bound_rows('parameters', frames['parameters'])
    targets = read_bound_rows('targets', frames['targets'])
    raw_input = {'history': sorted(history, key=lambda r: (str(r['Month']), str(r['SKU']))),
                 'parameters': sorted(parameters, key=lambda r: str(r['Scope'] if CANDIDATE_ETS else r['Key'])),
                 'targets': sorted(targets, key=lambda r: str(r['Period']))}
    input_hash = hashlib.sha256(json.dumps(raw_input, sort_keys=True, default=str,
                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if CANDIDATE_ETS:
        if len(parameters) != 1 or parameters[0]['Scope'] != 'Parameters':
            raise StatisticalPortError('INVALID_PARAMETER_SCOPE')
        p = parameters[0]
        selected, season, service, lead = (p['SelectedSKU'], p['Seasonality'],
                                           p['ServiceLevel'], p['LeadTime'])
    else:
        if len(parameters) != 4 or set(r['Key'] for r in parameters) != {
                'Selected SKU', 'Seasonality (months)', 'Service level', 'Lead time (months)'}:
            raise StatisticalPortError('INVALID_PARAMETER_KEYS')
        p = {r['Key']: r['Value'] for r in parameters}
        selected, season, service, lead = (p['Selected SKU'], p['Seasonality (months)'],
                                           p['Service level'], p['Lead time (months)'])
    if len(targets) != 12 or set(r['Period'] for r in targets) != set(range(1, 13)):
        raise StatisticalPortError('INVALID_TARGET_KEYS')
    ordered_targets = [r['Month'] for r in sorted(targets, key=lambda r: r['Period'])]
    provider = None
    if CANDIDATE_ETS:
        try:
            from importlib.metadata import PackageNotFoundError, version
            runtime_packages = {'statsmodels': version('statsmodels'),
                                'scipy': version('scipy')}
            if runtime_packages['statsmodels'] != '0.15.0':
                raise StatisticalPortError('CANDIDATE_VERSION_MISMATCH')
            if runtime_packages['scipy'] != '1.18.1':
                raise StatisticalPortError('CANDIDATE_SCIPY_VERSION_MISMATCH')
        except PackageNotFoundError as exc:
            raise StatisticalPortError('CANDIDATE_DEPENDENCY_UNAVAILABLE') from exc
        fit_index = [0]
        def provider(values, seasonality, horizon):
            sku = SKUS[fit_index[0]]
            try:
                fit = forecast_with_diagnostics(values, seasonality, horizon)
            except CandidateFitError as exc:
                fit_diagnostics[sku] = {'error': exc.code, **exc.diagnostics}
                raise StatisticalPortError('CANDIDATE_' + exc.code) from exc
            fit_diagnostics[sku] = fit['diagnostics']
            fit_index[0] += 1
            return fit['forecasts']
    result = calculate(history, selected, season,
                       service, lead, ordered_targets,
                       ets_forecaster=provider)
    latest_frames = read_bound_frames()
    latest_history = read_bound_rows('history', latest_frames['history'])
    latest_parameters = read_bound_rows('parameters', latest_frames['parameters'])
    latest_targets = read_bound_rows('targets', latest_frames['targets'])
    latest_input = {'history': sorted(latest_history, key=lambda r: (str(r['Month']), str(r['SKU']))),
                    'parameters': sorted(latest_parameters, key=lambda r: str(r['Scope'] if CANDIDATE_ETS else r['Key'])),
                    'targets': sorted(latest_targets, key=lambda r: str(r['Period']))}
    latest_hash = hashlib.sha256(json.dumps(latest_input, sort_keys=True, default=str,
                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if latest_hash != input_hash:
        raise StatisticalPortError('INPUT_CHANGED_DURING_RUN')
    summaries = {r['SKU']: r for r in result['Summary']}
    rows = []
    for period_index, period in enumerate(result['Periods']):
        for sku in SKUS:
            summary = summaries[sku]
            rows.append(dict(Status=result['Status'], ReadyToPublish=False,
                ErrorCode='CANDIDATE_REVIEW_REQUIRED' if CANDIDATE_ETS else 'EXCEL_ETS_PROVIDER_UNQUALIFIED', InputHash=input_hash,
                SourceHash=SOURCE_SHA256, Month=period['Month'], SKU=sku,
                ETS=period['ETS'][sku], Linear=period['Linear'][sku],
                SelectedSKUTrend=period['SelectedSKUTrend'],
                Selected3MMA=period['Selected3MMA'], FY26ETSTotal=summary['FY26ETSTotal'],
                StdDev36M=summary['StdDev36M'], SafetyStock=summary['SafetyStock'],
                ReorderPoint=summary['ReorderPoint'],
                IntendedSequenceDescending=result['IntendedSequenceDescending'][period_index],
                ModelIdentity=MODEL_IDENTITY, FitDiagnostics=json.dumps(fit_diagnostics, sort_keys=True, allow_nan=False),
                RuntimePackages=json.dumps(runtime_packages, sort_keys=True),
                PreviewRunId=run_id, SourceBindingHash=SOURCE_BINDING_HASH))
except Exception as error:
    rows = [dict(Status='FAILURE', ReadyToPublish=False,
                 ErrorCode=str(error) if isinstance(error, StatisticalPortError) else 'RUNTIME_INPUT_ERROR',
                 InputHash=input_hash, SourceHash=SOURCE_SHA256,
                 ModelIdentity=MODEL_IDENTITY,
                 FitDiagnostics=json.dumps(fit_diagnostics, sort_keys=True, default=str, allow_nan=False),
                 RuntimePackages=json.dumps(runtime_packages, sort_keys=True),
                 PreviewRunId=run_id, SourceBindingHash=SOURCE_BINDING_HASH)]

try:
    values = [[typed_output_value(row.get(name), OUTPUT_TYPES[name]) for name in OUTPUT_COLUMNS]
              for row in rows]
    output_frame = session.create_dataframe(values, schema=''' + repr(", ".join('"'+name+'" '+type_ for name,type_ in fields)) + ''')
except Exception:
    fallback = dict(Status='FAILURE', ReadyToPublish=False,
                    ErrorCode='RUNTIME_OUTPUT_TYPE_ERROR', SourceHash=SOURCE_SHA256,
                    ModelIdentity=MODEL_IDENTITY,
                    RuntimePackages=json.dumps(runtime_packages, sort_keys=True),
                    PreviewRunId=run_id, SourceBindingHash=SOURCE_BINDING_HASH)
    output_frame = session.create_dataframe([[typed_output_value(fallback.get(name), OUTPUT_TYPES[name])
                                              for name in OUTPUT_COLUMNS]],
        schema=''' + repr(", ".join('"'+name+'" '+type_ for name,type_ in fields)) + ''')
sigma.output(''' + repr(OUTPUT_NAME) + ''', output_frame)
'''
    return {"code": code, "codeHash": hashlib.sha256(code.encode()).hexdigest(),
            "output": OUTPUT_NAME, "schema": list(fields),
            "sourceBindingHash": binding_hash,
            "sourceIdentity": source_identity,
            "externalIdentityGuardRequired": candidate_ets,
            "runtimeStatus": "UNRESOLVED", "productionStatus": "BLOCKED",
            "reason": "CANDIDATE_REVIEW_REQUIRED" if candidate_ets else "EXCEL_ETS_PROVIDER_UNQUALIFIED",
            "modelIdentity": CANDIDATE_MODEL if candidate_ets else "NONE"}
