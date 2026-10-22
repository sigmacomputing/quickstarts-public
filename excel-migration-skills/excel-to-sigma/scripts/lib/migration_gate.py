"""Source-bound audit gate shared by Excel migration entrypoints."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

try:
    from .migration_manifest import validate_completion, validate_staging_approval
except ImportError:  # standalone tests/scripts that place lib directly on sys.path
    from migration_manifest import validate_completion, validate_staging_approval

try:
    from .xlsx_audit import audit_workbook
except ImportError:  # direct import when scripts/lib itself is on sys.path
    from xlsx_audit import audit_workbook


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MigrationGateError(RuntimeError):
    """A source cannot proceed through inference or migration."""

    def __init__(self, message, *, report=None, unresolved_codes=(), exit_code=1):
        super().__init__(message)
        self.report = report or {}
        self.unresolved_codes = tuple(unresolved_codes)
        self.exit_code = exit_code


def source_sha256(path):
    """Return the lowercase SHA256 identity of a source workbook."""
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_dispositions(path):
    if not path:
        return None
    record_path = Path(path)
    if not record_path.is_file():
        raise MigrationGateError(f"review dispositions file not found: {record_path}")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MigrationGateError(f"invalid review dispositions file {record_path}: {error}") from error
    if not isinstance(record, dict):
        raise MigrationGateError("review dispositions must be a JSON object")
    return record


def _review_index(record, digest):
    recorded_digest = record.get("sourceSha256")
    if not isinstance(recorded_digest, str) or recorded_digest.lower() != digest:
        raise MigrationGateError(
            "review dispositions sourceSha256 does not match the current source workbook"
        )
    items = record.get("issues")
    if not isinstance(items, list):
        raise MigrationGateError("review dispositions must contain an issues array")
    indexed = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            continue
        indexed[item["code"]] = item
    return indexed


def _complete_disposition(item):
    return (
        isinstance(item, dict)
        and isinstance(item.get("owner"), str)
        and bool(item["owner"].strip())
        and isinstance(item.get("disposition"), str)
        and bool(item["disposition"].strip())
        and item.get("verified") is True
    )


def plan_review_issues(plan):
    """Return review issues created by inference rather than OOXML inventory."""
    issues = []
    frozen = int((plan.get("parity") or {}).get("frozen") or 0)
    if frozen:
        issues.append({
            "code": "CACHED_FORMULA_FALLBACK",
            "severity": "review",
            "route": "formula-reimplementation-and-parity-review",
            "message": (
                f"{frozen} formula cell(s) use cached Excel values instead of live Sigma formulas."
            ),
            "evidence": [f"frozen={frozen}"],
        })
    needs_review = int((plan.get("summary") or {}).get("needs_review") or 0)
    if needs_review:
        issues.append({
            "code": "INFERENCE_REVIEW_REQUIRED",
            "severity": "review",
            "route": "canonical-formula-review",
            "message": f"{needs_review} inferred line item(s) still require formula review.",
            "evidence": [f"needs_review={needs_review}"],
        })
    # Issues a plan drafter raised from source shape (e.g. FLAT_CARRY_POLICY).
    issues.extend(dict(issue) for issue in plan.get("draftReviewIssues") or [])
    return issues


def gate_source(source, dispositions_path=None, additional_issues=(), draft=False):
    """Audit ``source`` and require source-bound dispositions for every review issue.

    ``draft=True`` is for local/dry-run builds: unresolved review issues are
    returned as ``reviewStatus: "DRAFT_PENDING"`` with ``pendingReview`` codes
    instead of raising. A supplied but invalid dispositions file still raises,
    and blockers always raise.
    """
    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise MigrationGateError(f"source workbook not found: {source_path}")
    source_path = source_path.resolve()
    digest = source_sha256(source_path)
    report = audit_workbook(source_path)
    report["source"] = str(source_path)
    report["sourceSha256"] = digest

    extra = [dict(issue) for issue in additional_issues]
    if extra:
        report["issues"] = list(report.get("issues", [])) + extra
        if report["status"] == "AUTO":
            report["status"] = "REVIEW_REQUIRED"

    blockers = [item for item in report.get("issues", []) if item.get("severity") == "blocker"]
    if report.get("status") == "BLOCKED" or blockers:
        codes = [item.get("code", "UNKNOWN_BLOCKER") for item in blockers]
        report["status"] = "BLOCKED"
        report["reviewStatus"] = "BLOCKED"
        raise MigrationGateError(
            "migration blocked by source audit: " + ", ".join(codes),
            report=report,
            unresolved_codes=codes,
            exit_code=2,
        )

    review_issues = [item for item in report.get("issues", []) if item.get("severity") != "blocker"]
    if not review_issues:
        report["reviewStatus"] = "NOT_REQUIRED"
        return report

    required_codes = [item["code"] for item in review_issues]
    try:
        record = _load_dispositions(dispositions_path)
        if record is None:
            unresolved = required_codes
        else:
            indexed = _review_index(record, digest)
            unresolved = [
                item["code"] for item in review_issues
                if not _complete_disposition(indexed.get(item["code"]))
            ]
    except MigrationGateError as error:
        report["reviewStatus"] = "UNRESOLVED"
        raise MigrationGateError(
            str(error),
            report=report,
            unresolved_codes=required_codes,
            exit_code=1,
        ) from error
    if unresolved and draft:
        report["reviewStatus"] = "DRAFT_PENDING"
        report["pendingReview"] = unresolved
        return report
    if unresolved:
        report["reviewStatus"] = "UNRESOLVED"
        raise MigrationGateError(
            "migration review is unresolved: " + ", ".join(unresolved),
            report=report,
            unresolved_codes=unresolved,
            exit_code=1,
        )

    report["reviewStatus"] = "DISPOSITIONED"
    return report


def gate_plan_source(plan, *, source_arg=None, dispositions_path=None, plan_path=None, draft=False):
    """Resolve and gate the exact workbook used to create an inference/build plan."""
    expected_digest = plan.get("sourceSha256")
    if not isinstance(expected_digest, str) or not SHA256_RE.fullmatch(expected_digest.lower()):
        raise MigrationGateError(
            "plan is missing a valid sourceSha256; regenerate it from the source workbook"
        )

    if source_arg:
        source_path = Path(source_arg).expanduser()
    else:
        saved_path = plan.get("sourcePath")
        if not isinstance(saved_path, str) or not saved_path.strip():
            raise MigrationGateError("plan source is missing; provide --source or regenerate the plan")
        source_path = Path(saved_path).expanduser()
        if not source_path.is_absolute() and plan_path:
            source_path = Path(plan_path).expanduser().resolve().parent / source_path
    if not source_path.is_file():
        raise MigrationGateError(f"source workbook not found: {source_path}")
    source_path = source_path.resolve()

    actual_digest = source_sha256(source_path)
    if actual_digest != expected_digest.lower():
        raise MigrationGateError(
            "source workbook SHA256 does not match the plan sourceSha256; regenerate the plan"
        )
    report = gate_source(
        source_path,
        dispositions_path=dispositions_path,
        additional_issues=plan_review_issues(plan),
        draft=draft,
    )
    return source_path, report


def dispositions_for_source(path, source):
    """Resolve a batch review file, including ``<sha256>.json`` in a directory."""
    if not path:
        return None
    candidate = Path(path).expanduser()
    if candidate.is_dir():
        candidate = candidate / f"{source_sha256(source)}.json"
    return candidate


def gate_plan_staging_source(plan, *, source_arg=None, plan_path=None):
    """Audit exact source bytes, retaining review issues for explicit test staging.

    This does not accept dispositions or assert verification. Only the strict
    source gate's audited UNRESOLVED review result may proceed to staging review;
    missing/stale sources and every BLOCKED result still raise unchanged.
    """
    try:
        source, report = gate_plan_source(plan, source_arg=source_arg, plan_path=plan_path)
    except MigrationGateError as error:
        report = error.report
        if (report.get("reviewStatus") != "UNRESOLVED"
                or report.get("status") == "BLOCKED"
                or any(item.get("severity") == "blocker" for item in report.get("issues", []))):
            raise
        source = Path(report["source"])
        report["reviewStatus"] = "PENDING_STAGING"
    return source, report


def source_issue_hash(issue):
    """Identity of the complete audited review issue, including evidence scope."""
    return hashlib.sha256(json.dumps(
        issue, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def gate_staging_manifest(manifest, approval):
    """Require a source/plan-bound named mapping review before staging."""
    return validate_staging_approval(manifest, approval)


def gate_completion_manifest(manifest):
    """Require passed evidence bound to the source, plan, and actual target version."""
    return validate_completion(manifest)
