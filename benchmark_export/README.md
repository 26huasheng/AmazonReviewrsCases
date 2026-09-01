# benchmark_export

这一层是最终收口：把前面所有长表构建产物做跨表一致性检查，然后物化成 [`SCHEMA.md`](../SCHEMA.md) 定义的 `Market → Cases` benchmark 目录。

## 输入

```text
final_market.parquet
market_products.parquet
market_population.parquet
canonical_user_events.parquet
accepted_cases.parquet
case_shelf.parquet
case_users.parquet
choice_truth.parquet
population_truth.parquet
market_truth.parquet
split_assignments.parquet
```

## 1. 导出前验证

`validate.py` 检查：

- accepted case id 唯一；
- focal 在 shelf 中恰好一行；
- GT2 覆盖全部 Case 用户；
- GT2 的商品结果都属于 shelf；
- GT1 与 GT2 正例完全一致；
- `market_truth.demand_count` 与 GT2 聚合一致；
- split 对 accepted cases 一一覆盖且无重复。

验证失败会停止最终物化，并写 `validation_report.json`。

## 2. 最终目录

```text
benchmark_data/
├── benchmark_manifest.json
├── validation_report.json
├── markets/
│   └── <market_id>/
│       ├── market_manifest.json
│       ├── products.parquet
│       ├── population/
│       │   ├── users.parquet
│       │   └── interactions.parquet
│       └── cases/
│           └── <case_id>/
│               ├── case_manifest.json
│               ├── shelf.parquet
│               ├── users.parquet
│               └── ground_truth/
│                   ├── choice_truth.parquet
│                   ├── population_truth.parquet
│                   └── market_truth.parquet
└── splits/
    ├── learning.json
    ├── validation.json
    └── evaluation.json
```

Market 的完整用户历史只在 Market population 下保存一次；Case 只保存自己的 `user_id` 列表和 GT。

## 3. Build 长表与最终文件的关系

前面阶段尽量使用大 Parquet 长表，避免产生海量小文件；只有这里才按 Market / Case 正式物化目录。

因此：

```text
case_users.parquet
```

是构建层长表；导出后每个 Case 的：

```text
users.parquet
```

只剩 `user_id`。

同理 `market_truth` 构建表可以带质量统计，最终 schema 只导出：

```text
product_id
demand_count
demand_share
rank
```

## 4. 运行

```bash
python -m benchmark_export.cli \
  --final-market ... \
  --market-products ... \
  --market-population ... \
  --canonical-user-events ... \
  --accepted-cases ... \
  --case-shelf ... \
  --case-users ... \
  --choice-truth ... \
  --population-truth ... \
  --market-truth ... \
  --split-assignments ... \
  --output-dir benchmark_data
```

未冻结的发布 / 体积问题见 [`TODO.md`](TODO.md)。
