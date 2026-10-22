"""Typed, resumable input-table seeding plans and reviewable Sigma SDK programs.

This module never queries Sigma.  The caller must query the current table with the
companion MCP describe/query tools, pass those rows to :func:`plan_seed`, execute
the emitted program, and query again before recording a checkpoint.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping, Sequence


MAX_BATCH_ROWS = 2000


class InputSyncError(ValueError):
    pass


def _json_value(value):
    if isinstance(value, dt.datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, dt.date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _digest(value):
    encoded = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _typed(value):
    if value is None:
        tag = "null"
    elif isinstance(value, bool):
        tag = "bool"
    elif isinstance(value, int):
        tag = "int"
    elif isinstance(value, float):
        tag = "float"
    elif isinstance(value, dt.datetime):
        tag, value = "datetime", value.isoformat()
    elif isinstance(value, dt.date):
        tag, value = "date", value.isoformat()
    elif isinstance(value, str):
        tag = "str"
    else:
        raise InputSyncError(f"unsupported business-key type: {type(value).__name__}")
    return {"type": tag, "value": value}


def _key(row, columns, origin):
    values = []
    for column in columns:
        if column not in row or row[column] is None:
            raise InputSyncError(f"missing business key {column!r} in {origin} row")
        values.append(_typed(row[column]))
    return values


def _key_token(key):
    return json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _index(rows, key_columns, origin):
    result = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise InputSyncError(f"{origin} rows must be objects")
        key = _key(row, key_columns, origin)
        token = _key_token(key)
        if token in result:
            raise InputSyncError(f"duplicate {origin} business key: {token}")
        result[token] = (key, dict(row))
    return result


def _same(left, right, column_type=None):
    if column_type == "datetime":
        try:
            date_only = any(
                isinstance(value, dt.date) and not isinstance(value, dt.datetime)
                or isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                for value in (left, right)
            )
            return (_parse_datetime(left, date_only=date_only)
                    == _parse_datetime(right, date_only=date_only))
        except (TypeError, ValueError):
            return False
    return _json_value(left) == _json_value(right) and type(left) is type(right)


def normalize_seed_plan(prior_seed):
    """Accept a canonical plan or the exact public {plan, programs} envelope.

    Never interpret an unrecognized persisted object as an empty baseline.
    """
    if prior_seed is None:
        return None
    if not isinstance(prior_seed, dict):
        raise InputSyncError("prior seed must be a canonical seed plan")
    if "plan" in prior_seed or "programs" in prior_seed:
        if set(prior_seed) != {"plan", "programs"} or not isinstance(prior_seed["programs"], list):
            raise InputSyncError("ambiguous prior seed wrapper")
        prior_seed = prior_seed["plan"]
    if (not isinstance(prior_seed, dict)
            or not isinstance(prior_seed.get("seedRecords"), list)
            or not isinstance(prior_seed.get("keyColumns"), list)
            or not prior_seed["keyColumns"] or not prior_seed.get("rowIdColumn")
            or "plan" in prior_seed or "programs" in prior_seed):
        raise InputSyncError("prior seed is not a canonical seed plan")
    allowed = {"sourceHash", "planHash", "keyColumns", "rowIdColumn", "inserts", "updates",
               "conflicts", "unchanged", "orphans", "snapshot", "seedRecords", "limitations",
               "extensionSeedCheckpoints", "extensionSeedScope"}
    if set(prior_seed) - allowed:
        raise InputSyncError("prior seed has foreign fields")
    for record in prior_seed["seedRecords"]:
        if (not isinstance(record, dict) or not isinstance(record.get("key"), list)
                or not any(field in record for field in (
                    "confirmedMigrationValue", "pendingMigrationValue", "lastMigrationValue"))):
            raise InputSyncError("invalid prior seed record")
        for field in ("confirmedMigrationValue", "pendingMigrationValue", "lastMigrationValue"):
            if record.get(field) is not None and not isinstance(record[field], dict):
                raise InputSyncError("invalid prior seed baseline")
    ledger = prior_seed.get("extensionSeedCheckpoints", [])
    if (not isinstance(ledger, list) or any(not isinstance(item, str) or not item for item in ledger)
            or len(ledger) != len(set(ledger))):
        raise InputSyncError("invalid extension checkpoint ledger")
    return prior_seed


def _prior_index(prior_seed):
    result = {}
    if not prior_seed:
        return result
    for record in prior_seed.get("seedRecords", []):
        key = record.get("key")
        if isinstance(key, list) and any(isinstance(record.get(field), dict) for field in (
                "confirmedMigrationValue", "pendingMigrationValue", "lastMigrationValue")):
            result[_key_token(key)] = record
    return result


def plan_seed(source_rows, current_rows, key_columns, row_id_column, prior_seed=None,
              snapshot=None, column_types=None):
    """Plan inserts and safe row-ID updates without overwriting observed user edits."""
    prior_seed = normalize_seed_plan(prior_seed)
    if prior_seed is not None and (prior_seed["keyColumns"] != list(key_columns)
                                   or prior_seed["rowIdColumn"] != row_id_column):
        raise InputSyncError("prior seed key/row-ID scope is foreign")
    source_rows = list(source_rows)
    current_rows = list(current_rows)
    if not key_columns or not all(isinstance(column, str) and column for column in key_columns):
        raise InputSyncError("key_columns must contain at least one column name")
    source = _index(source_rows, key_columns, "source")
    current = _index(current_rows, key_columns, "current")
    previous = _prior_index(prior_seed)
    inserts, updates, conflicts, unchanged, orphans, records = [], [], [], [], [], []

    for token in sorted(source):
        key, wanted = source[token]
        if token not in current:
            entry = {"key": key, "source": wanted}
            inserts.append(entry)
            prior = previous.get(token) or {}
            records.append({"key": key,
                            "confirmedMigrationValue": prior.get("confirmedMigrationValue"),
                            "pendingMigrationValue": wanted})
            continue
        _current_key, observed = current[token]
        row_id = observed.get(row_id_column)
        if row_id is None:
            raise InputSyncError(f"current row for {token} has no real server row ID in {row_id_column!r}")
        comparable = {name: value for name, value in observed.items() if name != row_id_column}
        types = dict(column_types or {})
        changed_columns = [name for name, value in wanted.items()
                           if name not in key_columns
                           and not _same(comparable.get(name), value, types.get(name))]
        if not changed_columns:
            unchanged.append({"key": key, "rowId": row_id, "source": wanted})
            records.append({"key": key, "confirmedMigrationValue": wanted,
                            "pendingMigrationValue": None})
            continue

        prior = previous.get(token) or {}
        confirmed = prior.get("confirmedMigrationValue")
        pending = prior.get("pendingMigrationValue")
        legacy = prior.get("lastMigrationValue")
        if confirmed is None and isinstance(legacy, dict):
            confirmed = legacy
        if isinstance(pending, dict) and all(
                name in comparable and _same(comparable[name], value, types.get(name))
                for name, value in pending.items()):
            confirmed = pending
        safe, conflicting = {}, []
        for name in changed_columns:
            if (isinstance(confirmed, dict) and name in confirmed
                    and _same(comparable.get(name), confirmed[name], types.get(name))):
                safe[name] = wanted[name]
            else:
                conflicting.append(name)
        if conflicting:
            conflicts.append({"key": key, "rowId": row_id, "columns": conflicting,
                              "source": wanted, "current": comparable,
                              "confirmedMigrationValue": confirmed})
            records.append({"key": key, "confirmedMigrationValue": confirmed,
                            "pendingMigrationValue": pending})
        else:
            updates.append({"key": key, "rowId": row_id, "changes": safe,
                            "source": wanted, "current": comparable,
                            "confirmedMigrationValue": confirmed})
            records.append({"key": key, "confirmedMigrationValue": confirmed,
                            "pendingMigrationValue": wanted})

    for token in sorted(set(current) - set(source)):
        key, row = current[token]
        orphans.append({"key": key, "rowId": row.get(row_id_column), "current": row})

    source_hash = _digest(list(source_rows))
    logical = {"sourceHash": source_hash, "keyColumns": list(key_columns),
               "rowIdColumn": row_id_column, "inserts": inserts, "updates": updates,
               "conflicts": conflicts, "unchanged": unchanged, "orphans": orphans}
    if prior_seed and prior_seed.get("extensionSeedCheckpoints"):
        logical["extensionSeedCheckpoints"] = list(prior_seed["extensionSeedCheckpoints"])
        logical["extensionSeedScope"] = copy.deepcopy(prior_seed.get("extensionSeedScope"))
    return {**logical, "planHash": _digest(logical), "snapshot": dict(snapshot or {}),
            "seedRecords": records,
            "limitations": [
                "No compare-and-swap is available between MCP query and write.",
                "Re-query after interruptions and before each emitted write program.",
                "Orphans are reported and are never deleted automatically.",
            ]}


def _parse_datetime(value, date_only=False):
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        if date_only and value.time() == dt.time.min:
            value = value.replace(hour=12)
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, 12)
    if isinstance(value, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = dt.date.fromisoformat(value)
            return dt.datetime(parsed.year, parsed.month, parsed.day, 12)
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _parse_datetime(parsed, date_only=date_only)
    return value


def _sdk_literal(value, column_type=None, *, date_only_hour=12):
    """Emit constructor literals admitted by the MCP SDK, never parser calls.

    Authored source dates use noon; captured warehouse timestamps/date strings
    use hour0 explicitly so rollback does not shift midnight. Aware instants
    normalize to UTC before their timezone-free warehouse constructor is emitted.
    """
    if date_only_hour not in (0, 12):
        raise InputSyncError('date-only SDK literal policy must be midnight or noon')
    if column_type == "datetime" or isinstance(value, (dt.datetime, dt.date)):
        date_only = (isinstance(value, dt.date) and not isinstance(value, dt.datetime)) or (
            isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        )
        value = _parse_datetime(value)
        if date_only:
            if date_only_hour == 12:
                return f"datetime({value.year}, {value.month}, {value.day}, 12)"
            value = value.replace(hour=0)
        if value is not None and not isinstance(value, dt.datetime):
            raise InputSyncError('datetime SDK literal requires an actual timestamp')
    if isinstance(value, dt.datetime):
        fraction=f", {value.microsecond}" if value.microsecond else ""
        return (f"datetime({value.year}, {value.month}, {value.day}, {value.hour}, "
                f"{value.minute}, {value.second}{fraction})")
    if value is None:
        return "None"
    return repr(value)


def _validate_spec(spec):
    required = ("pageId", "connectionId", "name", "columns")
    missing = [key for key in required if not spec.get(key)]
    if missing:
        raise InputSyncError("table spec missing: " + ", ".join(missing))
    names = [column.get("name") for column in spec["columns"]]
    if len(names) != len(set(names)) or any(not name for name in names):
        raise InputSyncError("editable column names must be unique and nonempty")
    if any(column.get("provenance") == "system" for column in spec["columns"]):
        raise InputSyncError("system columns cannot be seeded as editable columns")


def sigma_input_type(value):
    """Map a typed source literal to the ordinary input-table type vocabulary."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (dt.date, dt.datetime)):
        return "datetime"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def evaluate_timing_status(stage, close_date, as_of_date):
    """Reference behavior for the emitted day-grain sales calculation."""
    if stage in {"Closed Won", "Closed Lost"}:
        return "Closed"
    close_day = _parse_datetime(close_date).date()
    as_of_day = _parse_datetime(as_of_date).date()
    return "Slipped" if close_day < as_of_day else "Open"


def evaluate_expense_exception(row, policy_limit):
    """Reference behavior for the joined policy exception calculation."""
    if policy_limit is None:
        return {"policyExcess": None, "exception": None}
    excess = max(row["Amount"] - policy_limit, 0)
    try:
        from .workflow_repairs import reconciliation_required
    except ImportError:
        from workflow_repairs import reconciliation_required
    if reconciliation_required(row["Card Amount"], row["Ledger Amount"]):
        status = "RECON"
    elif excess > 0:
        status = "OVER LIMIT"
    elif row["Receipt Status"] == "Missing":
        status = "MISSING RECEIPT"
    elif row["Approval Status"] != "Approved":
        status = "PENDING"
    else:
        status = "CLEAR"
    return {"policyExcess": excess, "exception": status}


def include_research_line_input_literals(plan):
    """Promote source-authored, nondependency line literals into live inputs.

    The operation is deterministic and idempotent; conflicting pre-existing
    source-input metadata fails closed.
    """
    existing = list(plan.get("sourceInputs") or [])
    by_cell = {item.get("sourceCellId"): item for item in existing}
    additions = []
    for line in plan.get("lines") or []:
        literal_inputs = line.get("literalInputs") or {}
        provenance = line.get("provenance") or {}
        if line.get("deps") or not literal_inputs or not provenance:
            continue
        for year, value in literal_inputs.items():
            record = provenance.get(str(year)) or {}
            source_cell = record.get("sourceCellId")
            match = re.fullmatch(r"([^!]+)!([A-Z]+)(\d+)", source_cell or "")
            if not match or int(match.group(3)) != int(line.get("row")):
                raise InputSyncError(f"line literal provenance is incomplete: {line.get('col_id')}/{year}")
            logical_id = f"i_{match.group(1).lower().replace(' ', '_')}_{match.group(2).lower()}{match.group(3)}"
            candidate = {"id": logical_id, "sourceCellId": source_cell,
                         "sheet": match.group(1), "address": f"{match.group(2)}{match.group(3)}",
                         "defaultValue": value, "values": {str(year): value},
                         "mappingStatus": "live", "role": "source_literal"}
            prior = by_cell.get(source_cell)
            if prior is not None:
                for key in ("id", "sheet", "address", "defaultValue", "role"):
                    if prior.get(key) != candidate[key]:
                        raise InputSyncError(f"conflicting source input metadata: {source_cell}")
                continue
            by_cell[source_cell] = candidate
            additions.append(candidate)
    if additions:
        plan["sourceInputs"] = existing + additions
    return plan


def _manifest_architecture(manifest):
    projection = manifest.get("planProjection") or {}
    architecture = projection.get("sharedInputArchitecture")
    if not isinstance(architecture, dict) or not isinstance(architecture.get("inputs"), dict):
        raise InputSyncError("manifest does not contain hash-bound sharedInputArchitecture")
    return architecture


def _construction_spec(input_spec, binding):
    return {
        "pageId": binding.get("pageId"),
        "connectionId": input_spec.get("connectionId"),
        "name": input_spec.get("name"),
        "columns": input_spec.get("columns"),
        "writebackSchemaId": input_spec.get("writebackSchemaId"),
        "editMode": input_spec.get("editMode", "draft"),
        "frame": input_spec.get("frame", [1, 1, 24, 12]),
    }


def build_artifact_records(manifest, architecture, target_bindings):
    """Hash every approved feature's exact schema, seed rows, and target binding."""
    if architecture != _manifest_architecture(manifest):
        raise InputSyncError("architecture is not the immutable manifest architecture")
    inputs = architecture["inputs"]
    if set(target_bindings or {}) != set(inputs):
        raise InputSyncError("target bindings must exactly cover approved input tables")
    artifacts = {}
    wiring = build_operational_input_elements(architecture)
    wiring_hash = _digest(wiring)
    for feature in sorted(inputs):
        binding = target_bindings[feature]
        for field in ("documentId", "version", "pageId"):
            if binding.get(field) is None or binding.get(field) == "":
                raise InputSyncError(f"target binding for {feature} requires {field}")
        spec = _construction_spec(inputs[feature], binding)
        _validate_spec(spec)
        material = {
            "sourceHash": manifest.get("sourceHash"),
            "planHash": manifest.get("planHash"),
            "feature": feature,
            "constructionSpec": spec,
            "seedRows": inputs[feature].get("rows") or [],
            "targetBinding": binding,
            "workbookWiringHash": wiring_hash,
        }
        artifacts[feature] = {
            "feature": feature,
            "specHash": _digest(spec),
            "seedHash": _digest(material["seedRows"]),
            "targetBindingHash": _digest(binding),
            "workbookWiringHash": wiring_hash,
            "artifactHash": _digest(material),
        }
    return artifacts


def validate_artifact_receipt(manifest, receipt, *, allow_input_only=False):
    """Validate current source/plan integrity before trusting receipt claims.

    Matching two persisted hashes is insufficient: the manifest may have been
    edited since those hashes were approved. This gate also runs for consumers
    with no feature loop (wiring and acceptance matrices).
    """
    try:
        from .migration_manifest import validate_manifest, execution_scope
    except ImportError:
        from migration_manifest import validate_manifest, execution_scope
    try:
        validate_manifest(manifest, allow_input_only=allow_input_only)
    except ValueError as error:
        raise InputSyncError("approved manifest is stale or invalid: " + str(error)) from error
    if not isinstance(receipt, dict):
        raise InputSyncError("input artifact requires an approved staging receipt")
    input_only = execution_scope(manifest) == "input-tables-only"
    if input_only:
        if (receipt.get("status") != "APPROVED_INPUT_STAGING"
                or receipt.get("scope") != "input-tables-only"):
            raise InputSyncError("input-tables-only artifacts require an APPROVED_INPUT_STAGING receipt")
    else:
        if receipt.get("scope") is not None or receipt.get("status") == "APPROVED_INPUT_STAGING":
            raise InputSyncError("input-tables-only or scoped receipt cannot authorize a full artifact")
        if receipt.get("status") != "APPROVED_STAGING":
            raise InputSyncError("input artifact requires an APPROVED_STAGING receipt")
    if (receipt.get("sourceHash") != manifest.get("sourceHash")
            or receipt.get("planHash") != manifest.get("planHash")):
        raise InputSyncError("approved staging receipt is stale")
    architecture = _manifest_architecture(manifest)
    bindings = receipt.get("targetBindings") or {}
    expected = build_artifact_records(manifest, architecture, bindings)
    if receipt.get("artifacts") != expected:
        raise InputSyncError("approved artifact binding does not match manifest architecture")
    target = manifest.get("target")
    if target and any(target.get("documentId") != binding.get("documentId")
                      or target.get("version") != binding.get("version")
                      for binding in bindings.values()):
        raise InputSyncError("approved target document/version is stale")
    return architecture, bindings, expected


def _approved_feature(manifest, receipt, feature, *, require_assigned=False, allow_input_only=False):
    architecture, bindings, expected = validate_artifact_receipt(
        manifest, receipt, allow_input_only=allow_input_only)
    if feature not in architecture["inputs"]:
        raise InputSyncError(f"feature is not approved: {feature}")
    binding = bindings[feature]
    if require_assigned:
        for field in ("elementId", "columnIds"):
            if not binding.get(field):
                raise InputSyncError(f"approved target binding for {feature} requires {field}")
        expected_columns = {column["name"] for column in architecture["inputs"][feature]["columns"]}
        if set(binding["columnIds"]) != expected_columns:
            raise InputSyncError("approved column IDs do not exactly cover the input schema")
    return architecture["inputs"][feature], binding, expected[feature]


def plan_input_extension(manifest, staging_receipt, feature, current_columns):
    """Plan missing-only columns against an approved pre-extension target."""
    input_spec, target, artifact = _approved_feature(
        manifest, staging_receipt, feature)
    if not target.get("elementId") or not isinstance(target.get("columnIds"), dict):
        raise InputSyncError("approved pre-extension target requires elementId and columnIds")
    if not isinstance(current_columns, list):
        raise InputSyncError("extension requires current editable-column readback")
    observed = {}
    for column in current_columns:
        if not isinstance(column, dict):
            raise InputSyncError("current editable columns must be objects")
        name, column_id = column.get("name"), column.get("id")
        if not name or not column_id or name in observed:
            raise InputSyncError("current editable columns require unique names and IDs")
        observed[name] = column
    if set(target["columnIds"]) != set(observed):
        raise InputSyncError("current columns do not match the approved pre-extension binding")
    for name, column_id in target["columnIds"].items():
        if observed[name]["id"] != column_id:
            raise InputSyncError(f"current column ID is stale: {name}")
    expected = {column["name"]: column for column in input_spec["columns"]}
    if not set(observed).issubset(expected):
        raise InputSyncError("current columns are foreign to the approved input schema")
    for name, column in observed.items():
        if column.get("type") != expected[name]["type"]:
            raise InputSyncError(f"current column type is stale: {name}")
    missing = [expected[name] for name in expected if name not in observed]
    material = {
        "sourceHash": manifest["sourceHash"], "planHash": manifest["planHash"],
        "preReceiptHash": _digest(staging_receipt), "artifactHash": artifact["artifactHash"],
        "feature": feature, "documentId": target["documentId"],
        "baseVersion": target["version"], "pageId": target["pageId"],
        "elementId": target["elementId"], "observedColumns": target["columnIds"],
        "missingColumns": missing,
    }
    extension_hash = _digest(material)
    result = {**material, "extensionHash": extension_hash,
              "mode": "extend-existing" if missing else "reconcile-existing"}
    if missing:
        lines = [
            f"# extensionHash={extension_hash}",
            f"# preReceiptHash={material['preReceiptHash']}",
            f"host = sigma.workbook.get_page({target['pageId']!r})",
            "if not isinstance(host, Page):",
            "    raise RuntimeError('expected current page host')",
            f"table = host.get_element({target['elementId']!r})",
            "if not isinstance(table, InputTable):",
            "    raise RuntimeError('expected existing input table')",
        ]
        for index, column in enumerate(missing):
            lines.append(
                f"n{index} = table.add_editable_column({column['name']!r}, {column['type']!r})")
        lines.append("print('inputTableId=' + table.id())")
        for index, column in enumerate(missing):
            lines.append(f"print({('column:' + column['name'] + '=')!r} + n{index}.id())")
        result["program"] = "\n".join(lines) + "\n"
    return result


def checkpoint_input_extension(extension_plan, created_columns, *, result_version, readback):
    """Bind created IDs and immediate readback values to one extension plan."""
    if extension_plan.get("mode") != "extend-existing":
        raise InputSyncError("only a missing-column extension can be checkpointed")
    expected = {column["name"] for column in extension_plan["missingColumns"]}
    if (not isinstance(created_columns, dict) or set(created_columns) != expected
            or any(not value for value in created_columns.values())
            or len(set(created_columns.values())) != len(created_columns)):
        raise InputSyncError("created column IDs must exactly cover the extension")
    if (not isinstance(result_version, int)
            or result_version < extension_plan["baseVersion"]):
        raise InputSyncError("extension result version is stale")
    if (not isinstance(readback, dict) or not readback.get("readbackId")
            or readback.get("elementId") != extension_plan["elementId"]
            or readback.get("version") != result_version):
        raise InputSyncError("extension readback target/version is stale")
    columns = readback.get("columns")
    if not isinstance(columns, dict) or set(columns) != expected:
        raise InputSyncError("extension readback must exactly cover created columns")
    for name, item in columns.items():
        if not isinstance(item, dict) or item.get("columnId") != created_columns[name]:
            raise InputSyncError(f"extension readback column ID is stale: {name}")
    proof = {
        "status": "CHECKPOINTED_EXTENSION", "sourceHash": extension_plan["sourceHash"],
        "planHash": extension_plan["planHash"],
        "preReceiptHash": extension_plan["preReceiptHash"],
        "extensionHash": extension_plan["extensionHash"],
        "feature": extension_plan["feature"],
        "documentId": extension_plan["documentId"],
        "baseVersion": extension_plan["baseVersion"], "resultVersion": result_version,
        "pageId": extension_plan["pageId"], "elementId": extension_plan["elementId"],
        "createdColumns": dict(created_columns), "readback": readback,
    }
    proof["checkpointHash"] = _digest(proof)
    return proof


def plan_extension_seed(source_rows, current_rows, key_columns, row_id_column, *,
                        prior_seed, manifest, staging_receipt, feature,
                        extension_proof, snapshot=None, column_types=None):
    """Authorize a first seed only for checkpointed, newly-created null fields."""
    prior_seed = normalize_seed_plan(prior_seed)
    input_spec, target, _artifact = _approved_feature(
        manifest, staging_receipt, feature, require_assigned=True)
    source_rows, current_rows = list(source_rows), list(current_rows)
    if _digest(source_rows) != _artifact["seedHash"] or list(key_columns) != input_spec["keyColumns"]:
        raise InputSyncError("extension seed source rows/key scope differ from approved source")
    seed_scope = {"sourceHash": manifest["sourceHash"], "planHash": manifest["planHash"],
                  "feature": feature, "documentId": target["documentId"],
                  "pageId": target["pageId"], "elementId": target["elementId"]}
    if (prior_seed or {}).get("extensionSeedScope") not in (None, seed_scope):
        raise InputSyncError("prior extension seed scope is foreign")
    proof = dict(extension_proof or {})
    checkpoint_hash = proof.pop("checkpointHash", None)
    if not checkpoint_hash or checkpoint_hash != _digest(proof):
        raise InputSyncError("extension checkpoint hash is stale")
    proof["checkpointHash"] = checkpoint_hash
    if (proof.get("status") != "CHECKPOINTED_EXTENSION"
            or proof.get("sourceHash") != manifest.get("sourceHash")
            or proof.get("planHash") != manifest.get("planHash")
            or proof.get("feature") != feature):
        raise InputSyncError("extension checkpoint source/plan/feature is stale")
    if (proof.get("documentId") != target.get("documentId")
            or proof.get("resultVersion") != target.get("version")
            or proof.get("pageId") != target.get("pageId")
            or proof.get("elementId") != target.get("elementId")):
        raise InputSyncError("extension checkpoint element or target version is stale")
    created = proof.get("createdColumns") or {}
    if any(target["columnIds"].get(name) != column_id
           for name, column_id in created.items()):
        raise InputSyncError("extension checkpoint created IDs are foreign to the assigned receipt")
    readback_columns = (proof.get("readback") or {}).get("columns") or {}
    if set(readback_columns) != set(created):
        raise InputSyncError("extension checkpoint readback scope is stale")
    if checkpoint_hash in set((prior_seed or {}).get("extensionSeedCheckpoints") or []):
        raise InputSyncError("extension checkpoint replay is rejected")

    result = plan_seed(
        source_rows, current_rows, key_columns, row_id_column,
        prior_seed=prior_seed, snapshot=snapshot, column_types=column_types)
    current_index = _index(current_rows, key_columns, "current")
    source_index = _index(source_rows, key_columns, "source")
    authorized_updates = []
    authorized_by_token = {}
    for token, (key, wanted) in source_index.items():
        if token not in current_index:
            continue
        _observed_key, observed = current_index[token]
        safe = {}
        for name, column_id in created.items():
            proof_item = readback_columns[name]
            if proof_item.get("columnId") != column_id:
                raise InputSyncError("extension checkpoint readback column ID is stale")
            if name not in observed:
                raise InputSyncError("extension seed current readback omits a created column")
            if (proof_item.get("value") is None and observed[name] is None
                    and not _same(wanted[name], observed[name], (column_types or {}).get(name))):
                safe[name] = wanted[name]
        if safe:
            authorized_by_token[token] = set(safe)
            authorized_updates.append({
                "key": key, "rowId": observed[row_id_column], "changes": safe,
                "source": wanted,
                "current": {name: value for name, value in observed.items()
                            if name != row_id_column},
                "confirmedMigrationValue": (_prior_index(prior_seed).get(token) or {}).get(
                    "confirmedMigrationValue"),
                "extensionCheckpointHash": checkpoint_hash,
            })
    conflicts = []
    for conflict in result["conflicts"]:
        token = _key_token(conflict["key"])
        remaining = [name for name in conflict["columns"]
                     if name not in authorized_by_token.get(token, set())]
        if remaining:
            conflicts.append({**conflict, "columns": remaining})
    existing_updates = [update for update in result["updates"]
                        if not set(update["changes"]) & set(created)]
    for record in result["seedRecords"]:
        token = _key_token(record["key"])
        names = authorized_by_token.get(token)
        if names:
            wanted = source_index[token][1]
            pending = dict(record.get("pendingMigrationValue")
                           or record.get("confirmedMigrationValue") or {})
            pending.update({name: wanted[name] for name in names})
            pending.update({name: wanted[name] for name in key_columns})
            record["pendingMigrationValue"] = pending
    result["updates"] = existing_updates + authorized_updates
    result["conflicts"] = conflicts
    result["extensionSeedCheckpoints"] = list(
        (prior_seed or {}).get("extensionSeedCheckpoints") or [])
    # Planning consumes the creation proof before any write is attempted. The
    # caller persists this plan first, so an interrupted write cannot authorize
    # the same first-seed proof against a later null readback.
    result["extensionSeedCheckpoints"].append(checkpoint_hash)
    result["extensionSeedScope"] = seed_scope
    logical = {key: result[key] for key in (
        "sourceHash", "keyColumns", "rowIdColumn", "inserts", "updates",
        "conflicts", "unchanged", "orphans")}
    logical["extensionSeedCheckpoints"] = result["extensionSeedCheckpoints"]
    logical["extensionSeedScope"] = seed_scope
    result["planHash"] = _digest(logical)
    return result


def emit_workbook_wiring(manifest, staging_receipt):
    """Return approved REST-native join fragments bound to the artifact receipt."""
    architecture, _bindings, _artifacts = validate_artifact_receipt(manifest, staging_receipt)
    for feature in architecture["inputs"]:
        _approved_feature(manifest, staging_receipt, feature)
    return {
        "sourceHash": manifest["sourceHash"], "planHash": manifest["planHash"],
        "artifacts": staging_receipt["artifacts"],
        "wiring": build_operational_input_elements(
            architecture, target_bindings=staging_receipt["targetBindings"]),
    }


def _row_expression(row, variables, types):
    fields = []
    for name, variable in variables.items():
        if name in row:
            fields.append(f"{variable}: {_sdk_literal(row[name], types.get(name))}")
    return "{" + ", ".join(fields) + "}"


def emit_construction_program(manifest, staging_receipt, feature):
    """Emit construction only from an immutable manifest and approved artifact receipt."""
    input_spec, binding, artifact = _approved_feature(
        manifest, staging_receipt, feature, allow_input_only=True)
    spec = _construction_spec(input_spec, binding)
    seed_rows = input_spec.get("rows") or []
    _validate_spec(spec)
    if len(seed_rows) > MAX_BATCH_ROWS:
        raise InputSyncError("construction seed exceeds 2000 rows; create first, then emit checkpointed write chunks")
    columns = spec["columns"]
    types = {column["name"]: column["type"] for column in columns}
    lines = [
        f"# sourceHash={manifest['sourceHash']}", f"# planHash={manifest['planHash']}",
        f"# artifactHash={artifact['artifactHash']}", f"# feature={feature}",
        f"# targetDocumentId={binding['documentId']}", f"# targetVersion={binding['version']}",
        f"host = sigma.workbook.get_page({spec['pageId']!r})",
        "if not isinstance(host, Page):", "    raise RuntimeError('expected current page host')",
    ]
    schema = spec.get("writebackSchemaId")
    create = f"host.add_input_table({spec['connectionId']!r}"
    if schema:
        create += f", writeback_schema_id={schema!r}"
    frame = spec.get("frame") or [1, 1, 24, 12]
    if not (isinstance(frame, Sequence) and len(frame) == 4):
        raise InputSyncError("frame must contain x, y, width, height")
    lines += [f"created = {create})", f"created.set_name({spec['name']!r})",
              f"created.set_edit_mode({spec.get('editMode', 'draft')!r})",
              f"created.set_frame({frame[0]}, {frame[1]}, {frame[2]}, {frame[3]})"]
    for index, column in enumerate(columns):
        lines.append(f"created_c{index} = created.add_editable_column({column['name']!r}, {column['type']!r})")
    created_ids = ", ".join(f"created_c{index}.id()" for index in range(len(columns)))
    lines += [f"created_column_ids = [{created_ids}]",
              "system_columns = created.add_system_columns(['row_id'])",
              "created_id = created.id()",
              f"host = sigma.workbook.get_page({spec['pageId']!r})",
              "table = host.get_element(created_id)",
              "if not isinstance(table, InputTable):", "    raise RuntimeError('expected input table')"]
    variables = {}
    for index, column in enumerate(columns):
        variable = f"c{index}"; variables[column["name"]] = variable
        lines += [f"{variable} = table.get_column(created_column_ids[{index}])",
                  f"if not isinstance({variable}, LiteralEditableColumn):",
                  f"    raise RuntimeError('expected editable column: {column['name']}')"]
    if seed_rows:
        lines.append("row_ids = table.upsert_rows([")
        lines.extend(f"    {_row_expression(row, variables, types)}," for row in seed_rows)
        lines.append("])")
    lines += ["print('inputTableId=' + table.id())"]
    for name, variable in variables.items():
        lines.append(f"print({('column:' + name + '=')!r} + {variable}.id())")
    return "\n".join(lines) + "\n"


def emit_write_programs(seed_plan, manifest, staging_receipt, feature,
                        max_batch_rows=MAX_BATCH_ROWS):
    """Emit writes bound to the manifest, approved artifact, and assigned target IDs."""
    if not 1 <= max_batch_rows <= MAX_BATCH_ROWS:
        raise InputSyncError("max_batch_rows must be between 1 and 2000")
    input_spec, target, artifact = _approved_feature(
        manifest, staging_receipt, feature, require_assigned=True, allow_input_only=True)
    seed_plan = normalize_seed_plan(seed_plan)
    if seed_plan["sourceHash"] != artifact["seedHash"]:
        raise InputSyncError("reconciliation source rows differ from approved seed rows")
    if seed_plan["keyColumns"] != input_spec["keyColumns"]:
        raise InputSyncError("reconciliation key scope differs from approved seed schema")
    logical_keys = ("sourceHash", "keyColumns", "rowIdColumn", "inserts", "updates",
                    "conflicts", "unchanged", "orphans")
    if any(key not in seed_plan for key in logical_keys):
        raise InputSyncError("reconciliation plan is incomplete")
    logical = {key: seed_plan[key] for key in logical_keys}
    if seed_plan.get("extensionSeedCheckpoints"):
        logical["extensionSeedCheckpoints"] = seed_plan["extensionSeedCheckpoints"]
        logical["extensionSeedScope"] = seed_plan.get("extensionSeedScope")
        expected_scope = {"sourceHash": manifest["sourceHash"], "planHash": manifest["planHash"],
                          "feature": feature, "documentId": target["documentId"],
                          "pageId": target["pageId"], "elementId": target["elementId"]}
        actual_scope = logical["extensionSeedScope"]
        extension_actions = any(item.get("extensionCheckpointHash")
                                for item in seed_plan["updates"])
        # Legacy d19 consumed ledgers did not carry a scope. A fresh ordinary
        # reconciliation may retain that historical ledger, but it must never
        # turn an unscoped old creation proof into authorized extension writes.
        if ((actual_scope is None and extension_actions)
                or (actual_scope is not None and actual_scope != expected_scope)):
            raise InputSyncError("reconciliation extension seed scope is foreign")
    if _digest(logical) != seed_plan.get("planHash"):
        raise InputSyncError("reconciliation plan digest is stale")
    approved_rows = _index(input_spec.get("rows") or [], input_spec["keyColumns"], "approved")
    action_keys = set()
    for action in seed_plan["updates"] + seed_plan["inserts"]:
        token = _key_token(action.get("key"))
        if token not in approved_rows or token in action_keys:
            raise InputSyncError("reconciliation action has a foreign or duplicate source key")
        action_keys.add(token)
        wanted = approved_rows[token][1]
        if _digest(action.get("source")) != _digest(wanted):
            raise InputSyncError("reconciliation action source differs from approved rows")
        if "changes" in action:
            if action.get("rowId") is None or not isinstance(action["changes"], dict):
                raise InputSyncError("reconciliation update requires an observed row ID and changes")
            if any(name in input_spec["keyColumns"] or name not in wanted
                   or _digest(value) != _digest(wanted[name])
                   for name, value in action["changes"].items()):
                raise InputSyncError("reconciliation changes differ from approved source values")
    actions = [("update", item) for item in seed_plan.get("updates", [])]
    actions += [("insert", item) for item in seed_plan.get("inserts", [])]
    columns = dict(target["columnIds"])
    types = {column["name"]: column["type"] for column in input_spec["columns"]}
    programs = []
    for offset in range(0, len(actions), max_batch_rows):
        chunk = actions[offset:offset + max_batch_rows]
        chunk_index = offset // max_batch_rows
        checkpoint = _digest({"sourceHash": seed_plan["sourceHash"],
                              "planHash": seed_plan["planHash"],
                              "approvedSourceHash": manifest["sourceHash"],
                              "approvedPlanHash": manifest["planHash"],
                              "artifactHash": artifact["artifactHash"],
                              "target": target, "chunkIndex": chunk_index,
                              "actions": chunk})
        lines = [f"# sourceHash={manifest['sourceHash']}", f"# planHash={manifest['planHash']}",
                 f"# reconciliationSourceHash={seed_plan['sourceHash']}",
                 f"# reconciliationPlanHash={seed_plan['planHash']}",
                 f"# artifactHash={artifact['artifactHash']}", f"# feature={feature}",
                 f"# targetDocumentId={target['documentId']}",
                 f"# targetVersion={target['version']}",
                 f"# checkpointId={checkpoint}",
                 f"host = sigma.workbook.get_page({target['pageId']!r})",
                 "if not isinstance(host, Page):", "    raise RuntimeError('expected current page host')",
                 f"table = host.get_element({target['elementId']!r})",
                 "if not isinstance(table, InputTable):", "    raise RuntimeError('expected input table')"]
        variables = {}
        for index, (name, column_id) in enumerate(columns.items()):
            variable = f"c{index}"; variables[name] = variable
            lines += [f"{variable} = table.get_column({column_id!r})",
                      f"if not isinstance({variable}, LiteralEditableColumn):",
                      f"    raise RuntimeError('expected editable column: {name}')"]
        update_rows = [item for kind, item in chunk if kind == "update"]
        insert_rows = [item for kind, item in chunk if kind == "insert"]
        if update_rows:
            lines.append("table.update_rows([")
            for item in update_rows:
                lines.append(f"    ({item['rowId']!r}, {_row_expression(item['changes'], variables, types)}),")
            lines.append("])")
        if insert_rows:
            lines.append("row_ids = table.upsert_rows([")
            lines.extend(f"    {_row_expression(item['source'], variables, types)}," for item in insert_rows)
            lines.append("])")
        lines.append(f"print({'checkpointId=' + checkpoint!r})")
        programs.append({"chunkIndex": chunk_index, "checkpointId": checkpoint,
                         "artifactHash": artifact["artifactHash"], "feature": feature,
                         "targetBinding": target, "actionCount": len(chunk),
                         "program": "\n".join(lines) + "\n"})
    return programs


def build_shared_input_architecture(plan, *, connection_id, folder_id, workflows):
    """Build only the selected source workbook's hash-bound input architecture."""
    if not connection_id or not folder_id:
        raise InputSyncError("connection_id and folder_id are required target scope")
    if isinstance(workflows, str):
        workflows = [workflows]
    selected = list(dict.fromkeys(workflows or []))
    unknown = set(selected) - {"sales", "expense", "research"}
    if not selected or unknown:
        raise InputSyncError("workflows must select sales, expense, and/or research")
    if "research" in selected:
        include_research_line_input_literals(plan)
    shared_sources = plan.get("sharedInputSources") or {}
    architecture = {
        "workflows": selected,
        "targetScope": {"connectionId": connection_id, "folderId": folder_id},
        "mappedFeatures": [], "featureToInput": {}, "inputs": {}, "joins": {},
        "workbookWiring": {}, "calculations": {}, "provenance": {},
        "acceptance": {"persistence": "reopen/refresh and query unique key counts after each restore"},
        "acceptanceChecks": [],
    }
    if "sales" in selected:
        source = shared_sources.get("salesSettings") or {}
        if (source.get("sourceBinding") != "Assumptions!F2"
                or not isinstance(source.get("rows"), list) or len(source["rows"]) != 1):
            raise InputSyncError("sales plan requires validated Assumptions!F2 sharedInputSources")
        if (source["rows"][0].get("Setting") != "AsOfDate"
                or source["rows"][0].get("AsOfDate") is None):
            raise InputSyncError("sales source row must bind AsOfDate to Assumptions!F2")
        plan_seed(source["rows"], [], ["Setting"], "Row ID")
        architecture["inputs"]["salesSettings"] = {
            "kind": "input-table", "name": "Sales Settings", "keyColumns": ["Setting"],
            "editMode": "published-explore", "frame": [1, 4, 24, 10],
            "connectionId": connection_id, "sourceBinding": source["sourceBinding"],
            "rows": source["rows"],
            "columns": [{"name": "Setting", "type": "text", "provenance": "source"},
                        {"name": "AsOfDate", "type": "datetime", "provenance": "source"}],
        }
        architecture["mappedFeatures"] += ["sales-as-of-date", "sales-timing-status-day-grain"]
        architecture["featureToInput"].update({
            "sales-as-of-date": "salesSettings",
            "sales-timing-status-day-grain": "salesSettings",
        })
        architecture["joins"]["sales"] = {
            "type": "left_outer", "key": "constant setting scope", "cardinality": "many-to-one"}
        architecture["workbookWiring"]["salesSource"] = {
            "elementId": source.get("sourceElementId", "salesSource"),
            "name": source.get("sourceElementName", "Sales Source"),
            "consumerSourceElementId": "salesWithSettings"}
        architecture["calculations"]["TimingStatus"] = (
            'If([Stage] = "Closed Won" or [Stage] = "Closed Lost", "Closed", '
            'If(DateTrunc("day", [Close Date]) < DateTrunc("day", [AsOfDate]), '
            '"Slipped", "Open"))')
        architecture["provenance"]["dayGrainTimingDecision"] = {
            "source": '=IF(H2="Closed Won","Closed",IF(H2="Closed Lost","Closed",IF(C2<\'Assumptions\'!$F$2,"Slipped","Open")))',
            "replacement": "compare DateTrunc day for both Close Date and shared AsOfDate",
            "status": "reviewed-equivalence"}
        architecture["acceptance"]["sales"] = (
            "edit source-derived AsOfDate from 2026-06-30 to 2026-07-01, verify boundary rows, restore")
        architecture["acceptanceChecks"].append("sales-as-of-date-boundary")
    if "expense" in selected:
        source = shared_sources.get("expensePolicy") or {}
        if (source.get("sourceRange") != "Policy!A1:D7"
                or not isinstance(source.get("rows"), list) or not source["rows"]):
            raise InputSyncError("expense plan requires validated Policy!A1:D7 sharedInputSources")
        expected_policy_columns = {
            "Category", "Per-item Limit", "Receipt Threshold", "Policy Owner"}
        if any(set(row) != expected_policy_columns for row in source["rows"]):
            raise InputSyncError("expense policy rows must preserve all Policy!A1:D7 columns")
        plan_seed(source["rows"], [], ["Category"], "Row ID")
        architecture["inputs"]["expensePolicy"] = {
            "kind": "input-table", "name": "Expense Policy", "keyColumns": ["Category"],
            "editMode": "published-explore", "frame": [1, 4, 24, 12],
            "connectionId": connection_id, "sourceRange": source["sourceRange"],
            "rows": source["rows"],
            "columns": [{"name": "Category", "type": "text", "provenance": "source"},
                        {"name": "Per-item Limit", "type": "number", "provenance": "source"},
                        {"name": "Receipt Threshold", "type": "number", "provenance": "source"},
                        {"name": "Policy Owner", "type": "text", "provenance": "source"}],
            "unknownCategoryBehavior": "explicit-null-error",
            "duplicateOrMissingKeyBehavior": "block-before-join",
        }
        architecture["mappedFeatures"].append("expense-policy")
        architecture["featureToInput"]["expense-policy"] = "expensePolicy"
        architecture["joins"]["expense"] = {
            "type": "left_outer", "key": "Category", "cardinality": "many-to-one"}
        architecture["workbookWiring"]["expenseSource"] = {
            "elementId": source.get("sourceElementId", "expenseSource"),
            "name": source.get("sourceElementName", "Expense Source"),
            "consumerSourceElementId": "expensesWithPolicy"}
        architecture["calculations"]["PolicyExcess"] = (
            "If(IsNull([Per-item Limit]), Null, Greatest([Amount] - [Per-item Limit], 0))")
        architecture["acceptance"]["expense"] = (
            "edit source-derived Meals limit 90 to 400, verify all matching rows/counts, restore")
        architecture["acceptanceChecks"].append("expense-meals-limit-propagation")
        architecture["provenance"]["expense-cent-comparison"] = {
            "mappingKind": "reviewed-currency-replacement", "sourcePrecision": 2,
            "sourceComparison": "Abs(Recon Variance)>0.01",
            "replacement": "Abs(Round(Card Amount*100,0)-Round(Ledger Amount*100,0))>1",
            "storedAmounts": "preserved", "runtimeStatus": "PENDING_CENT_BOUNDARY_AND_NULL_UI_ACCEPTANCE"}
    if "research" in selected:
        source_inputs = list(plan.get("sourceInputs") or [])
        ids = [item.get("id") for item in source_inputs]
        cells = [item.get("sourceCellId") for item in source_inputs]
        if (any(not value for value in ids + cells) or len(set(ids)) != len(ids)
                or len(set(cells)) != len(cells)):
            raise InputSyncError("research sourceInputs require unique ids and sourceCellIds")
        bindings = {item["id"]: item["sourceCellId"] for item in source_inputs}
        architecture["inputs"]["researchModelInputs"] = {
            "kind": "input-table", "name": "Research Model Inputs", "keyColumns": ["Scope"],
            "connectionId": connection_id,
            "rows": [{"Scope": "shared", **{
                item["id"]: item.get("defaultValue") for item in source_inputs}}],
            "editableColumnBindings": list(bindings),
            "columns": [{"name": "Scope", "type": "text", "provenance": "migration"}] + [
                {"name": item["id"], "type": sigma_input_type(item.get("defaultValue")),
                 "provenance": item["sourceCellId"]} for item in source_inputs],
            "sourceCellBindings": bindings, "joinGrain": ["Scope"],
            "excludedFromGrouping": ["Row ID", "Created At", "Created By", "Updated At", "Updated By"],
        }
        architecture["mappedFeatures"] += ["research-model-inputs", "research-literal-overrides"]
        architecture["featureToInput"].update({
            "research-model-inputs": "researchModelInputs",
            "research-literal-overrides": "researchModelInputs"})
        architecture["joins"]["research"] = {
            "type": "left_outer", "key": "constant Scope", "cardinality": "many-to-one"}
        architecture["acceptance"]["research"] = (
            "edit growth and literal-year overrides, verify downstream years, restore")
        architecture["acceptanceChecks"] += [
            "research-growth-propagation", "research-literal-override-propagation"]
    return architecture


def _rest_columns(spec, prefix):
    return [{"id": f"{prefix}_{index}", "name": column["name"], "type": column["type"]}
            for index, column in enumerate(spec["columns"])]


def build_operational_input_elements(architecture, target_bindings=None):
    """Build executable ordinary inputs and native join/calculation fragments."""
    if architecture.get("nativeWiring") is not None:
        def resolve(value):
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            if isinstance(value, str) and value.startswith("@input:"):
                feature = value[len("@input:"):]
                if feature not in architecture["inputs"]:
                    raise InputSyncError("native wiring references a foreign input")
                if target_bindings is None:
                    return value
                binding = target_bindings.get(feature) or {}
                if not binding.get("elementId"):
                    raise InputSyncError(f"assigned target binding required for {feature}")
                return binding["elementId"]
            return value
        return resolve(architecture["nativeWiring"])
    inputs = architecture.get("inputs") or {}
    connection = (architecture.get("targetScope") or {}).get("connectionId")
    wiring = architecture.get("workbookWiring") or {}
    if not connection:
        raise InputSyncError("approved target connection is required")
    elements, consumers, validations = [], {}, {}
    def resolved_source(key):
        source = copy.deepcopy(wiring.get(key) or {})
        feature = source.pop("inputFeature", None)
        if feature:
            if target_bindings is None:
                source["elementId"] = f"@input:{feature}"
            else:
                binding = target_bindings.get(feature) or {}
                if not binding.get("elementId"):
                    raise InputSyncError(f"assigned target binding required for {feature}")
                source["elementId"] = binding["elementId"]
        return source
    if "salesSettings" in inputs:
        spec = inputs["salesSettings"]
        source = resolved_source("salesSource")
        if not source.get("elementId") or not source.get("name"):
            raise InputSyncError("approved sales source wiring is required")
        elements.extend([
            {"id": "salesSettings", "kind": "input-table", "name": spec["name"],
             "inputMode": "edit", "source": {"kind": "empty", "connectionId": connection},
             "columns": _rest_columns(spec, "sales_setting")},
            {"id": "salesInputBase", "kind": "table", "name": "Sales Input Base",
             "source": {"kind": "table", "elementId": source["elementId"]},
             "columns": [
                 {"id": "sales_" + str(index), "name": name,
                  "formula": f"[{source['name']}/{source_name}]"}
                 for index, (name, source_name) in enumerate([
                     ("Opportunity ID", "Opportunity ID"), ("Created Date", "Created Date"),
                     ("Close Date", "Expected Close"), ("Account", "Account"),
                     ("Region", "Region"), ("Segment", "Segment"), ("Rep", "Rep"),
                     ("Stage", "Stage"), ("Probability", "Probability"), ("ACV", "ACV"),
                     ("Forecast Category", "Forecast Category"),
                     ("Weighted ACV", "Weighted ACV"), ("Cycle Days", "Cycle Days")])
             ] + [
                 {"id": "sales_setting", "name": "Setting", "formula": '"AsOfDate"'}]},
            {"id": "salesWithSettings", "kind": "table", "name": "Sales With Settings",
             "source": {"kind": "join", "name": "SalesJoin",
                        "primarySource": {"kind": "table", "elementId": "salesInputBase"},
                        "joins": [{"name": "Settings", "joinType": "left-outer",
                                   "left": {"kind": "table", "elementId": "salesInputBase"},
                                   "right": {"kind": "table", "elementId": "salesSettings"},
                                   "columns": [{"left": "[Setting]", "right": "[Setting]"}]}]},
             "columns": [
                 {"id": "sales_join_" + str(index), "name": name,
                  "formula": f"[SalesJoin/{name}]"}
                 for index, name in enumerate([
                     "Opportunity ID", "Created Date", "Close Date", "Account", "Region",
                     "Segment", "Rep", "Stage", "Probability", "ACV", "Forecast Category",
                     "Weighted ACV", "Cycle Days"])
             ] + [
                 {"id": "sales_join_asof", "name": "AsOfDate", "formula": "[Settings/AsOfDate]"},
                 {"id": "sales_timing", "name": "TimingStatus",
                  "formula": architecture["calculations"]["TimingStatus"].replace(
                      "[AsOfDate]", "[Settings/AsOfDate]")}]},
        ])
        consumers["sales"] = source["consumerSourceElementId"]
        validations["salesSettings"] = {"uniqueKeys": ["Setting"]}
    if "expensePolicy" in inputs:
        spec = inputs["expensePolicy"]
        source = resolved_source("expenseSource")
        if not source.get("elementId") or not source.get("name"):
            raise InputSyncError("approved expense source wiring is required")
        # Excel arithmetic reads a cleared numeric input as zero; the raw input stays null.
        card_for_arithmetic = "Coalesce([ExpenseJoin/Card Amount], 0)"
        ledger_for_arithmetic = "Coalesce([ExpenseJoin/Ledger Amount], 0)"
        elements.extend([
            {"id": "expensePolicy", "kind": "input-table", "name": spec["name"],
             "inputMode": "edit", "source": {"kind": "empty", "connectionId": connection},
             "columns": _rest_columns(spec, "expense_policy")},
            {"id": "expenseInputBase", "kind": "table", "name": "Expense Input Base",
             "source": {"kind": "table", "elementId": source["elementId"]},
             "columns": [
                 {"id": "expense_" + str(index), "name": name,
                  "formula": f"[{source['name']}/{name}]"}
                 for index, name in enumerate([
                     "Expense ID", "Date", "Employee", "Department", "Category", "Vendor",
                     "Amount", "Receipt Status", "Approval Status", "Card Amount", "Ledger Amount"])]},
            {"id": "expensesWithPolicy", "kind": "table", "name": "Expenses With Policy",
             "source": {"kind": "join", "name": "ExpenseJoin",
                        "primarySource": {"kind": "table", "elementId": "expenseInputBase"},
                        "joins": [{"name": "Policy", "joinType": "left-outer",
                                   "left": {"kind": "table", "elementId": "expenseInputBase"},
                                   "right": {"kind": "table", "elementId": "expensePolicy"},
                                   "columns": [{"left": "[Category]", "right": "[Category]"}]}]},
             "columns": [
                 {"id": "expense_join_" + str(index), "name": name,
                  "formula": f"[ExpenseJoin/{name}]"}
                 for index, name in enumerate([
                     "Expense ID", "Date", "Employee", "Department", "Category", "Vendor",
                     "Amount", "Receipt Status", "Approval Status", "Card Amount", "Ledger Amount"])
             ] + [
                 {"id": "expense_join_limit", "name": "Per-item Limit", "formula": "[Policy/Per-item Limit]"},
                 {"id": "expense_join_receipt", "name": "Receipt Threshold", "formula": "[Policy/Receipt Threshold]"},
                 {"id": "expense_join_owner", "name": "Policy Owner", "formula": "[Policy/Policy Owner]"},
                 {"id": "expense_policy_status", "name": "PolicyMatchStatus",
                  "formula": 'If(IsNull([Policy/Category]), "ERROR: missing policy", "Matched")'},
                 {"id": "expense_recon", "name": "Recon Variance",
                  "formula": f"{card_for_arithmetic} - {ledger_for_arithmetic}"},
                 {"id": "expense_excess", "name": "PolicyExcess",
                  "formula": "If(IsNull([Policy/Category]), Null, Greatest([ExpenseJoin/Amount] - [Policy/Per-item Limit], 0))"},
                 {"id": "expense_exception", "name": "Exception",
                  "formula": ('If(IsNull([Policy/Category]), Null, '
                              f'If(Abs(Round({card_for_arithmetic} * 100, 0) - Round({ledger_for_arithmetic} * 100, 0)) > 1, "RECON", '
                              'If([PolicyExcess] > 0, "OVER LIMIT", '
                              'If([ExpenseJoin/Receipt Status] = "Missing", "MISSING RECEIPT", '
                              'If([ExpenseJoin/Approval Status] <> "Approved", "PENDING", "CLEAR")))))')}]},
        ])
        consumers["expense"] = source["consumerSourceElementId"]
        validations["expensePolicy"] = {"uniqueKeys": ["Category"]}
    return {"elements": elements, "consumerSources": consumers,
            "preJoinValidation": validations}
