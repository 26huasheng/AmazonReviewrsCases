from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


def write_population_truth(
    con: duckdb.DuckDBPyConnection,
    case_users: Path,
    positive_outcomes: Path,
    destination: Path,
    copy_atomic,
) -> None:
    users = sql_literal(str(case_users))
    outcomes = sql_literal(str(positive_outcomes))
    copy_atomic(f"""
        SELECT u.case_candidate_id,
               u.user_id,
               o.outcome_product_id,
               o.event_timestamp,
               o.rating,
               o.verified_purchase,
               o.outcome_policy
        FROM read_parquet({users}) u
        LEFT JOIN read_parquet({outcomes}) o
          ON u.case_candidate_id=o.case_candidate_id
         AND u.user_id=o.user_id
        ORDER BY u.case_candidate_id, u.user_id
    """, destination)


def write_choice_truth(
    con: duckdb.DuckDBPyConnection,
    population_truth: Path,
    destination: Path,
    copy_atomic,
) -> None:
    src = sql_literal(str(population_truth))
    copy_atomic(f"""
        SELECT case_candidate_id,
               user_id,
               outcome_product_id AS target_product_id,
               event_timestamp,
               rating,
               verified_purchase,
               outcome_policy
        FROM read_parquet({src})
        WHERE outcome_product_id IS NOT NULL
        ORDER BY case_candidate_id, user_id
    """, destination)


def write_market_truth(
    con: duckdb.DuckDBPyConnection,
    case_shelf: Path,
    population_truth: Path,
    destination: Path,
    copy_atomic,
) -> None:
    shelf = sql_literal(str(case_shelf))
    truth = sql_literal(str(population_truth))
    copy_atomic(f"""
        WITH products AS (
            SELECT DISTINCT case_candidate_id, product_id, role
            FROM read_parquet({shelf})
        ), counts AS (
            SELECT case_candidate_id, outcome_product_id AS product_id,
                   count(*)::BIGINT AS demand_count
            FROM read_parquet({truth})
            WHERE outcome_product_id IS NOT NULL
            GROUP BY case_candidate_id, outcome_product_id
        ), totals AS (
            SELECT case_candidate_id,
                   count(*) FILTER (outcome_product_id IS NOT NULL)::BIGINT
                       AS market_positive_count,
                   count(*)::BIGINT AS population_count
            FROM read_parquet({truth})
            GROUP BY case_candidate_id
        ), joined AS (
            SELECT p.case_candidate_id,
                   p.product_id,
                   p.role,
                   coalesce(c.demand_count, 0)::BIGINT AS demand_count,
                   coalesce(t.market_positive_count, 0)::BIGINT AS market_positive_count,
                   coalesce(t.population_count, 0)::BIGINT AS population_count
            FROM products p
            LEFT JOIN counts c USING(case_candidate_id, product_id)
            LEFT JOIN totals t USING(case_candidate_id)
        ), ranked AS (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY case_candidate_id
                       ORDER BY demand_count DESC, product_id
                   )::BIGINT AS rank
            FROM joined
        )
        SELECT case_candidate_id,
               product_id,
               role,
               demand_count,
               CASE WHEN market_positive_count > 0
                    THEN demand_count::DOUBLE / market_positive_count
                    ELSE 0.0 END AS demand_share,
               rank,
               population_count,
               market_positive_count,
               (population_count - market_positive_count)::BIGINT AS none_count,
               CASE WHEN population_count > 0
                    THEN market_positive_count::DOUBLE / population_count
                    ELSE 0.0 END AS market_entry_rate
        FROM ranked
        ORDER BY case_candidate_id, rank, product_id
    """, destination)
