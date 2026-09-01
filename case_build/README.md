# case_build

这一目录负责从 Final Market 生成完整的 Case 构建链。它已经不只包含商品侧，现在分成四段：

```text
Final Market
    ↓
1. Case Discovery
    ↓
2. t0 Shelf
    ↓
3. Case Population
    ↓
4. Ground Truth
    ↓
5. Quality Gate
```

最终 accepted cases 再交给根目录的 `benchmark_split/` 和 `benchmark_export/`。

---

## 1. Case Discovery

主要代码：

```text
product_timeline.py
market_timeline.py
case_discovery.py
time_windows.py
case_features.py
pipeline.py
cli.py
```

主要迁自 `AmazonReviewrepo@v5` 的商品时间、temporal segmentation 和 focal feature 计算。

保留：

- `t0 = first_rating_date`；
- Market 商品时间轴；
- active competitor 区间累计；
- `market_pre_t0_review_count` 的 many-to-one + ASOF 计算；
- 既有 `product_time_summary.parquet` 接口。

删除 / 后移：

- 一个时间段只取 top-1 focal；
- `post90>=50` 等旧 hard gate；
- competitor 数旧 hard gate。

一个 Market 中每个结构完整的新品进入事件都先形成 candidate case。

输出：

```text
market_product_map.parquet
market_product_timeline.parquet
case_candidates.parquet
case_candidates_evaluable.parquet
```

`case_candidates_evaluable` 这里只要求：

```text
valid_t0
evaluation_window_complete
```

---

## 2. t0 Shelf

主要代码：

```text
shelf.py
CaseShelfBuilder
```

一个 competitor 进入 Case shelf 需要：

```text
同一 Market
product_id != focal
first_rating_date < t0
last_rating_date >= t0
```

保留 v5 已验证的商品累计表 + ASOF 查询，计算：

```text
pre_t0_review_count
pre_t0_rating_mean
pre_t0_recent_review_count
```

当前不做：

```text
Top-150
最近120天>=10硬筛
8 CORE + 8 RESERVE
固定 competitor 数
```

Amazon metadata snapshot price 只保留成 `metadata_snapshot_price`，不会冒充历史 `price_at_t0`。

---

## 3. Case Population

目录：[`population/`](population/README.md)

```text
Market shared population
+ Case t0
+ 用户累计历史
        ↓
case_user_features
        ↓
threshold scan
        ↓
eligibility
        ↓
case_users
```

所有用户资格字段只来自 `t0` 以前；未来正例不能参与用户筛选。

核心输出：

```text
case_user_features.parquet
population_threshold_scan.parquet
case_user_eligibility.parquet
case_users.parquet
```

---

## 4. Ground Truth

目录：[`ground_truth/`](ground_truth/README.md)

Case 用户锁定之后才查询 future：

```text
future_market_events
        ↓
GT2: all case users -> product / none
        ↓
GT1: GT2 positives -> product
        ↓
market demand / share / rank
```

核心输出：

```text
choice_truth.parquet
population_truth.parquet
market_truth.parquet
```

可选：

```text
review_activity_truth.parquet
```

它直接对完整 shelf 的未来评论量排名，作为辅助商品侧真值 / 质量信号。

---

## 5. Quality Gate

目录：[`quality/`](quality/README.md)

把：

```text
商品侧
用户侧
GT1 / GT2
辅助 review ranking
外部 Keepa / BSR signals（可选）
```

汇总后输出：

```text
quality_metrics.parquet
quality_decisions.parquet
accepted_cases.parquet
rejected_cases.parquet
```

结构性完整性会直接检查；研究阈值全部由 JSON 配置，不把 v5 的旧数字写死。

---

## 6. 时间段

时间段仍使用：

- 2021 年以前按两年；
- 2021-2023 按半年。

它现在只是 Case 的 `time_box_id` 属性，不再产生 `Market Segment` 层级。

所有时间窗口使用半开区间 `[start, end)`。

---

## 7. 当前完整接口

```text
market_discovery/final_market.parquet
        ↓
case_build discover
        ↓
case_candidates_evaluable.parquet
        ↓
case_build shelf
        ↓
case_shelf.parquet
        ↓
case_build.population
        ↓
case_users.parquet
        ↓
case_build.ground_truth
        ↓
GT1 / GT2 / market truth
        ↓
case_build.quality
        ↓
accepted_cases.parquet
```

商品侧仍未冻结的规则见 [`TODO.md`](TODO.md)；用户、GT、Quality 各自的研究 TODO 放在对应子目录里。
