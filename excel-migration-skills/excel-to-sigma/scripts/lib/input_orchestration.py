"""Source/plan/target-bound gates for shared-input staging and completion."""
from __future__ import annotations

import json

try:
    from .input_sync import build_artifact_records
    from .migration_gate import gate_completion_manifest, gate_staging_manifest, source_issue_hash
except ImportError:
    from input_sync import build_artifact_records
    from migration_gate import gate_completion_manifest, gate_staging_manifest, source_issue_hash


def _architecture(value):
    if not isinstance(value, dict):
        raise ValueError("approved architecture must be an object")
    architecture = value.get("sharedInputArchitecture", value)
    if not isinstance(architecture, dict) or not isinstance(architecture.get("inputs"), dict):
        raise ValueError("approved architecture is missing sharedInputArchitecture.inputs")
    return architecture


def _same_hashes(manifest, value, label):
    if value.get("sourceHash") != manifest.get("sourceHash"):
        raise ValueError(f"{label} sourceHash is stale")
    if value.get("planHash") != manifest.get("planHash"):
        raise ValueError(f"{label} planHash is stale")


def _typed_natural_keys(rows, key_columns, label):
    if not isinstance(rows, list):
        raise ValueError(f"{label} natural keys are required")
    expected_fields = set(key_columns)
    tokens = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValueError(f"{label} natural keys do not match approved key columns")
        key = []
        for column in key_columns:
            value = row[column]
            if value is None:
                raise ValueError(f"{label} natural keys cannot contain null")
            if isinstance(value, bool):
                value_type = "bool"
            elif isinstance(value, int):
                value_type = "int"
            elif isinstance(value, float):
                value_type = "float"
            elif isinstance(value, str):
                value_type = "str"
            else:
                raise ValueError(f"{label} natural keys contain an unsupported value")
            key.append({"type": value_type, "value": value})
        tokens.append(json.dumps(key, sort_keys=True, separators=(",", ":")))
    if len(tokens) != len(set(tokens)):
        raise ValueError(f"{label} natural keys contain duplicates")
    return set(tokens)


def gate_input_staging(manifest, approval, plan_or_architecture, source_gate_evidence):
    """Run PR1 review, preserve the real source gate, and bind exact artifacts."""
    gate_staging_manifest(manifest, approval)
    architecture = _architecture(plan_or_architecture)
    for field in ("sourceHash", "planHash", "reviewer", "mappedFeatures", "targetBindings"):
        if not approval.get(field):
            raise ValueError(f"approved staging requires {field}")
    if not isinstance(approval["reviewer"], str) or not approval["reviewer"].strip():
        raise ValueError("approved staging requires a named reviewer")
    _same_hashes(manifest, approval, "approval")
    if set(approval["mappedFeatures"]) != set(architecture.get("mappedFeatures") or []):
        raise ValueError("mappedFeatures must exactly match the approved architecture")
    if not isinstance(source_gate_evidence, dict):
        raise ValueError("source gate evidence is required")
    if source_gate_evidence.get("sourceSha256") != manifest.get("sourceHash"):
        raise ValueError("source gate evidence sourceHash is stale")
    source_status = source_gate_evidence.get("status")
    review_status = source_gate_evidence.get("reviewStatus")
    issues = source_gate_evidence.get("issues") or []
    if (source_status == "BLOCKED" or review_status == "BLOCKED"
            or any(issue.get("severity") == "blocker" for issue in issues)):
        raise ValueError("source audit is BLOCKED")
    if review_status not in {"NOT_REQUIRED", "DISPOSITIONED", "PENDING_STAGING"}:
        raise ValueError("source audit review is unresolved")
    if issues:
        source_approval = approval.get("sourceReviewApproval") or {}
        if (source_approval.get("status") != "approved_for_staging"
                or source_approval.get("issues") != issues):
            raise ValueError("sourceReviewApproval must explicitly approve the exact audited issue scope")
        # A staging review never marks a source feature verified/dispositioned.
        review_status = "PENDING_STAGING"
    artifacts = build_artifact_records(manifest, architecture, approval["targetBindings"])
    return {
        "status": "APPROVED_STAGING", "sourceHash": approval["sourceHash"],
        "planHash": approval["planHash"], "reviewer": approval["reviewer"],
        "mappedFeatures": sorted(approval["mappedFeatures"]),
        "sourceStatus": source_status, "sourceReviewStatus": review_status,
        "sourceAuditEvidenceId": source_gate_evidence.get("evidenceId"),
        "pendingSourceIssues": issues,
        "sourceReviewRequirements": [
            {"issue": issue, "issueHash": source_issue_hash(issue)} for issue in issues],
        "targetBindings": approval["targetBindings"], "artifacts": artifacts,
    }


def gate_input_only_staging(manifest, approval, source_input_plan, source_gate_evidence, *, source_path):
    """Explicit first phase: seed source literals while every formula stays pending.

    This receipt is accepted only by ordinary input creation/seed emitters. It
    cannot pass native construction or completion. Default full staging retains
    its original requirement that every formula mapping has been reviewed.
    """
    try:
        from .migration_manifest import validate_manifest
        from .source_inputs import validate_source_input_plan
    except ImportError:
        from migration_manifest import validate_manifest
        from source_inputs import validate_source_input_plan
    validate_manifest(manifest, source_path, allow_input_only=True)
    validate_source_input_plan(source_input_plan, source_path)
    projection = manifest.get("planProjection") or {}
    if (projection.get("executionScope") != "input-tables-only"
            or approval.get("status") != "approved_for_staging"
            or approval.get("scope") != "input-tables-only"
            or "nativeCalculationPlan" in projection or "nativeReviewApproval" in projection):
        raise ValueError("explicit input-tables-only plan and approval are required")
    if (projection.get("inputPlanHash") != source_input_plan["inputPlanHash"]
            or projection.get("sharedInputArchitecture") != source_input_plan["sharedInputArchitecture"]
            or source_input_plan["sourceSha256"] != manifest["sourceHash"]):
        raise ValueError("input-only source/input/manifest identity is stale")
    for field in ("owner", "reviewer"):
        if not isinstance(approval.get(field), str) or not approval[field].strip():
            raise ValueError("input-only staging requires a named " + field)
    _same_hashes(manifest, approval, "input-only approval")
    formula_ids = {record["id"] for record in manifest["formulaCells"]}
    for field in ("reviewItems", "pendingFormulaIds"):
        items = approval.get(field)
        if not isinstance(items, list) or len(items) != len(formula_ids) or set(items) != formula_ids:
            raise ValueError("input-only staging must retain every pending formula: " + field)
    if any(record.get("targetMapping") or record.get("verification") or record.get("evidence")
           for record in manifest["formulaCells"]):
        raise ValueError("input-only staging cannot assert formula mapping or runtime evidence")
    architecture = source_input_plan["sharedInputArchitecture"]
    if set(approval.get("mappedFeatures") or []) != set(architecture["mappedFeatures"]):
        raise ValueError("mappedFeatures must exactly match the approved input architecture")
    target = manifest.get("target") or {}
    if not target.get("documentId") or type(target.get("version")) is not int:
        raise ValueError("input-only staging requires an actual target document/version")
    bindings = approval.get("targetBindings") or {}
    for binding in bindings.values():
        if (binding.get("documentId") != target["documentId"]
                or binding.get("version") != target["version"]):
            raise ValueError("input-only target binding is foreign or stale")
    for spec in architecture["inputs"].values():
        # The system row ID is an additional column in the current SDK.
        if not 1 <= len(spec["columns"]) <= 63:
            raise ValueError("input-only schema plus system row ID exceeds the 64-column limit")
        frame = spec.get("frame", [1, 1, 24, 12])
        if len(frame) != 4 or not 1 <= frame[0] or not 1 <= frame[2] <= 24 or frame[0] + frame[2] > 25:
            raise ValueError("input-only frame exceeds the 24-column SDK layout")
    if not isinstance(source_gate_evidence, dict) or source_gate_evidence.get("sourceSha256") != manifest["sourceHash"]:
        raise ValueError("input-only source gate evidence is missing or stale")
    issues = source_gate_evidence.get("issues") or []
    if (source_gate_evidence.get("status") == "BLOCKED"
            or source_gate_evidence.get("reviewStatus") not in {"NOT_REQUIRED", "DISPOSITIONED", "PENDING_STAGING"}
            or any(issue.get("severity") == "blocker" for issue in issues)):
        raise ValueError("input-only source audit is blocked or unresolved")
    if issues:
        review = approval.get("sourceReviewApproval") or {}
        if review.get("status") != "approved_for_staging" or review.get("issues") != issues:
            raise ValueError("input-only sourceReviewApproval must approve the exact audited issue scope")
    artifacts = build_artifact_records(manifest, architecture, bindings)
    return {"status": "APPROVED_INPUT_STAGING", "scope": "input-tables-only",
            "sourceHash": manifest["sourceHash"], "planHash": manifest["planHash"],
            "owner": approval["owner"], "reviewer": approval["reviewer"],
            "mappedFeatures": sorted(architecture["mappedFeatures"]),
            "pendingFormulaIds": sorted(formula_ids), "runtimeStatus": "UNVERIFIED_CANDIDATE",
            "sourceStatus": source_gate_evidence["status"],
            "sourceReviewStatus": "PENDING_STAGING" if issues else source_gate_evidence["reviewStatus"],
            "pendingSourceIssues": issues,
            "sourceReviewRequirements": [{"issue": issue, "issueHash": source_issue_hash(issue)} for issue in issues],
            "targetBindings": bindings, "artifacts": artifacts}


def _validate_target_bindings(manifest, receipt, runtime_evidence, architecture):
    receipt_bindings = receipt.get("targetBindings") or {}
    if runtime_evidence.get("targetBindings") != receipt_bindings:
        raise ValueError("runtime target bindings do not match approved target bindings")
    expected_tables = set(architecture["inputs"])
    if set(receipt_bindings) != expected_tables:
        raise ValueError("approved target bindings must exactly cover input tables")
    target = runtime_evidence.get("target") or {}
    manifest_target = manifest.get("target") or {}
    if target != manifest_target or not target.get("documentId") or target.get("version") is None:
        raise ValueError("runtime target document/version does not match manifest")
    for name, binding in receipt_bindings.items():
        if (binding.get("documentId") != target["documentId"]
                or binding.get("version") != target["version"]
                or not binding.get("pageId") or not binding.get("elementId")):
            raise ValueError(f"target binding is incomplete or stale for {name}")
        expected_columns = {column["name"] for column in architecture["inputs"][name]["columns"]}
        if set(binding.get("columnIds") or {}) != expected_columns:
            raise ValueError(f"target columns are incomplete or stale for {name}")


def gate_input_completion(manifest, staging_receipt, runtime_evidence):
    """Require complete feature/table/readback coverage for the approved live target."""
    gate_completion_manifest(manifest)
    architecture = _architecture((manifest.get("planProjection") or {}).get(
        "sharedInputArchitecture", {}))
    if staging_receipt.get("status") != "APPROVED_STAGING":
        raise ValueError("completion requires an approved staging receipt")
    _same_hashes(manifest, staging_receipt, "staging receipt")
    _same_hashes(manifest, runtime_evidence, "runtime evidence")
    if runtime_evidence.get("status") != "passed":
        raise ValueError("runtime evidence has not passed")
    expected_features = set(architecture.get("mappedFeatures") or [])
    if (set(staging_receipt.get("mappedFeatures") or []) != expected_features
            or set(runtime_evidence.get("mappedFeatures") or []) != expected_features):
        raise ValueError("runtime mapped features must exactly cover approved feature scope")
    expected_artifacts = build_artifact_records(
        manifest, architecture, staging_receipt.get("targetBindings") or {})
    if staging_receipt.get("artifacts") != expected_artifacts:
        raise ValueError("staging receipt artifacts are stale")
    _validate_target_bindings(manifest, staging_receipt, runtime_evidence, architecture)

    expected_tables = set(architecture["inputs"])
    tables = runtime_evidence.get("tables")
    if not isinstance(tables, dict) or set(tables) != expected_tables:
        raise ValueError("runtime table evidence must exactly cover approved input tables")
    for name, spec in architecture["inputs"].items():
        item = tables[name]
        for field in ("querySnapshotId", "readbackId", "persistenceReadbackId"):
            if not item.get(field):
                raise ValueError(f"runtime table evidence for {name} requires {field}")
        if item.get("keyColumns") != spec.get("keyColumns"):
            raise ValueError(f"runtime key columns are stale for {name}")
        expected_count = len(spec.get("rows") or [])
        if ((expected_count < 1 and spec.get("emptySchema") is not True)
                or type(item.get("rows")) is not int
                or type(item.get("distinct")) is not int
                or item["rows"] != expected_count or item["distinct"] != expected_count):
            raise ValueError(f"runtime evidence does not match approved row count for {name}")
        key_columns = spec["keyColumns"]
        expected_keys = _typed_natural_keys(
            [{key: row[key] for key in key_columns} for row in spec["rows"]],
            key_columns, f"approved {name}")
        actual_keys = _typed_natural_keys(
            item.get("naturalKeys"), key_columns, f"runtime {name}")
        if actual_keys != expected_keys:
            raise ValueError(f"runtime natural keys do not match approved rows for {name}")

    checkpoints = runtime_evidence.get("checkpointBindings")
    if not isinstance(checkpoints, list) or not checkpoints:
        raise ValueError("checkpoint bindings are required")
    covered = set()
    target = runtime_evidence["target"]
    for item in checkpoints:
        feature = item.get("feature")
        if feature not in expected_tables or not item.get("checkpointId"):
            raise ValueError("checkpoint binding has an unknown feature")
        binding = staging_receipt["targetBindings"][feature]
        if (item.get("artifactHash") != expected_artifacts[feature]["artifactHash"]
                or item.get("documentId") != target["documentId"]
                or item.get("version") != target["version"]
                or item.get("elementId") != binding["elementId"]):
            raise ValueError(f"checkpoint binding is stale for {feature}")
        covered.add(feature)
    if covered != expected_tables:
        raise ValueError("checkpoint bindings must exactly cover approved input tables")

    checks = runtime_evidence.get("acceptanceChecks")
    expected_checks = set(architecture.get("acceptanceChecks") or [])
    if not isinstance(checks, list) or {check.get("id") for check in checks} != expected_checks:
        raise ValueError("acceptance checks must exactly cover approved feature checks")
    for check in checks:
        if (check.get("status") != "passed" or check.get("restored") is not True
                or not check.get("evidenceId")
                or check.get("documentId") != target["documentId"]
                or check.get("version") != target["version"]
                or check.get("sourceHash") != manifest["sourceHash"]
                or check.get("planHash") != manifest["planHash"]):
            raise ValueError(f"acceptance check is incomplete or stale: {check.get('id')}")
    return {
        "status": "VERIFIED_COMPLETE", "target": target,
        "tableReadbackIds": {name: item["readbackId"] for name, item in tables.items()},
        "checkpointIds": [item["checkpointId"] for item in checkpoints],
        "acceptanceEvidenceIds": [item["evidenceId"] for item in checks],
    }
