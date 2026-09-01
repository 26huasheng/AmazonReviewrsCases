from __future__ import annotations

from pathlib import Path

import duckdb

from utils import sql_literal


POPULATION_SOURCES = {"category", "global"}


def write_market_population(
    con: duckdb.DuckDBPyConnection,
    market_products: Path,
    user_summary: Path,
    destination: Path,
    copy_atomic,
    *,
    population_source: str,
    population_size: int | None = None,
    seed: str = "market_population_v1",
) -> None:
    """给每个 Market 固定一批共享候选用户。

    这一步只看 Market/source_partition 与大类用户池，不看任何 Case future outcome。
    """
    if population_source not in POPULATION_SOURCES:
        raise ValueError(
            f"population_source must be one of {sorted(POPULATION_SOURCES)}"
        )
    if population_size is not None and population_size <= 0:
        raise ValueError("population_size must be positive or None")
    products = sql_literal(str(market_products))
    users = sql_literal(str(user_summary))
    seed_sql = sql_literal(seed)

    if population_source == "category":
        pool = f"""
            SELECT m.market_id, m.source_partition, u.user_id
            FROM (
                SELECT DISTINCT market_id, source_partition
                FROM read_parquet({products})
            ) m
            JOIN read_parquet({users}) u
              ON m.source_partition=u.source_partition
        """
    else:
        pool = f"""
            SELECT m.market_id, m.source_partition, u.user_id
            FROM (
                SELECT DISTINCT market_id, source_partition
                FROM read_parquet({products})
            ) m
            CROSS JOIN (
                SELECT DISTINCT user_id FROM read_parquet({users})
            ) u
        """

    limit_clause = (
        f"WHERE sampling_rank <= {int(population_size)}"
        if population_size is not None else ""
    )
    copy_atomic(f"""
        WITH pool AS ({pool}), ranked AS (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY market_id
                       ORDER BY sha256(CAST(to_json(list_value(
                           {seed_sql}, market_id, user_id
                       )) AS VARCHAR)), user_id
                   ) AS sampling_rank
            FROM pool
        )
        SELECT market_id, source_partition, user_id,
               {sql_literal(population_source)}::VARCHAR AS population_source,
               sampling_rank::BIGINT
        FROM ranked
        {limit_clause}
        ORDER BY market_id, sampling_rank
    """, destination)
