"""Bounded JSON transport for the review-only statistical ETS provider.

The Snowflake handler receives the injected Session but never uses it. Forecast
math stays in statistical_ets_candidate.py; this module only transports one
SKU's completed series and its diagnostic result.
"""
from __future__ import annotations

import json
import math
import re

RPC_PROTOCOL = "statistical-ets-candidate-rpc-v1"
RPC_MODEL = "statsmodels 0.15.0 ETSModel(add,add,add; estimated initial states)"
RPC_SOURCE_SHA256 = "02f90f32fa077ee1fac7e2d7a8cdc48b61bf09f6fc69b27a855886ed9cd9d310"
RPC_REQUEST_MAX_BYTES = 8192
RPC_RESPONSE_MAX_BYTES = 16384
RPC_SKUS = ("SKU-A100", "SKU-B200", "SKU-C300")
RPC_IDENTITY_KEYS = {"protocol", "modelIdentity", "sourceHash", "sourceBindingHash",
                     "inputHash", "previewRunId", "sku"}


class RpcContractError(ValueError):
    pass


def _require(condition, code):
    if not condition:
        raise RpcContractError(code)


def _json_loads(raw, maximum, code):
    _require(isinstance(raw, str) and len(raw.encode("utf-8")) <= maximum, code)
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (TypeError, ValueError) as exc:
        raise RpcContractError(code) from exc


def _json_dumps(value, maximum, code):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RpcContractError(code) from exc
    _require(len(raw.encode("utf-8")) <= maximum, code)
    return raw


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _identity(identity):
    _require(isinstance(identity, dict) and set(identity) == RPC_IDENTITY_KEYS,
             "RPC_IDENTITY_INVALID")
    _require(identity["protocol"] == RPC_PROTOCOL and
             identity["modelIdentity"] == RPC_MODEL and
             identity["sourceHash"] == RPC_SOURCE_SHA256 and
             identity["sku"] in RPC_SKUS and
             all(isinstance(identity[k], str) and re.fullmatch("[0-9a-f]{64}", identity[k])
                 for k in ("sourceBindingHash", "inputHash")) and
             isinstance(identity["previewRunId"], str) and
             re.fullmatch("[0-9a-f-]{36}", identity["previewRunId"]),
             "RPC_IDENTITY_INVALID")
    return identity


def encode_fit_request(values, seasonality, horizon, *, source_binding_hash,
                       input_hash, preview_run_id, sku):
    _require(isinstance(values, (list, tuple)) and len(values) == 36 and
             all(_finite_number(v) for v in values),
             "RPC_VALUES_INVALID")
    _require(type(seasonality) is int and 0 <= seasonality <= 8760 and
             type(horizon) is int and horizon == 12, "RPC_PARAMETERS_INVALID")
    identity = _identity({"protocol": RPC_PROTOCOL, "modelIdentity": RPC_MODEL,
        "sourceHash": RPC_SOURCE_SHA256, "sourceBindingHash": source_binding_hash,
        "inputHash": input_hash, "previewRunId": preview_run_id, "sku": sku})
    return _json_dumps({"identity": identity, "values": list(values),
                        "seasonality": seasonality, "horizon": horizon},
                       RPC_REQUEST_MAX_BYTES, "RPC_REQUEST_INVALID")


def _request(raw):
    request = _json_loads(raw, RPC_REQUEST_MAX_BYTES, "RPC_REQUEST_INVALID")
    _require(isinstance(request, dict) and
             set(request) == {"identity", "values", "seasonality", "horizon"},
             "RPC_REQUEST_INVALID")
    _identity(request["identity"])
    _require(isinstance(request["values"], list) and len(request["values"]) == 36 and
             all(_finite_number(v) for v in request["values"]), "RPC_VALUES_INVALID")
    _require(type(request["seasonality"]) is int and 0 <= request["seasonality"] <= 8760
             and type(request["horizon"]) is int and request["horizon"] == 12,
             "RPC_PARAMETERS_INVALID")
    return request


def decode_fit_response(raw, request_raw):
    request = _request(request_raw)
    response = _json_loads(raw, RPC_RESPONSE_MAX_BYTES, "RPC_RESPONSE_INVALID")
    _require(isinstance(response, dict) and set(response) ==
             {"identity", "status", "errorCode", "forecasts", "diagnostics",
              "runtimePackages"}, "RPC_RESPONSE_INVALID")
    _require(response["identity"] == request["identity"], "RPC_RESPONSE_IDENTITY_MISMATCH")
    _require(response["status"] in ("SUCCESS", "FAILURE") and
             (response["errorCode"] is None or isinstance(response["errorCode"], str)) and
             isinstance(response["diagnostics"], dict) and
             isinstance(response["runtimePackages"], dict), "RPC_RESPONSE_INVALID")
    packages = response["runtimePackages"]
    _require(set(packages) == {"statsmodels", "scipy"} and
             all(v is None or isinstance(v, str) for v in packages.values()),
             "RPC_RESPONSE_INVALID")
    if response["status"] == "SUCCESS":
        _require(response["errorCode"] is None and packages ==
                 {"statsmodels": "0.15.0", "scipy": "1.18.1"} and
                 isinstance(response["forecasts"], list) and
                 len(response["forecasts"]) == 12 and
                 all(_finite_number(v) for v in response["forecasts"]), "RPC_RESPONSE_INVALID")
    else:
        _require(response["errorCode"] and response["forecasts"] is None,
                 "RPC_RESPONSE_INVALID")
    return response


def server_fit(request_raw, fit_fn=None, version_fn=None):
    """Pure Snowflake handler body. No SQL, Snowpark actions, network, or writes."""
    try:
        request = _request(request_raw)
    except RpcContractError as exc:
        # Invalid envelopes cannot carry trusted source/model attribution.
        return _json_dumps({"identity": None, "status": "FAILURE",
            "errorCode": str(exc), "forecasts": None, "diagnostics": {},
            "runtimePackages": {"statsmodels": None, "scipy": None}},
            RPC_RESPONSE_MAX_BYTES, "RPC_RESPONSE_INVALID")
    from importlib.metadata import PackageNotFoundError, version
    if version_fn is None:
        version_fn = version
    try:
        candidate_error_type = CandidateFitError
    except NameError:
        from statistical_ets_candidate import CandidateFitError as candidate_error_type
        if fit_fn is None:
            from statistical_ets_candidate import forecast_with_diagnostics as fit_fn
    if fit_fn is None:
        fit_fn = forecast_with_diagnostics
    packages = {"statsmodels": None, "scipy": None}
    diagnostics = {}
    forecasts = None
    error = None
    try:
        packages = {"statsmodels": version_fn("statsmodels"),
                    "scipy": version_fn("scipy")}
        if packages["statsmodels"] != "0.15.0":
            error = "CANDIDATE_VERSION_MISMATCH"
        elif packages["scipy"] != "1.18.1":
            error = "CANDIDATE_SCIPY_VERSION_MISMATCH"
        else:
            fit = fit_fn(request["values"], request["seasonality"], request["horizon"])
            forecasts, diagnostics = fit["forecasts"], fit["diagnostics"]
    except candidate_error_type as exc:
        diagnostics = {"error": exc.code, **exc.diagnostics}
        error = "CANDIDATE_" + exc.code
    except PackageNotFoundError:
        error = "CANDIDATE_DEPENDENCY_UNAVAILABLE"
    except Exception:
        error = "CANDIDATE_DEPENDENCY_OR_RUNTIME_ERROR"
    response = {"identity": request["identity"],
                "status": "FAILURE" if error else "SUCCESS", "errorCode": error,
                "forecasts": None if error else forecasts, "diagnostics": diagnostics,
                "runtimePackages": packages}
    try:
        raw = _json_dumps(response, RPC_RESPONSE_MAX_BYTES, "RPC_RESPONSE_TOO_LARGE")
        decode_fit_response(raw, request_raw)
        return raw
    except RpcContractError:
        return _json_dumps({"identity": request["identity"], "status": "FAILURE",
            "errorCode": "RPC_RESPONSE_INVALID", "forecasts": None,
            "diagnostics": {}, "runtimePackages": packages},
            RPC_RESPONSE_MAX_BYTES, "RPC_RESPONSE_INVALID")
