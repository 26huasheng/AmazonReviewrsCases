from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from case_build.pipeline import CaseDiscoveryPipeline
from utils import write_json


PARTITION = "Electronics"
VERSION = "market_v1"


def _copy_rows(path: Path, ddl: str, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE value {ddl}")
        if rows:
            placeholders = ",".join("?" for _ in rows[0])
            con.executemany(f"INSERT INTO value VALUES ({placeholders})", rows)
        con.execute("COPY value TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        con.close()


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    market = tmp_path / "final_market.parquet"
    core = tmp_path / "product_core.parquet"
    daily = tmp_path / "rating_daily_summary.parquet"
    metadata = tmp_path / "storage_metadata.json"

    _copy_rows(market, """(
        discovery_version VARCHAR,
        source_partition VARCHAR,
        market_id VARCHAR,
        market_label VARCHAR,
        source_market_ids VARCHAR[],
        source_path_ids VARCHAR[],
        source_category_paths VARCHAR[][],
        product_ids VARCHAR[],
        product_count BIGINT
    )""", [(
        VERSION, PARTITION, "M1", "dog_collar", ["L1"], ["P1"],
        [["Pet Supplies", "Dogs", "Collars"]], ["A", "B", "C", "D"], 4,
    )])

    _copy_rows(core, """(
        source_partition VARCHAR,
        product_id VARCHAR,
        product_title VARCHAR,
        category_path VARCHAR[],
        first_available_date VARCHAR,
        snapshot_price DOUBLE
    )""", [
        (PARTITION, "A", "Old A", ["Pet Supplies"], "2010-01-01", 10.0),
        (PARTITION, "B", "Old B", ["Pet Supplies"], "2010-01-01", 20.0),
        (PARTITION, "C", "New C", ["Pet Supplies"], "2010-01-01", 30.0),
        (PARTITION, "D", "New D", ["Pet Supplies"], "2010-01-01", 40.0),
    ])

    _copy_rows(daily, """(
        source_partition VARCHAR,
        product_id VARCHAR,
        event_date DATE,
        rating_count BIGINT,
        rating_sum DOUBLE
    )""", [
        (PARTITION, "A", date(2020, 1, 1), 5, 25.0),
        (PARTITION, "A", date(2023, 12, 31), 5, 25.0),
        (PARTITION, "B", date(2021, 1, 1), 10, 40.0),
        (PARTITION, "B", date(2022, 1, 1), 1, 4.0),
        (PARTITION, "C", date(2022, 1, 1), 1, 5.0),
        (PARTITION, "C", date(2022, 3, 1), 1, 4.0),
        (PARTITION, "D", date(2023, 10, 3), 1, 5.0),
    ])
    write_json(metadata, {
        "rating_observation": {
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
        }
    })
    return {
        "market": market,
        "core": core,
        "daily": daily,
        "metadata": metadata,
        "out": tmp_path / "out",
    }


def test_discovery_keeps_multiple_focals_and_only_structural_gate(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    pipeline = CaseDiscoveryPipeline(
        paths["market"],
        paths["core"],
        paths["metadata"],
        paths["out"],
        rating_daily_summary=paths["daily"],
    )
    try:
        summary = pipeline.run()
    finally:
        pipeline.close()

    assert summary["candidate_case_count"] == 4
    assert summary["evaluable_case_count"] == 4
    assert summary["hard_quality_gates_applied"] is False
    assert summary["market_pre_t0_review_count_status"] == "COMPUTED"

    con = duckdb.connect()
    try:
        rows = {
            row[0]: row[1:]
            for row in con.execute("""
                SELECT focal_product_id,
                       t0,
                       post90_rating_count,
                       active_competitor_count_at_t0,
                       time_box_id,
                       evaluation_window_complete,
                       market_pre_t0_review_count
                FROM read_parquet(?)
            """, [str(paths["out"] / "case_candidates.parquet")]).fetchall()
        }
        columns = {
            row[0]
            for row in con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)",
                [str(paths["out"] / "case_candidates.parquet")],
            ).fetchall()
        }
    finally:
        con.close()

    # t0 来自首评时间；metadata 的 2010 Date First Available 不参与 t0。
    assert rows["C"][0] == date(2022, 1, 1)
    # C 未来 90 天只有 2 条评论，仍保留为结构完整的候选。
    assert rows["C"][1] == 2
    # C 首评当日不把自己算 competitor；A 与 B 当日仍活跃，所以为 2。
    assert rows["C"][2] == 2
    assert rows["C"][3] == "2022-H1"
    # [2023-10-03, 2024-01-01) 需要的数据最后一天是 2023-12-31，窗口完整。
    assert rows["D"][4] is True
    # C t0 以前整个 Market 的评论量为 A 的 5 + B 的 10；t0 当天不计入。
    assert rows["C"][5] == 15
    # 时间段只是 Case 属性，不再制造 market_segment 层。
    assert "market_segment_id" not in columns


def test_discovery_accepts_existing_v5_product_time_summary(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    product_time = tmp_path / "product_time_summary.parquet"
    _copy_rows(product_time, """(
        source_partition VARCHAR,
        product_id VARCHAR,
        entry_date DATE,
        first_rating_date DATE,
        last_rating_date DATE,
        total_rating_count BIGINT,
        post90_rating_count BIGINT
    )""", [
        (PARTITION, "A", date(2020, 1, 1), date(2020, 1, 1), date(2023, 12, 31), 10, 5),
        (PARTITION, "B", date(2021, 1, 1), date(2021, 1, 1), date(2022, 1, 1), 11, 10),
        (PARTITION, "C", date(2022, 1, 1), date(2022, 1, 1), date(2022, 3, 1), 2, 2),
        (PARTITION, "D", date(2023, 10, 3), date(2023, 10, 3), date(2023, 10, 3), 1, 1),
    ])

    out = tmp_path / "provided_time_out"
    pipeline = CaseDiscoveryPipeline(
        paths["market"],
        paths["core"],
        paths["metadata"],
        out,
        product_time_summary=product_time,
    )
    try:
        summary = pipeline.run()
    finally:
        pipeline.close()

    assert summary["product_time_source"] == "provided"
    assert summary["candidate_case_count"] == 4
    assert summary["market_pre_t0_review_count_status"] == "UNAVAILABLE_WITHOUT_RATING_DAILY"
