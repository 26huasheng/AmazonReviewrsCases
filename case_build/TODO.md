# case_build TODO

`case_build` 的商品侧、用户侧、GT 和 Quality Gate 代码骨架都已经接通。这个总 TODO 只保留跨商品侧的未冻结事项；更细的研究口径分别见：

```text
population/TODO.md
ground_truth/TODO.md
quality/TODO.md
```

## 1. Shelf 最终规模规则

当前所有通过时间资格的商品都进入 shelf：

```text
product_id != focal
first_rating_date < t0
last_rating_date >= t0
```

尚未决定：

- 是否需要 shelf size 上限；
- 极大 Market 是否截断；
- 截断时依据长期评论量、近期活跃度、价格或其它信号。

v5 的 `Top-150 / 8 CORE + 8 RESERVE` 没有继续写死。

## 2. 商品活跃度阈值

已经计算：

```text
pre_t0_recent_review_count
```

默认最近窗口 `[t0-120天, t0)`。

是否要求最近窗口至少多少条评论，需要看真实 shelf size / 活跃度分布以后冻结。

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
- checkpoint / resume；
- DuckDB 临时目录容量统计；
- Market 级并行。

这些只影响运行方式，不改变当前 Case 数据语义。
