from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import duckdb

from utils import sql_literal


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.size: dict[str, int] = {}

    def add(self, value: str) -> None:
        if value not in self.parent:
            self.parent[value] = value
            self.size[value] = 1

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        self.add(left)
        self.add(right)
        a = self.find(left)
        b = self.find(right)
        if a == b:
            return
        if self.size[a] < self.size[b]:
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]


def _stable_component_id(source_partition: str, leaf_category: str, members: list[str]) -> str:
    payload = source_partition + "\x1f" + leaf_category + "\x1f" + "\x1f".join(sorted(members))
    return "graph_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def write_full_graph_components(
    con: duckdb.DuckDBPyConnection,
    full_graph_edges: Path,
    product_user_totals: Path,
    destination: Path,
    copy_atomic,
    *,
    min_endpoint_users: int,
) -> None:
    """对 full-period strong edges 在每个 leaf 内做连通分量。

    size >= 2 的连通分量写 `graph_status='component'`；完整时期用户数已经达到
    端点资格、但没有任何 strong edge 的商品写 `graph_status='isolated'`。
    """
    if min_endpoint_users <= 0:
        raise ValueError("min_endpoint_users must be positive")

    edges = sql_literal(str(full_graph_edges))
    totals = sql_literal(str(product_user_totals))

    eligible_rows = con.execute(f"""
        SELECT source_partition, leaf_category, product_id
        FROM read_parquet({totals})
        WHERE n_users_full >= {int(min_endpoint_users)}
          AND leaf_category IS NOT NULL
          AND trim(leaf_category) <> ''
        ORDER BY source_partition, leaf_category, product_id
    """).fetchall()

    by_leaf: dict[tuple[str, str], _UnionFind] = defaultdict(_UnionFind)
    eligible_by_leaf: dict[tuple[str, str], list[str]] = defaultdict(list)
    for source_partition, leaf_category, product_id in eligible_rows:
        key = (str(source_partition), str(leaf_category))
        product = str(product_id)
        eligible_by_leaf[key].append(product)
        by_leaf[key].add(product)

    edge_rows = con.execute(f"""
        SELECT source_partition, leaf_category, product_a, product_b
        FROM read_parquet({edges})
        ORDER BY source_partition, leaf_category, product_a, product_b
    """).fetchall()
    for source_partition, leaf_category, product_a, product_b in edge_rows:
        key = (str(source_partition), str(leaf_category))
        by_leaf[key].union(str(product_a), str(product_b))

    output_rows: list[tuple[str, str, str, str | None, int, str]] = []
    for (source_partition, leaf_category), products in sorted(eligible_by_leaf.items()):
        uf = by_leaf[(source_partition, leaf_category)]
        groups: dict[str, list[str]] = defaultdict(list)
        for product in products:
            groups[uf.find(product)].append(product)

        for members in groups.values():
            members = sorted(members)
            size = len(members)
            if size >= 2:
                component_id = _stable_component_id(source_partition, leaf_category, members)
                status = "component"
            else:
                component_id = None
                status = "isolated"
            for product in members:
                output_rows.append((
                    source_partition,
                    leaf_category,
                    product,
                    component_id,
                    size,
                    status,
                ))

    con.execute("DROP TABLE IF EXISTS behavior_graph_components_tmp")
    con.execute("""
        CREATE TEMP TABLE behavior_graph_components_tmp (
            source_partition VARCHAR,
            leaf_category VARCHAR,
            product_id VARCHAR,
            graph_component_id VARCHAR,
            component_size BIGINT,
            graph_status VARCHAR
        )
    """)
    if output_rows:
        con.executemany(
            "INSERT INTO behavior_graph_components_tmp VALUES (?, ?, ?, ?, ?, ?)",
            output_rows,
        )
    copy_atomic("""
        SELECT *
        FROM behavior_graph_components_tmp
        ORDER BY source_partition, leaf_category,
                 coalesce(graph_component_id, ''), product_id
    """, destination)
