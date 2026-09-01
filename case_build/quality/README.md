# case_build/quality

这一层把商品侧、用户侧、GT 和可选外部信号汇总成一张 Case 质量表，再执行显式配置的 acceptance gate。

```text
case candidates
+ shelf
+ case users
+ GT1 / GT2 / market truth
+ review_activity_truth（可选）
+ Keepa / BSR external signals（可选）
        ↓
quality_metrics.parquet
        ↓
quality_decisions.parquet
        ├── accepted_cases.parquet
        └── rejected_cases.parquet
```

## 1. 自动汇总的质量字段

当前包括：

```text
shelf_product_count
competitor_count
focal_rows
focal_pre_t0_review_count
focal_recent_review_count
selected_user_count
gt1_user_count
gt2_user_count
market_positive_user_count
none_user_count
none_rate
gt2_coverage_complete
focal_demand_count
focal_demand_share
focal_demand_rank
focal_review_activity_count / rank（可选）
```

同时保留 Case Discovery 已有的：

```text
post90_rating_count
active_competitor_count_at_t0
market_pre_t0_review_count
valid_t0
evaluation_window_complete
```

## 2. 结构性检查

这些直接属于数据完整性，不等真实分布：

```text
valid_t0 = true
evaluation_window_complete = true
shelf 中 focal 恰好一行
GT2 用户数 == selected Case 用户数
```

## 3. 研究阈值

以下门槛全部通过 JSON 配置，可为空：

```text
min_shelf_products
min_competitors
min_selected_users
min_gt1_users
min_market_positive_users
max_none_rate
min_focal_demand_count
min_post90_rating_count
min_market_pre_t0_review_count
require_review_activity_truth
```

仓库没有重新把 v5 的 `post90>=50 / competitor>=5 / 8+8` 偷偷写回默认规则。

## 4. 外部销量 / BSR 接口

`--external-signals` 可以传一张以 `case_candidate_id` 为键的 Parquet。Quality stage 会把其它列直接拼到 `quality_metrics`。

因此 Keepa 接入以后可以增加例如：

```text
focal_bsr_available
market_bsr_coverage
external_sales_proxy_rank
external_quality_pass
```

获取 Keepa 数据本身单独实现，Quality Gate 不依赖某个具体供应商 API。

## 5. 运行

```bash
python -m case_build.quality.cli \
  --cases /path/to/cases.parquet \
  --case-shelf /path/to/case_shelf.parquet \
  --case-users /path/to/case_users.parquet \
  --choice-truth /path/to/choice_truth.parquet \
  --population-truth /path/to/population_truth.parquet \
  --market-truth /path/to/market_truth.parquet \
  --review-activity-truth /path/to/review_activity_truth.parquet \
  --rules-json quality_rules.json \
  --output-dir outputs/quality
```

未冻结事项见 [`TODO.md`](TODO.md)。
