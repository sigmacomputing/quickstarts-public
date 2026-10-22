"""Source-bound, side-effect-free math for the Statistical Demand Forecast workbook.

The FORECAST.ETS slot is deliberately injectable: Microsoft's published AAA
description does not specify the initialization and optimizer needed for Excel
parity. No caller may describe an injected estimate as a verified Excel result.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from math import isfinite, sqrt
from statistics import NormalDist


SOURCE_SHA256 = "02f90f32fa077ee1fac7e2d7a8cdc48b61bf09f6fc69b27a855886ed9cd9d310"
SKUS = ("SKU-A100", "SKU-B200", "SKU-C300")
HISTORY_MONTHS = 36
FORECAST_MONTHS = 12


class StatisticalPortError(ValueError):
    pass


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise StatisticalPortError("INVALID_" + field)
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise StatisticalPortError("INVALID_" + field) from exc
    if not isfinite(result):
        raise StatisticalPortError("NONFINITE_" + field)
    return result


def _derived(value, field):
    try:
        result = float(value)
    except (OverflowError, ValueError, TypeError) as exc:
        raise StatisticalPortError("NONFINITE_" + field) from exc
    if not isfinite(result):
        raise StatisticalPortError("NONFINITE_" + field)
    return result


def typed_output_value(value, kind):
    """Verify every generated Sigma cell before Snowpark sees it."""
    if value is None:
        return None
    if kind == "DOUBLE":
        return _number(value, "OUTPUT")
    expected = {"STRING": str, "INTEGER": int, "BOOLEAN": bool}.get(kind)
    if expected is None or type(value) is not expected:
        raise StatisticalPortError("INVALID_OUTPUT_TYPE")
    return value


def _date(value, field):
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise StatisticalPortError("INVALID_" + field) from exc
    if not isinstance(value, date):
        raise StatisticalPortError("INVALID_" + field)
    return value


def _next_month(value):
    return date(value.year + (value.month == 12), value.month % 12 + 1, 1)


def excel_serial(value):
    """Excel 1900-system serial for dates after its fictitious 1900-02-29."""
    return (_date(value, "DATE") - date(1899, 12, 30)).days


def _history(rows):
    if not isinstance(rows, (list, tuple)) or len(rows) != HISTORY_MONTHS * len(SKUS):
        raise StatisticalPortError("EXPECTED_108_HISTORY_ROWS")
    by_key = {}
    for row in rows:
        if not isinstance(row, dict):
            raise StatisticalPortError("INVALID_HISTORY_ROW")
        sku = row.get("SKU")
        month = _date(row.get("Month"), "HISTORY_MONTH")
        if sku not in SKUS or month.day != 1 or (sku, month) in by_key:
            raise StatisticalPortError("INVALID_HISTORY_KEY")
        raw = row.get("Demand")
        by_key[sku, month] = None if raw is None else _number(raw, "DEMAND")
    months = sorted({month for _, month in by_key})
    if len(months) != HISTORY_MONTHS or any(_next_month(a) != b for a, b in zip(months, months[1:])):
        raise StatisticalPortError("NONCONSECUTIVE_HISTORY_MONTHS")
    if set(by_key) != {(sku, month) for sku in SKUS for month in months}:
        raise StatisticalPortError("INCOMPLETE_HISTORY_GRID")
    return months, {sku: [by_key[sku, month] for month in months] for sku in SKUS}


def _targets(values, last_history):
    if not isinstance(values, (list, tuple)) or len(values) != FORECAST_MONTHS:
        raise StatisticalPortError("EXPECTED_12_TARGET_DATES")
    targets = [_date(v, "TARGET_DATE") for v in values]
    if any(v.day != 1 for v in targets) or targets[0] != _next_month(last_history):
        raise StatisticalPortError("INVALID_TARGET_TIMELINE")
    if any(_next_month(a) != b for a, b in zip(targets, targets[1:])):
        raise StatisticalPortError("NONCONSECUTIVE_TARGET_MONTHS")
    return targets


def forecast_linear(target, months, values):
    """FORECAST.LINEAR/TREND regression on Excel date serials, paired blanks omitted."""
    pairs = [(float(excel_serial(month)), _number(value, "DEMAND"))
             for month, value in zip(months, values) if value is not None]
    if len(months) != len(values) or len(pairs) < 2:
        raise StatisticalPortError("INSUFFICIENT_LINEAR_HISTORY")
    xbar = _derived(sum(x for x, _ in pairs) / len(pairs), "LINEAR_X_MEAN")
    ybar = _derived(sum(y for _, y in pairs) / len(pairs), "LINEAR_Y_MEAN")
    xx = _derived(sum((x - xbar) ** 2 for x, _ in pairs), "LINEAR_VARIANCE")
    if xx == 0:
        raise StatisticalPortError("ZERO_LINEAR_VARIANCE")
    try:
        covariance = sum((x - xbar) * (y - ybar) for x, y in pairs)
        slope = covariance / xx
        forecast = ybar + slope * (excel_serial(target) - xbar)
    except OverflowError as exc:
        raise StatisticalPortError("NONFINITE_LINEAR_FORECAST") from exc
    return _derived(forecast, "LINEAR_FORECAST")


def trailing_three_average(values):
    # OFFSET starts at the last History row and returns that row and two above.
    tail = [v for v in values[-3:] if v is not None]
    if not tail:
        raise StatisticalPortError("EMPTY_TRAILING_WINDOW")
    return _derived(sum(tail) / len(tail), "TRAILING_AVERAGE")


def sample_stdev(values):
    observed = [_number(v, "DEMAND") for v in values if v is not None]
    if len(observed) < 2:
        raise StatisticalPortError("INSUFFICIENT_STDEV_HISTORY")
    mean = _derived(sum(observed) / len(observed), "STDEV_MEAN")
    try:
        variance = sum((v - mean) ** 2 for v in observed) / (len(observed) - 1)
        stdev = sqrt(_derived(variance, "STDEV_VARIANCE"))
    except OverflowError as exc:
        raise StatisticalPortError("NONFINITE_STDEV_VARIANCE") from exc
    return _derived(stdev, "STDEV")


def interpolate_missing(values):
    """The documented FORECAST.ETS data_completion=1 neighbor interpolation."""
    result = list(values)
    missing = sum(v is None for v in result)
    if missing > len(result) * .30:
        raise StatisticalPortError("TOO_MANY_MISSING_ETS_POINTS")
    for index, value in enumerate(result):
        if value is not None:
            continue
        left = index - 1
        while left >= 0 and values[left] is None:
            left -= 1
        right = index + 1
        while right < len(result) and values[right] is None:
            right += 1
        if left < 0 or right >= len(result):
            raise StatisticalPortError("UNBOUNDED_MISSING_ETS_POINT")
        try:
            interpolated = values[left] + (values[right] - values[left]) * (index-left) / (right-left)
        except OverflowError as exc:
            raise StatisticalPortError("NONFINITE_ETS_COMPLETION") from exc
        result[index] = _derived(interpolated, "ETS_COMPLETION")
    return result


def calculate(rows, selected_sku, seasonality, service_level, lead_months,
              target_dates, *, ets_forecaster=None):
    """Calculate live source fields; mark every ETS-derived field unqualified.

    ``ets_forecaster(values, seasonality, horizon)`` must produce twelve finite
    numbers from the current history. An available candidate is review-only.
    """
    months, series = _history(rows)
    targets = _targets(target_dates, months[-1])
    if selected_sku not in SKUS:
        raise StatisticalPortError("MISSING_OR_INVALID_SELECTED_SKU")
    season = _number(seasonality, "SEASONALITY")
    if season != int(season) or not 0 <= season <= 8760:
        raise StatisticalPortError("INVALID_SEASONALITY")
    seasonality = int(season)
    service = _number(service_level, "SERVICE_LEVEL")
    lead = _number(lead_months, "LEAD_MONTHS")
    if not 0 < service < 1 or lead < 0:
        raise StatisticalPortError("INVALID_INVENTORY_PARAMETERS")
    z = _derived(NormalDist().inv_cdf(service), "SERVICE_QUANTILE")
    linear = {sku: [forecast_linear(target, months, series[sku]) for target in targets]
              for sku in SKUS}
    trailing = trailing_three_average(series[selected_sku])
    forecasts = None
    if ets_forecaster is not None:
        forecasts = {}
        for sku in SKUS:
            completed = interpolate_missing(series[sku])
            estimate = ets_forecaster(completed, seasonality, FORECAST_MONTHS)
            if not isinstance(estimate, (list, tuple)) or len(estimate) != FORECAST_MONTHS:
                raise StatisticalPortError("ETS_FIT_FAILED")
            forecasts[sku] = [_number(v, "ETS_FORECAST") for v in estimate]
    period_rows = []
    for i, target in enumerate(targets):
        period_rows.append({"Month": target.isoformat(),
                            "ETS": {sku: forecasts[sku][i] if forecasts else None for sku in SKUS},
                            "Linear": {sku: linear[sku][i] for sku in SKUS},
                            "SelectedSKUTrend": linear[selected_sku][i],
                            "Selected3MMA": trailing})
    summary = []
    for sku in SKUS:
        stdev = sample_stdev(series[sku])
        safety = _derived(z * stdev * sqrt(lead), "SAFETY_STOCK")
        total = _derived(sum(forecasts[sku]), "ETS_TOTAL") if forecasts else None
        reorder = _derived(total / 12 * lead + safety, "REORDER_POINT") if total is not None else None
        summary.append({"SKU": sku, "FY26ETSTotal": total,
                        "StdDev36M": stdev, "SafetyStock": safety,
                        "ReorderPoint": reorder})
    return {"Status": "REVIEW_REQUIRED" if forecasts else "ETS_UNAVAILABLE",
            "ReadyToPublish": False, "SourceHash": SOURCE_SHA256,
            "ETSMethod": "UNQUALIFIED_CANDIDATE" if forecasts else "NONE",
            "Periods": period_rows, "Summary": summary,
            "IntendedSequenceDescending": list(range(12, 0, -1)),
            "SourceK4": "#NAME?"}
