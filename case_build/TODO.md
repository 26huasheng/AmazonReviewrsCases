# case_build TODO

`case_build` 的商品侧、用户侧、GT 和 Quality Gate 代码骨架都已经接通。这个总 TODO 只保留跨商品侧的未冻结事项；更细的研究口径分别见：

```text
population/TODO.md
ground_truth/TODO.md
quality/TODO.md
```

## 1. Shelf 规模规则已经冻结

基础时间资格：

```text
product_id != focal
first_rating_date < t0
last_rating_date >= t0
```

然后执行固定的 competitor cap：

```text
K = 16
```

规则：

```text
competitor 数 <= 16
→ 全部保留

competitor 数 > 16
→ 使用 market_build/behavior_graph 的严格 pre-t0 focal 共评关系筛选
→ 强共评优先
→ 不足 16 时按 pre_t0_recent_review_count 补齐
```

因此最终一个 Case 最多：

```text
1 focal + 16 competitors
```

旧的 `Top-150 / 8 CORE + 8 RESERVE` 不再使用。

## 2. 商品活跃度阈值

已经计算：

```text
pre_t0_recent_review_count
```

默认最近窗口 `[t0-120天, t0)`。

当前它主要作为 behavior graph 不足 16 个强共评竞品时的补位排序信号；是否另外把它做成 Case 硬资格阈值，仍需后续决定。

## 3. 商品“仍在市场”代理

当前使用：

```text
first_rating_date < t0
last_rating_date >= t0
```

它表示 Amazon Reviews 观测意义下的活跃区间。后续如果 Keepa 能提供更可靠的 availability / offer history，可以增强这一资格定义。

## 4. 历史价格

当前：

```text
metadata_snapshot_price   # 只作 metadata 参考
price_at_t0 = NULL
price_source = NULL
```

Keepa 接入后需要冻结：

- t0 当日价格取值；
- 当日缺失时的最近历史值规则；
- 价格时间戳与来源字段；
- 价格序列缺失处理。

## 5. Case candidate 到正式 case_id

构建阶段继续使用稳定的：

```text
case_candidate_id
```

最终 exporter 当前直接把它作为目录 case id。若论文 / 发布版需要另一套短 ID，应在 export 阶段增加显式映射表，不修改上游事实表主键。

## 6. 工程优化

大 Market 正式全量运行时可以继续增加：

- shelf 分批物化；
- behavior graph Market 分块；
- checkpoint / resume；
- DuckDB 临时目录容量统计；
- Market 级并行。

这些只影响运行方式，不改变当前 Case 数据语义。
