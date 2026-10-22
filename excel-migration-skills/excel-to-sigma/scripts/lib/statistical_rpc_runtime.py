"""Emit the isolated Snowflake ETS provider and its guarded Sigma caller.

The existing statistical preview remains the source of its literal Sigma input
bindings, input fingerprint, second read, typed output, and review-only status.
Only its candidate provider slot is replaced by a bounded RPC call.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .statistical_ets_rpc import RPC_SOURCE_SHA256
from .statistical_runtime import CANDIDATE_MODEL, emit_preview_program


PROCEDURE = "SIGMA_WRITE_DB.SIGMA_TASK5_SP_TEST.STAT_ETS_PROVIDER_20261020_6A8D32F1"


def _source(name):
    return Path(__file__).with_name(name).read_text().replace(
        "from __future__ import annotations\n", "")


def _guard_kernel_source(kernel):
    marker = f'SOURCE_SHA256 = "{RPC_SOURCE_SHA256}"'
    if kernel.count(marker) != 1:
        raise ValueError("RPC_KERNEL_SOURCE_CHANGED")


def emit_rpc_preview_program(binding, source_identity, *, procedure=PROCEDURE):
    if procedure != PROCEDURE or not re.fullmatch(r"[A-Z0-9_]+(?:\.[A-Z0-9_]+){2}", procedure):
        raise ValueError("APPROVED_RPC_PROCEDURE_REQUIRED")
    base = emit_preview_program(binding, candidate_ets=True,
                                source_identity=source_identity)
    _guard_kernel_source(Path(__file__).with_name("statistical_forecast.py").read_text())
    old_provider = _source("statistical_ets_candidate.py") + "\n"
    rpc_contract = _source("statistical_ets_rpc.py").split("\ndef server_fit(", 1)[0]
    code = base["code"]
    if code.count(old_provider) != 1:
        raise ValueError("CANDIDATE_PROVIDER_SOURCE_CHANGED")
    code = code.replace(old_provider, rpc_contract + "\n", 1)
    anchor = "MODEL_IDENTITY = " + repr(CANDIDATE_MODEL) + "\n"
    if code.count(anchor) != 1:
        raise ValueError("CANDIDATE_MODEL_ANCHOR_CHANGED")
    code = code.replace(anchor, anchor + "RPC_PROCEDURE = " + repr(procedure) + "\n", 1)
    begin = "    provider = None\n    if CANDIDATE_ETS:\n"
    end = "    result = calculate(history, selected, season,\n"
    if code.count(begin) != 1 or code.count(end) != 1:
        raise ValueError("CANDIDATE_PROVIDER_SLOT_CHANGED")
    start, stop = code.index(begin), code.index(end)
    if stop <= start:
        raise ValueError("CANDIDATE_PROVIDER_SLOT_CHANGED")
    remote = '''    provider = None
    if CANDIDATE_ETS:
        fit_index = [0]
        def provider(values, seasonality, horizon):
            sku = SKUS[fit_index[0]]
            try:
                request_raw = encode_fit_request(values, seasonality, horizon,
                    source_binding_hash=SOURCE_BINDING_HASH, input_hash=input_hash,
                    preview_run_id=run_id, sku=sku)
                response = decode_fit_response(session.call(RPC_PROCEDURE, request_raw),
                                               request_raw)
            except RpcContractError as exc:
                raise StatisticalPortError(str(exc)) from exc
            except Exception as exc:
                raise StatisticalPortError('RPC_CALL_FAILED') from exc
            runtime_packages.update(response['runtimePackages'])
            fit_diagnostics[sku] = response['diagnostics']
            if response['status'] != 'SUCCESS':
                raise StatisticalPortError(response['errorCode'])
            fit_index[0] += 1
            return response['forecasts']
'''
    code = code[:start] + remote + code[stop:]
    compile(code, "<statistical-rpc-sigma-preview>", "exec")
    return {**base, "code": code,
            "codeHash": hashlib.sha256(code.encode()).hexdigest(),
            "providerProcedure": procedure, "runtimeStatus": "UNRUN_RPC_CANDIDATE"}


def emit_procedure_sql(*, procedure=PROCEDURE):
    if procedure != PROCEDURE:
        raise ValueError("APPROVED_RPC_PROCEDURE_REQUIRED")
    kernel = Path(__file__).with_name("statistical_forecast.py").read_text()
    _guard_kernel_source(kernel)
    provider = _source("statistical_ets_candidate.py")
    rpc = _source("statistical_ets_rpc.py")
    body = kernel + "\n" + provider + "\n" + rpc + "\n\n" + (
        "def run(session, request_json):\n"
        "    # Snowflake injects session; this pure handler never uses it.\n"
        "    return server_fit(request_json)\n")
    if "$$" in body:
        raise ValueError("SQL_DELIMITER_COLLISION")
    compile(body, "<statistical-rpc-snowflake-handler>", "exec")
    return (f"CREATE PROCEDURE {procedure}(REQUEST_JSON VARCHAR)\n"
            "RETURNS VARCHAR\nLANGUAGE PYTHON\nRUNTIME_VERSION = '3.12'\n"
            "PACKAGES = ('snowflake-snowpark-python', 'statsmodels==0.15.0', 'scipy==1.18.1')\n"
            "HANDLER = 'run'\nEXECUTE AS CALLER\nAS\n$$\n" + body + "$$;\n")
