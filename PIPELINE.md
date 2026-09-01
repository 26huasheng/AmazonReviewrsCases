# End-to-End Pipeline Contract

这份文件只描述整条产线的 **阶段顺序、输入、输出和依赖关系**。概念说明看 `README.md`，最终文件字段看 `SCHEMA.md`，未冻结研究口径看 `TODO.md`。

## 0. Upstream 基础数据

当前新仓库优先复用 `AmazonReviewrepo@v5` 已经能够产出的基础表：

```text
product_core.parquet
product_time_summary.parquet        # 可选；没有时可从 rating_daily 重建
rating_daily_summary.parquet
storage_metadata.json
rating_event_store/ 或等价用户事件表
```

Market Discovery 还会读取自己的 `product_core` 输入并生成 `final_market.parquet`。

---

## 1. Population Scan

```text
用户事件
    ↓
population_scan
    ↓
users.parquet
summary.json
```

用途：扫描大类用户池与历史厚度分布。

---

## 2. Market Discovery

```text
product_core.parquet
    ↓
market_discovery
    ↓
first_market.parquet
    ↓
normalized exact-name cross-path merge
    ↓
final_market.parquet
```

Cross-path 不调用 LLM。

---

## 3. Market Build

```text
final_market.parquet
product_core.parquet
product_time_summary.parquet（可选）
population_scan/users.parquet
用户事件
    ↓
market_build
```

核心输出：

```text
market_products.parquet
market_population.parquet
canonical_user_events.parquet
user_history_cumulative.parquet
user_category_history_cumulative.parquet
user_market_history_cumulative.parquet
```

---

## 4. Case Discovery

```text
final_market.parquet
product_core.parquet
product_time_summary / rating_daily
storage_metadata.json
    ↓
case_build discover
```

输出：

```text
market_product_timeline.parquet
case_candidates.parquet
case_candidates_evaluable.parquet
```

这里只筛结构完整的时间事件，不执行最终质量阈值。

---

## 5. Case Shelf

```text
明确传入的一批 cases
market_product_timeline.parquet
rating_daily_summary.parquet
    ↓
case_build shelf
    ↓
case_shelf.parquet
```

Shelf 与全部 candidate cases 分开物化，避免超大 Market 自动产生完整 case×product 网格。

---

## 6. Case Population

```text
cases
market_population.parquet
三套 user history cumulative
    ↓
case_build.population
```

输出：

```text
case_user_features.parquet
population_threshold_scan.parquet
case_user_eligibility.parquet
case_users.parquet
```

这里完全不读 future GT。

---

## 7. Ground Truth

```text
cases
case_users.parquet
case_shelf.parquet
canonical_user_events.parquet
rating_daily_summary.parquet（可选）
    ↓
case_build.ground_truth
```

输出：

```text
choice_truth.parquet
population_truth.parquet
market_truth.parquet
review_activity_truth.parquet（可选）
```

---

## 8. External Signals（可选）

```text
cases
case_shelf.parquet
provider-agnostic price / BSR history
    ↓
external_signals
```

输出：

```text
case_product_external_signals.parquet
case_external_signals.parquet
case_shelf_with_external.parquet
```

如果要让历史 t0 价格进入最终 benchmark，后续 Quality / Export 使用 `case_shelf_with_external.parquet` 作为 shelf 输入。

---

## 9. Quality Gate

```text
cases
case_shelf
case_users
GT1 / GT2 / market truth
review_activity_truth（可选）
case_external_signals（可选）
quality_rules.json
    ↓
case_build.quality
```

输出：

```text
quality_metrics.parquet
quality_decisions.parquet
accepted_cases.parquet
rejected_cases.parquet
```

---

## 10. Benchmark Split

```text
accepted_cases.parquet
    ↓
benchmark_split
```

输出：

```text
split_assignments.parquet
learning.json
validation.json
evaluation.json
```

Split 不使用 GT 数值决定归属。

---

## 11. Benchmark Export

```text
final_market
market_products
market_population
canonical_user_events
accepted_cases
case_shelf
case_users
GT1 / GT2 / market truth
split_assignments
    ↓
benchmark_export
```

先做跨表一致性检查，再生成 `SCHEMA.md` 的最终 `benchmark_data/`。

---

## 12. Evaluation

模拟器 / agent 至少输出：

```text
case_candidate_id
user_id
predicted_outcome_product_id
```

然后：

```text
predictions
+ GT1 / GT2 / market truth
    ↓
evaluation
    ↓
individual_metrics.parquet
market_metrics.parquet
case_metrics.parquet
evaluation_summary.json
```

---

# 核心依赖图

```text
population_scan ─────────────┐
                             ▼
market_discovery ───────► market_build
       │                     │
       ▼                     │
case discovery               │
       ▼                     │
case shelf                   │
       └──────────┬──────────┘
                  ▼
          case population
                  ▼
            ground truth
                  │
       external ──┤
                  ▼
             quality
                  ▼
               split
                  ▼
              export
                  ▼
             evaluation
```

# 版本化原则

正式 benchmark 发布时至少要记录：

```text
market discovery version
population policy + seed
Case eligibility thresholds
GT outcome policy
quality rules version
split strategy + seed
external signal source/version（如果使用）
schema version
```

其中阈值还没冻结的项目统一见根目录 `TODO.md`。
