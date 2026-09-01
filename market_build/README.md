# market_build

这一层负责把 `Final Market` 变成后续多个 Case 可以复用的 **Market-level 资产**。

主链：

```text
final_market.parquet
+ product_core / product_time_summary
+ population_scan users
+ Amazon 用户事件
        ↓
market_build
        ├── market_products.parquet
        ├── market_population.parquet
        ├── canonical_user_events.parquet
        ├── user_event_store/
        ├── user_history_cumulative.parquet
        ├── user_category_history_cumulative.parquet
        └── user_market_history_cumulative.parquet
```

## 1. Market 商品资产

`market_products.parquet` 一行一个 `Market × product`，把 Final Market 的商品 universe 与 metadata / 首评时间拼起来。它对应最终 schema 中每个 Market 的 `products.parquet` 的长表版本。

## 2. 统一用户事件

`user_events.py` 兼容：

- v5 `rating_event_store/`；
- 普通 Parquet；
- rating_only 风格 CSV / TSV。

统一字段：

```text
source_partition
user_id
product_id
event_timestamp
event_date
rating
verified_purchase
```

同时生成按 `user_id` 哈希分桶的 `user_event_store/`，服务后续大量用户历史查询。

## 3. Market shared population

`market_population.parquet` 给每个 Market 固定一批共享候选用户。

当前支持两种来源：

```text
category  -> 从 Market 所在 Amazon 大类用户池组织
global    -> 从全局用户池组织
```

可以通过 `population_size` 做确定性哈希抽样；同一 Market 在同一 seed 下用户集合稳定。

这里不看任何 Case 的 future outcome，所以不会因为“未来买了”才被选入人口池。

## 4. 用户历史累计索引

为了后面按很多不同 `t0` 查询用户历史，本层一次性生成三套累计表：

```text
user_history_cumulative
  用户全局历史事件数 / 不同商品数

user_category_history_cumulative
  用户在某 Amazon 大类的历史

user_market_history_cumulative
  用户在某 Final Market 的历史
```

不同商品数通过“用户第一次碰到该商品的日期”累计，重复评分不会把历史商品数重复增加。

## 5. 运行

```bash
python -m market_build.cli \
  --final-market outputs/market_discovery/market_v1/final_market.parquet \
  --product-core /path/to/product_core.parquet \
  --product-time-summary /path/to/product_time_summary.parquet \
  --user-events /path/to/rating_event_store \
  --user-summary outputs/population_scan/all/users.parquet \
  --population-source category \
  --population-size 50000 \
  --output-dir outputs/market_build
```

`population_size` 和 `population_source` 属于 benchmark 研究配置，代码支持但不在仓库里写死最终值。

## 6. 下游接口

```text
market_products.parquet
        ↓
case_build / benchmark_export

market_population.parquet
+ 三套 user history cumulative
        ↓
case_build/population

canonical_user_events.parquet
        ↓
case_build/ground_truth
```

未冻结事项见 [`TODO.md`](TODO.md)。
