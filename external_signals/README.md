# external_signals

这一层定义 **Keepa / 其它外部价格与销量代理** 如何进入 benchmark，但把“付费 API 怎么抓”与“Case 怎么使用这些历史序列”分开。

## 1. 输入接口

当前要求 provider adapter 最终整理成一张 Parquet：

```text
source_partition
product_id
event_timestamp / event_date
price              # 可选
bsr / sales_rank   # 可选
```

具体 Keepa JSON / token / 下载流程以后单独接；后续 Case 逻辑只认这张统一历史表。

## 2. Case 商品级外部信号

对每个 Case shelf 商品计算：

```text
price_at_t0
bsr_at_t0
external_snapshot_timestamp
future_bsr_observation_count
future_bsr_median
future_bsr_best
future_price_mean
external_future_bsr_rank
```

`t0` 使用向前 ASOF 历史记录；future BSR 统计只落在 Case evaluation window。

输出：

```text
case_product_external_signals.parquet
```

## 3. Case 级质量信号

再聚合出：

```text
price_at_t0_coverage
bsr_at_t0_coverage
future_bsr_coverage
focal_price_at_t0
focal_bsr_at_t0
focal_future_bsr_median
focal_external_future_bsr_rank
```

输出：

```text
case_external_signals.parquet
```

这张表可以直接传给：

```text
case_build.quality --external-signals
```

## 4. 历史价格回填 shelf

同时生成：

```text
case_shelf_with_external.parquet
```

如果外部历史里能找到 t0 价格：

```text
price_at_t0 = 外部历史值
price_source = external_history
```

找不到则保留原 shelf 的空值 / 原来源。Amazon metadata snapshot price 仍然只作为 metadata 参考。

## 5. 职责边界

本层负责：

```text
统一历史序列
→ Case t0 / future 对齐
→ coverage / rank / price signals
```

本层当前不负责：

```text
Keepa 账号与 token 管理
API 请求调度
网页手动导出
具体套餐限制
```

这些 provider-specific 获取逻辑见 [`TODO.md`](TODO.md)。
