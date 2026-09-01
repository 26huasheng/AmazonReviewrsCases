from __future__ import annotations

from pathlib import Path

import duckdb

from .config import ENTRY_DATE_SOURCE
from utils import sql_literal


def _columns(con: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    }


def write_market_product_map_and_timeline(
    con: duckdb.DuckDBPyConnection,
    final_market: Path,
    product_time_summary: Path,
    product_core: Path,
    map_path: Path,
    timeline_path: Path,
    copy_atomic,
) -> dict[str, int]:
    """把 Final Market 的商品集合展开，并挂上商品首评/末评时间与基础 metadata。"""
    market = sql_literal(str(final_market))
    times = sql_literal(str(product_time_summary))
    core = sql_literal(str(product_core))

    core_columns = _columns(con, product_core)
    required_core = {"source_partition", "product_id", "product_title"}
    missing_core_columns = required_core - core_columns
    if missing_core_columns:
        raise ValueError(
            f"product_core missing columns: {sorted(missing_core_columns)}"
        )

    category_path_expr = (
        "p.category_path" if "category_path" in core_columns
        else "NULL::VARCHAR[]"
    )
    first_available_expr = (
        "CAST(p.first_available_date AS VARCHAR)" if "first_available_date" in core_columns
        else "NULL::VARCHAR"
    )
    snapshot_price_expr = (
        "TRY_CAST(p.snapshot_price AS DOUBLE)" if "snapshot_price" in core_columns
        else "NULL::DOUBLE"
    )

    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW market_product_map AS
        SELECT discovery_version,
               source_partition,
               market_id,
               market_label,
               CAST(product_id AS VARCHAR) AS product_id
        FROM read_parquet({market}), unnest(product_ids) AS u(product_id)
    """)

    duplicates = con.execute("""
        SELECT source_partition, product_id, count(*)
        FROM market_product_map
        GROUP BY source_partition, product_id
        HAVING count(*) > 1
        ORDER BY source_partition, product_id
        LIMIT 10
    """).fetchall()
    if duplicates:
        raise ValueError(
            f"product_id belongs to multiple final markets: {duplicates}"
        )

    missing_time = con.execute(f"""
        SELECT m.source_partition, m.product_id
        FROM market_product_map m
        LEFT JOIN read_parquet({times}) t
          USING (source_partition, product_id)
        WHERE t.product_id IS NULL
        ORDER BY m.source_partition, m.product_id
        LIMIT 10
    """).fetchall()
    if missing_time:
        raise ValueError(
            f"market products missing from product_time_summary: {missing_time}"
        )

    missing_core = con.execute(f"""
        SELECT m.source_partition, m.product_id
        FROM market_product_map m
        LEFT JOIN read_parquet({core}) p
          USING (source_partition, product_id)
        WHERE p.product_id IS NULL
        ORDER BY m.source_partition, m.product_id
        LIMIT 10
    """).fetchall()
    if missing_core:
        raise ValueError(
            f"market products missing from product_core: {missing_core}"
        )

    map_count = int(con.execute(
        "SELECT count(*) FROM market_product_map"
    ).fetchone()[0])
    copy_atomic("SELECT * FROM market_product_map", map_path)

    copy_atomic(f"""
        SELECT m.source_partition,
               m.discovery_version,
               m.market_id,
               m.market_label,
               m.product_id,
               p.product_title,
               {category_path_expr} AS category_path,
               {first_available_expr} AS first_available_date,
               {snapshot_price_expr} AS metadata_snapshot_price,
               t.first_rating_date AS entry_date,
               t.first_rating_date,
               t.last_rating_date,
               t.total_rating_count,
               t.post90_rating_count,
               {sql_literal(ENTRY_DATE_SOURCE)}::VARCHAR AS entry_date_source
        FROM market_product_map m
        JOIN read_parquet({times}) t
          USING (source_partition, product_id)
        JOIN read_parquet({core}) p
          USING (source_partition, product_id)
    """, timeline_path)

    timeline_count = int(con.execute(
        "SELECT count(*) FROM read_parquet(?)", [str(timeline_path)]
    ).fetchone()[0])
    if timeline_count != map_count:
        raise ValueError(
            f"timeline row count {timeline_count} != market_product_map {map_count}"
        )
    return {"market_product_count": map_count}
