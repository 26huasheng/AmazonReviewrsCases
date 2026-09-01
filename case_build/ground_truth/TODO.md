# Ground Truth TODO

## 最重要的未冻结口径

同一用户在一个 evaluation window 内命中多个 shelf 商品时，最终 target 的唯一化规则还需要正式确认。

当前代码提供：

```text
first_observed_event
```

并保留全部 `future_market_events.parquet`，所以以后改 policy 不需要重新读原始数据。

候选替代规则可以包括：

- 第一条观测事件；
- 第一条 verified_purchase 事件，没有 verified 再回退第一条；
- 规定时间窗内的最后一次选择；
- 多商品 outcome（这会改变 GT1 / GT2 schema，需要单独版本）。

## 需要继续确认

1. evaluation window 是否全 benchmark 固定 90 天，还是允许 Case 配置其他长度。
2. `review_activity_truth` 是否进入正式商品侧评测，还是只做质量检查 / 辅助对照。
3. 是否需要额外导出逐周 / 截至第 N 天的 demand ranking；v5 `weekly_truth` 可以继续迁来作为派生 truth。
4. Amazon Review 观测事件与真实购买的命名在论文和 benchmark 文档中保持一致，避免把 review observation 直接称作完整订单。

## 固定原则

- Case population 必须先锁定，再查询 future；
- GT2 必须覆盖全部 Case 用户；
- GT1 必须与 GT2 正例完全一致；
- `none` 只表示公开数据中未观测到当前 shelf 的目标交互。
