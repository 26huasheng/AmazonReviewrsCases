# case_build

这一目录负责把已经确认的 `Final Market` 转成一批真实新品进入事件的候选 Case，并在需要时给指定 Case 物化 `t0` 货架。

核心链条：

```text
final_market.parquet
        ↓
Market 商品展开
        ↓
商品首评 / 末评时间轴
        ↓
每个商品作为一次候选新品进入事件
        ↓
case_candidates.parquet
        ↓
结构完整的候选
case_candidates_evaluable.parquet
        ↓
先筛出准备继续处理的 Case
        ↓
显式调用 shelf 阶段
        ↓
case_shelf.parquet
```

这一版主要迁自 `AmazonReviewrepo@v5` 的：

```text
data_prep/product_time_summary.py
temporal_segmentation/attach_market_ids.py
temporal_segmentation/competitor_count_at_entry.py
temporal_segmentation/focal_prefilter.py
temporal_segmentation/assign_segments.py
competitor_selection/build_wide_pool.py
competitor_selection/activity_features.py
```

保留的是已经验证过的时间计算、累计统计和 ASOF 查询；旧的 focal top-1、未来评论量硬阈值、固定 competitor 数、150 截断、8 CORE + 8 RESERVE 都没有带进来。

## 1. Case Discovery

运行：

```bash
python -m case_build.cli discover \
  --final-market outputs/market_discovery/market_v1/final_market.parquet \
  --product-core /path/to/product_core.parquet \
  --product-time-summary /path/to/product_time_summary.parquet \
  --storage-metadata /path/to/storage_metadata.json \
  --output-dir outputs/case_build/discovery
```

如果没有现成 `product_time_summary.parquet`，也可以提供：

```bash
--rating-daily-summary /path/to/rating_daily_summary.parquet
```

代码会从逐日表重新生成商品首评/末评汇总。

### 输出

```text
<output-dir>/
├── market_product_map.parquet
├── market_product_timeline.parquet
├── case_candidates.parquet
├── case_candidates_evaluable.parquet
├── case_discovery_summary.json
└── _work/
    ├── product_time_summary.parquet        # 仅在没有外部输入时生成
    ├── active_product_interval_events.parquet
    ├── active_product_count_cumulative.parquet
    └── case_candidates_without_boxes.parquet
```

### `market_product_timeline.parquet`

一行一个 `Market × product`，主要字段：

```text
source_partition
market_id
market_label
product_id
product_title
first_rating_date
last_rating_date
post90_rating_count
entry_date = first_rating_date
entry_date_source = first_rating_date
```

### `case_candidates.parquet`

Market 中每个商品先形成一个候选新品进入事件：

```text
case_candidate_id
market_id
focal_product_id
t0
evaluation_start
evaluation_end_exclusive
evaluation_days
post90_rating_count
active_competitor_count_at_t0
valid_t0
evaluation_window_complete
time_box_id
```

这里 `post90_rating_count` 和 `active_competitor_count_at_t0` 只是质量统计字段，不会提前淘汰 Case。

`case_candidates_evaluable.parquet` 只做两项结构性筛选：

```text
valid_t0 = true
evaluation_window_complete = true
```

这不等于最终 accepted case，后面仍要结合用户、GT 和外部质量信号做 Quality Gate。

## 2. t0 货架

Shelf 阶段单独运行：

```bash
python -m case_build.cli shelf \
  --cases /path/to/cases_to_materialize.parquet \
  --market-timeline outputs/case_build/discovery/market_product_timeline.parquet \
  --rating-daily-summary /path/to/rating_daily_summary.parquet \
  --output-dir outputs/case_build/shelf
```

`--cases` 必须显式传入。这里没有默认把全部候选 Case 一次性展开成 `case × market products`，因为大 Market 上这样会产生非常大的中间表。正式大规模运行时应先筛出准备继续处理的 Case，再物化 shelf。

### 货架资格

一个同 Market 商品成为某 Case 的 competitor，需要：

```text
product_id != focal_product_id
first_rating_date < t0
last_rating_date >= t0
```

因此：

- 和 focal 同日首评的商品不算已有 competitor；
- `last_rating_date == t0` 的商品仍算 t0 当日活跃；
- 一个较早 Case 的 focal 可以在后续 Case 中自然成为 competitor。

### 商品历史特征

代码一次性生成：

```text
product_rating_cumulative.parquet
```

之后所有 Case 都通过 ASOF 查询得到：

```text
pre_t0_review_count
pre_t0_rating_mean
pre_t0_recent_review_count
```

默认最近窗口为 `[t0-120天, t0)`，起点当天计入，t0 当天不计入。

当前没有：

```text
最近120天 >= 10条 的硬门槛
150 个 competitor 截断
CORE / RESERVE 角色
固定 8 个 competitor
```

### 价格

`product_core.snapshot_price` 会保留为：

```text
metadata_snapshot_price
```

它不能冒充历史 `t0` 价格，因此当前：

```text
price_at_t0 = NULL
price_source = NULL
```

等 Keepa 历史价格接入后再填。

## 3. 时间段

默认时间段沿用此前确定的口径：

- 2021 年以前按两年一段；
- 2021、2022、2023 按半年一段。

时间段现在只是 Case 的 `time_box_id` 属性，不再生成 `Market Segment` 这一层。

所有区间使用半开区间：

```text
[start_date, end_date)
```

因此 `2023-H2` 写成：

```text
2023-07-01 <= t0 < 2024-01-01
```

## 4. 当前边界

这一目录只完成商品侧的 Case 骨架：

```text
Market
+
focal
+
t0
+
evaluation window
+
t0 shelf
+
pre-t0 商品统计
```

用户 population、Case 用户筛选、GT1 / GT2、最终 Quality Gate 和 benchmark split 在后续模块完成。

未定事项见 [`TODO.md`](TODO.md)。
