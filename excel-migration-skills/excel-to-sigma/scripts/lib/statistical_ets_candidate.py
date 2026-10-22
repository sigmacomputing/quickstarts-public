"""Explicit, unqualified statsmodels AAA candidate for review and comparison.

Requires statsmodels 0.15 and SciPy 1.18 in an isolated environment. Excel's
optimizer and initial state convention are unpublished; this is not an Excel
FORECAST.ETS implementation or a production dependency declaration.
"""
from __future__ import annotations

import math
from numbers import Integral
import warnings


class CandidateFitError(ValueError):
    def __init__(self, code, diagnostics=None):
        super().__init__(code)
        self.code = code
        self.diagnostics = diagnostics or {}


def _fit_model(values, seasonality):
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel

    model = ETSModel(values, error="add", trend="add",
                     seasonal="add" if seasonality else None,
                     seasonal_periods=seasonality if seasonality else None,
                     initialization_method="estimated")
    return model.fit(disp=False, maxiter=1000)


def _warning_details(captured):
    distinct = []
    for warning in captured:
        item = {"category": warning.category.__name__,
                "message": str(warning.message)[:240]}
        if item not in distinct:
            distinct.append(item)
    return {"warningCount": len(captured), "warnings": distinct[:12],
            "warningsTruncated": len(distinct) > 12}


def forecast_with_diagnostics(values, seasonality, horizon):
    if isinstance(seasonality, bool) or not isinstance(seasonality, int) or seasonality < 0 or seasonality == 1:
        raise CandidateFitError("UNSUPPORTED_SEASONALITY")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise CandidateFitError("INVALID_HORIZON")
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise CandidateFitError("INSUFFICIENT_HISTORY")
    try:
        observed = [float(value) for value in values]
    except (TypeError, ValueError, OverflowError) as exc:
        raise CandidateFitError("INVALID_HISTORY") from exc
    if not all(math.isfinite(value) for value in observed):
        raise CandidateFitError("NONFINITE_HISTORY")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            fit = _fit_model(observed, seasonality)
        except Exception as exc:
            raise CandidateFitError("OPTIMIZER_EXCEPTION", _warning_details(captured)) from exc
    diagnostics = _warning_details(captured)
    status = getattr(fit, "mle_retvals", None)
    if not isinstance(status, dict):
        raise CandidateFitError("MISSING_OPTIMIZER_STATUS", diagnostics)
    converged, warnflag = status.get("converged"), status.get("warnflag")
    diagnostics.update({"converged": converged if type(converged) is bool else None,
                        "warnflag": int(warnflag) if isinstance(warnflag, Integral) and not isinstance(warnflag, bool) else None,
                        "iterations": int(status["iterations"]) if isinstance(status.get("iterations"), Integral) else None,
                        "functionCalls": int(status["fcalls"]) if isinstance(status.get("fcalls"), Integral) else None})
    if diagnostics["converged"] is None or diagnostics["warnflag"] is None:
        raise CandidateFitError("MISSING_OPTIMIZER_STATUS", diagnostics)
    if not diagnostics["converged"] or diagnostics["warnflag"] != 0:
        raise CandidateFitError("NONCONVERGED_FIT", diagnostics)
    try:
        raw = fit.forecast(horizon)
        forecast_values = [float(value) for value in raw]
    except Exception as exc:
        raise CandidateFitError("FORECAST_EXCEPTION", diagnostics) from exc
    if len(forecast_values) != horizon or not all(math.isfinite(value) for value in forecast_values):
        raise CandidateFitError("INVALID_FORECAST_OUTPUT", diagnostics)
    return {"forecasts": forecast_values, "diagnostics": diagnostics}


def forecast(values, seasonality, horizon):
    return forecast_with_diagnostics(values, seasonality, horizon)["forecasts"]
