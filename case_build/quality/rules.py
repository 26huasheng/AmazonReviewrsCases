from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from utils import sql_literal


DEFAULT_RULES: dict[str, Any] = {
    "min_shelf_products": None,
    "min_competitors": None,
    "min_selected_users": None,
    "min_gt1_users": None,
    "min_market_positive_users": None,
    "max_none_rate": None,
    "min_focal_demand_count": None,
    "min_post90_rating_count": None,
    "min_market_pre_t0_review_count": None,
    "require_review_activity_truth": False,
}


def load_quality_rules(path: Path | None) -> dict[str, Any]:
    rules = dict(DEFAULT_RULES)
    if path is None:
        return rules
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("quality rules must be a JSON object")
    unknown = set(value) - set(rules)
    if unknown:
        raise ValueError(f"unknown quality rule keys: {sorted(unknown)}")
    rules.update(value)
    return rules


def write_quality_decisions(
    con: duckdb.DuckDBPyConnection,
    metrics: Path,
    destination: Path,
    copy_atomic,
    *,
    rules: dict[str, Any],
) -> None:
    src = sql_literal(str(metrics))
    checks: list[tuple[str, str]] = [
        ("valid_t0", "coalesce(valid_t0, false)"),
        ("evaluation_window_complete", "coalesce(evaluation_window_complete, false)"),
        ("one_focal_in_shelf", "focal_rows = 1"),
        ("gt2_coverage_complete", "coalesce(gt2_coverage_complete, false)"),
    ]
    mapping = [
        ("min_shelf_products", "shelf_product_count", ">=", "shelf_products_below_threshold"),
        ("min_competitors", "competitor_count", ">=", "competitors_below_threshold"),
        ("min_selected_users", "selected_user_count", ">=", "selected_users_below_threshold"),
        ("min_gt1_users", "gt1_user_count", ">=", "gt1_users_below_threshold"),
        ("min_market_positive_users", "market_positive_user_count", ">=", "market_positive_users_below_threshold"),
        ("max_none_rate", "none_rate", "<=", "none_rate_above_threshold"),
        ("min_focal_demand_count", "focal_demand_count", ">=", "focal_demand_below_threshold"),
        ("min_post90_rating_count", "post90_rating_count", ">=", "post90_rating_count_below_threshold"),
        ("min_market_pre_t0_review_count", "market_pre_t0_review_count", ">=", "market_pre_t0_review_count_below_threshold"),
    ]
    reason_cases = [
        "CASE WHEN NOT coalesce(valid_t0,false) THEN 'invalid_t0' END",
        "CASE WHEN NOT coalesce(evaluation_window_complete,false) THEN 'evaluation_window_incomplete' END",
        "CASE WHEN focal_rows <> 1 THEN 'focal_shelf_integrity_failed' END",
        "CASE WHEN NOT coalesce(gt2_coverage_complete,false) THEN 'gt2_coverage_incomplete' END",
    ]
    for key, field, op, reason in mapping:
        value = rules.get(key)
        if value is None:
            continue
        checks.append((key, f"{field} IS NOT NULL AND {field} {op} {float(value)}"))
        reason_cases.append(
            f"CASE WHEN NOT ({field} IS NOT NULL AND {field} {op} {float(value)}) "
            f"THEN {sql_literal(reason)} END"
        )
    if rules.get("require_review_activity_truth"):
        checks.append((
            "require_review_activity_truth",
            "focal_review_activity_rank IS NOT NULL",
        ))
        reason_cases.append(
            "CASE WHEN focal_review_activity_rank IS NULL THEN 'review_activity_truth_missing' END"
        )

    pass_expr = " AND ".join(f"({expr})" for _, expr in checks)
    reasons_expr = (
        "list_filter(list_value(" + ",".join(reason_cases) + "), x -> x IS NOT NULL)"
    )
    copy_atomic(f"""
        SELECT *,
               ({pass_expr}) AS quality_pass,
               {reasons_expr} AS quality_rejection_reasons,
               CASE WHEN ({pass_expr}) THEN 'accepted' ELSE 'rejected' END
                   AS quality_status
        FROM read_parquet({src})
        ORDER BY market_id, t0, case_candidate_id
    """, destination)
