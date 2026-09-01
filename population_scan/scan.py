from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from utils import sql_literal, write_json


USER_COLUMNS = ("user_id", "consumer_id", "reviewer_id", "stable_user_key")
PRODUCT_COLUMNS = ("product_id", "parent_asin", "asin", "item_id")
TIME_COLUMNS = ("event_time_ms", "timestamp", "event_timestamp", "event_date")
RATING_COLUMNS = ("rating", "rating_value")
VERIFIED_COLUMNS = ("verified_purchase", "verified")


def _first(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((name for name in candidates if name in columns), None)


class PopulationScanner:
    """对一个大类的用户事件做 case-agnostic 基础人口扫描。

    支持两类已经存在的输入：
    1. Amazon rating_only / canonical CSV、Parquet；
    2. AmazonReviewrepo v5 的 rating_event_store 目录。
    """

    def __init__(
        self,
        events: Path,
        output_dir: Path,
        *,
        source_partition: str | None = None,
    ) -> None:
        self.events = events.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.source_partition = source_partition
        if not self.events.exists():
            raise FileNotFoundError(self.events)
        self.users_path = self.output_dir / "users.parquet"
        self.summary_path = self.output_dir / "summary.json"
        self.con = duckdb.connect()
        self.con.execute("SET preserve_insertion_order=false")
        temp = self.output_dir / ".duckdb_tmp"
        temp.mkdir(parents=True, exist_ok=True)
        self.con.execute(f"SET temp_directory={sql_literal(str(temp))}")

    def close(self) -> None:
        self.con.close()

    def _copy_atomic(self, query: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        part.unlink(missing_ok=True)
        self.con.execute(
            f"COPY ({query}) TO {sql_literal(str(part))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        os.replace(part, path)

    def _source_relation(self) -> tuple[str, str]:
        """返回 DuckDB relation SQL 与 source_kind。"""
        if self.events.is_dir():
            pattern = self.events / "source_partition=*" / "bucket=*" / "events.parquet"
            if list(self.events.glob("source_partition=*/bucket=*/events.parquet")):
                return (
                    f"read_parquet({sql_literal(str(pattern))}, hive_partitioning=true)",
                    "v5_rating_event_store",
                )
            parquet_files = list(self.events.rglob("*.parquet"))
            if parquet_files:
                pattern = self.events / "**" / "*.parquet"
                return (
                    f"read_parquet({sql_literal(str(pattern))}, union_by_name=true, hive_partitioning=true)",
                    "parquet_directory",
                )
            raise ValueError(f"no parquet event files found under {self.events}")
        suffix = self.events.suffix.lower()
        if suffix == ".parquet":
            return f"read_parquet({sql_literal(str(self.events))})", "parquet"
        if suffix in {".csv", ".tsv"}:
            delim = "'\\t'" if suffix == ".tsv" else "','"
            return (
                f"read_csv_auto({sql_literal(str(self.events))}, delim={delim}, header=true, sample_size=-1)",
                "delimited_text",
            )
        raise ValueError(f"unsupported event source: {self.events}")

    def _register_events(self) -> dict[str, Any]:
        relation, source_kind = self._source_relation()
        columns = {
            str(row[0])
            for row in self.con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        }
        user_col = _first(columns, USER_COLUMNS)
        product_col = _first(columns, PRODUCT_COLUMNS)
        time_col = _first(columns, TIME_COLUMNS)
        verified_col = _first(columns, VERIFIED_COLUMNS)
        if not user_col or not product_col or not time_col:
            raise ValueError(
                "event source must provide user/product/time columns; "
                f"columns={sorted(columns)}"
            )

        if "source_partition" in columns:
            partition_expr = "CAST(source_partition AS VARCHAR)"
        elif self.source_partition:
            partition_expr = f"{sql_literal(self.source_partition)}::VARCHAR"
        else:
            raise ValueError(
                "source_partition missing from input; provide --source-partition"
            )

        if time_col == "event_time_ms":
            ts_expr = f"try(to_timestamp(CAST({time_col} AS DOUBLE) / 1000.0))"
        elif time_col == "timestamp":
            ts_expr = (
                f"CASE WHEN try_cast({time_col} AS DOUBLE) IS NOT NULL THEN "
                f"try(to_timestamp(CASE WHEN try_cast({time_col} AS DOUBLE) > 100000000000 "
                f"THEN try_cast({time_col} AS DOUBLE) / 1000.0 "
                f"ELSE try_cast({time_col} AS DOUBLE) END)) "
                f"ELSE try_cast({time_col} AS TIMESTAMP) END"
            )
        elif time_col == "event_date":
            ts_expr = f"try_cast({time_col} AS TIMESTAMP)"
        else:
            ts_expr = f"try_cast({time_col} AS TIMESTAMP)"

        verified_expr = (
            f"try_cast({verified_col} AS BOOLEAN)" if verified_col else "NULL::BOOLEAN"
        )
        self.con.execute(f"""
            CREATE OR REPLACE TEMP VIEW population_events AS
            SELECT {partition_expr} AS source_partition,
                   CAST({user_col} AS VARCHAR) AS user_id,
                   CAST({product_col} AS VARCHAR) AS product_id,
                   {ts_expr} AS event_timestamp,
                   CAST({ts_expr} AS DATE) AS event_date,
                   {verified_expr} AS verified_purchase
            FROM {relation}
            WHERE {user_col} IS NOT NULL
              AND trim(CAST({user_col} AS VARCHAR)) <> ''
              AND {product_col} IS NOT NULL
              AND trim(CAST({product_col} AS VARCHAR)) <> ''
              AND {ts_expr} IS NOT NULL
        """)
        return {
            "source_kind": source_kind,
            "source_columns": sorted(columns),
            "resolved_user_column": user_col,
            "resolved_product_column": product_col,
            "resolved_time_column": time_col,
            "resolved_verified_column": verified_col,
        }

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        source_meta = self._register_events()
        self._copy_atomic("""
            SELECT source_partition,
                   user_id,
                   count(*)::BIGINT AS n_events,
                   count(DISTINCT product_id)::BIGINT AS n_products,
                   CASE WHEN count(verified_purchase) = 0 THEN NULL
                        ELSE count(*) FILTER (verified_purchase)::BIGINT END
                       AS n_verified_purchases,
                   min(event_date) AS first_event_date,
                   max(event_date) AS last_event_date
            FROM population_events
            GROUP BY source_partition, user_id
            ORDER BY source_partition, user_id
        """, self.users_path)

        event_count = int(self.con.execute(
            "SELECT count(*) FROM population_events"
        ).fetchone()[0])
        user_count = int(self.con.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(self.users_path)]
        ).fetchone()[0])
        partition_count = int(self.con.execute(
            "SELECT count(DISTINCT source_partition) FROM read_parquet(?)",
            [str(self.users_path)],
        ).fetchone()[0])
        stats = self.con.execute("""
            SELECT avg(n_events)::DOUBLE,
                   quantile_cont(n_events, 0.5)::DOUBLE,
                   quantile_cont(n_events, 0.9)::DOUBLE,
                   quantile_cont(n_events, 0.99)::DOUBLE,
                   avg(n_products)::DOUBLE,
                   quantile_cont(n_products, 0.5)::DOUBLE,
                   quantile_cont(n_products, 0.9)::DOUBLE,
                   quantile_cont(n_products, 0.99)::DOUBLE,
                   avg(CASE WHEN n_events=1 THEN 1.0 ELSE 0.0 END)::DOUBLE
            FROM read_parquet(?)
        """, [str(self.users_path)]).fetchone()
        summary = {
            "status": "COMPLETE",
            "schema_version": "population_scan_v1",
            "source": str(self.events),
            "requested_source_partition": self.source_partition,
            "source_metadata": source_meta,
            "event_count": event_count,
            "user_count": user_count,
            "partition_count": partition_count,
            "event_count_policy": "every observed rating/review event counts once",
            "product_count_policy": "distinct product_id per user",
            "verified_purchase_policy": "separate count when available; never substitutes n_events",
            "stats": {
                "mean_events": stats[0], "p50_events": stats[1],
                "p90_events": stats[2], "p99_events": stats[3],
                "mean_products": stats[4], "p50_products": stats[5],
                "p90_products": stats[6], "p99_products": stats[7],
                "single_event_user_rate": stats[8],
            },
        }
        write_json(self.summary_path, summary)
        return summary
