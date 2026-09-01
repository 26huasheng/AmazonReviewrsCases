# TODO：Case Build 后续事项

当前 `case_build` 已经接通商品侧主链，但下面这些规则还没有在没有数据依据的情况下写死。

## 1. Shelf 最终截断规则

当前 t0 时间资格通过的商品全部进入 shelf 候选，不做：

```text
Top-150
Top-8
8 CORE + 8 RESERVE
```

需要先统计真实 `Market × Case` 的 shelf size 分布，再决定：

- 是否需要上限；
- 大 Market 如何截断；
- 截断时用长期热度、近期活跃度、价格还是其他规则排序。

这一步确定前，正式大规模运行应先选出需要继续处理的 Case，再调用 shelf 物化，避免超大 Market 的 `case × product` 展开。

## 2. 活跃度阈值

目前已经计算：

```text
pre_t0_recent_review_count
```

默认窗口为 `[t0-120天, t0)`。

v5 的 `>=10` 只保留为历史参考，没有继续作为硬门槛。需要在真实分布和 Case 保留率统计后冻结阈值。

## 3. `last_rating_date >= t0` 的含义

当前用首评/末评观测区间近似商品在市场中的可见生命周期：

```text
first_rating_date < t0
last_rating_date >= t0
```

这是 Amazon Reviews 数据上的可操作代理，并不等同于真实 Amazon 上架/下架状态。后续若 Keepa 能稳定提供商品 availability / offer history，需要评估是否替换或增强这个资格定义。

## 4. 历史价格

当前只有 Amazon metadata snapshot price，因此：

```text
metadata_snapshot_price   # 保留
price_at_t0 = NULL
```

待 Keepa 接入以后，需要：

- 定义 `price_at_t0` 的取值规则；
- 处理 t0 当天无价格记录时的最近值回填；
- 保存价格来源和时间戳；
- 明确价格序列的缺失处理。

## 5. Case Quality Gate

当前只做结构性检查：

```text
valid_t0
evaluation_window_complete
```

还没有用下面这些字段提前淘汰：

```text
post90_rating_count
active_competitor_count_at_t0
shelf size
```

最终 Quality Gate 需要和后续用户侧一起决定，并至少纳入：

```text
可用用户数
GT1 正样本数
GT2 market-positive 数
none 比例
商品侧未来活动量
外部 BSR / sales proxy
```

## 6. Final Case 物化

现在输出仍是构造阶段的扁平表：

```text
case_candidates.parquet
case_shelf.parquet
```

等 Population + GT + Quality Gate 完成后，再按照根目录 `SCHEMA.md` 物化成：

```text
benchmark_data/markets/<market_id>/cases/<case_id>/
├── case_manifest.json
├── shelf.parquet
├── users.parquet
└── ground_truth/
```

最终 `case_id` 的正式分配也放在这一步完成；当前使用稳定的 `case_candidate_id`。

## 7. 大规模性能审计

代码沿用了 v5 已验证的：

- 区间事件累计计算 active competitor 数；
- 商品累计评论表只算一次；
- ASOF 查询 pre-t0 特征。

仍需在真实最大 Market 上单独审计 shelf 输出规模、DuckDB 临时磁盘占用和运行时间。
