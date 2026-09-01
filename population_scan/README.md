# population_scan

这一层只做 **Amazon 大类级、case-agnostic 的用户基础扫描**。它回答“这个大类里有哪些用户、每个人历史有多厚”，不做 Market / Case 用户选择，也不看任何 case 未来数据。

## 输入

支持：

- Amazon `rating_only` 风格 CSV / TSV；
- 已整理的 Parquet 事件表；
- `AmazonReviewrepo@v5` 的 `rating_event_store/` 目录。

代码会识别常见字段：

```text
user_id / consumer_id
product_id / parent_asin / asin
timestamp / event_time_ms / event_timestamp
verified_purchase（可选）
```

如果输入自身没有 `source_partition`，运行时必须通过 `--source-partition` 指定大类。

## 输出

```text
<output-dir>/
├── users.parquet
└── summary.json
```

`users.parquet` 一行一个大类用户：

```text
source_partition
user_id
n_events
n_products
n_verified_purchases
first_event_date
last_event_date
```

口径固定为：

- `n_events`：每条观测评分/评论事件计一次；
- `n_products`：该用户在当前大类碰过的不同商品数；
- `verified_purchase` 有则另计，不把公开 Review 数据说成完整订单流水；
- 本层不做 `t0` 截断。

`summary.json` 记录用户量、事件量、用户历史厚度分位数、单次用户比例、输入字段解析方式等，后面用来定 Case 用户资格阈值。

## 运行

```bash
python -m population_scan.cli \
  --events /path/to/Home_and_Kitchen.csv \
  --source-partition Home_and_Kitchen \
  --output-dir outputs/population_scan/Home_and_Kitchen
```

或者直接扫 v5 event store：

```bash
python -m population_scan.cli \
  --events /path/to/rating_event_store \
  --output-dir outputs/population_scan/all
```

## 在整体流程里的位置

```text
Amazon 用户事件
      ↓
population_scan
      ↓
大类用户基础表
      ↓
market_build 组织 Market shared population
      ↓
case_build/population 按每个 Case 的 t0 做资格计算与采样
```

这一层不会根据未来是否购买来选人，因此不会污染 GT2 的 `none`。

未定事项见 [`TODO.md`](TODO.md)。
