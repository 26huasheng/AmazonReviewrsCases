# external_signals TODO

## Provider 获取层

需要为 Keepa 单独补：

1. ASIN / parent_asin 到 Keepa product 的稳定映射；
2. 批量 API 请求与 token 预算；
3. 历史价格完整序列解析；
4. BSR 历史序列解析；
5. 缺失 / 下架 / 无 rank 的状态字段；
6. 原始响应与规范化 Parquet 的版本 / 时间戳记录。

## 研究口径

需要冻结：

- `price_at_t0` 允许向前回看多久；
- t0 当天有多条价格时取哪个值；
- future BSR 用 median / mean / best / cumulative rank 中哪一个做正式筛选；
- BSR 只在同 category / Market 内比较，还是做 category normalization；
- 外部销量代理只用于 Quality Gate，还是也进入最终 evaluator。

## 稳定接口

无论具体 provider 怎么变，下游尽量保持：

```text
case_product_external_signals.parquet
case_external_signals.parquet
case_shelf_with_external.parquet
```

这样 Keepa 获取逻辑不会侵入 Case / GT 主链。
