# population_scan TODO

当前代码已经完成大类用户基础扫描；下面这些留给真实数据分布或上游数据口径确认后再冻结。

## 需要用真实数据确认

1. `rating_only` 在正式数据目录中的最终字段名与时间单位；当前适配器同时兼容秒 / 毫秒时间戳和常见列名。
2. 同一 `user_id × product_id` 是否可能存在多条评分记录；当前 `n_events` 按源事件逐条计数，`n_products` 单独做 distinct。
3. 全量扫描后记录各大类 `n_products`、recency 分布，为 Case 用户硬阈值提供依据。

## 后续可选增强

- 全文 review JSONL 的 `verified_purchase` 扫描；
- 大类间同一用户的跨类覆盖统计；
- 仅用于发布数据时的用户 ID 匿名化策略。

这些增强不会改变本层职责：这里只做大类基础盘点，不根据 Market / Case future outcome 选用户。
