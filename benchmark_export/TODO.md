# benchmark_export TODO

## 发布形态

1. 内部 benchmark 是否保留原始 `user_id`，公开发布时是否稳定匿名化。
2. Market `population/interactions.parquet` 当前保存该 Market 用户的完整可用轨迹；如果最终发布包体积过大，可改成共享全局 event store + manifest 引用，但不能让 Case 重复保存历史。
3. held-out evaluation 的 GT 是否独立放在 evaluator 可见、evolving agent 不可见的位置，取决于最终评测平台的隔离方式。

## Schema 演进

- Keepa 历史价格接入后，把 `price_at_t0 / price_source` 进入最终 shelf。
- 如果 GT outcome policy 改成多商品结果，需要新 schema version，不能静默替换现有 `user -> one product / none`。
- 如果增加 weekly / cumulative truth，作为 `ground_truth/derived/` 一类派生目录，不改变 GT1 / GT2 canonical tables。

## 大规模物化

当前 exporter 逻辑按 Market / Case 逐个写文件，职责清楚。正式全量发布时可以再增加：

- 并行 Market export；
- 小文件合并 / 分区策略；
- checksum manifest；
- 可恢复的 export checkpoint。

这些属于发布工程优化，不改变 benchmark 数据语义。
