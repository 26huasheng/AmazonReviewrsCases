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
        ├── user_market_history_cumulative.parquet
        └── behavior_graph/
              ├── full-period graph audit
              └── pre-t0 pair cumulative indexes
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

## 5. Behavior Graph：Market 内行为结构

`behavior_graph/` 单独实现用户—商品二部图投影 / 共评图逻辑。

它不重新定义 Final Market，作用是：

```text
Final Market 定义语义竞争边界
        +
真实用户共评关系
        ↓
Market 内哪些商品行为上更接近
```

分两种结果：

### Full-period graph

完整观测期生成 strong edges 和 connected components，用于审计 Final Market 与行为结构的一致性。完整时期结果不能直接参与历史 Case 选择。

### Pre-t0 cumulative graph

把用户对商品 pair 的共同用户贡献按首次同时成立日期累计。Case 给定 `t0` 后，通过 ASOF 得到：

```text
shared_users_pre_t0
endpoint_users_pre_t0
direct_strong_edge_pre_t0
same_component_pre_t0
graph_relation
```

默认沿用此前 Electronics 实验规则：

```text
same leaf category
两端用户数 >= 100
shared users >= 5
```

Case shelf 的时间资格仍由 `case_build` 决定，behavior graph 先作为竞品接近度 / 分层特征；以后若大 Market 需要 Top-K，优先考虑：

```text
direct strong edge
> same component
> same market other
```

详细逻辑、表结构和 TODO 见 [`behavior_graph/README.md`](behavior_graph/README.md) 与 [`behavior_graph/TODO.md`](behavior_graph/TODO.md)。

## 6. 运行

主 Market Build：

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

Behavior graph 基础索引 / full audit：

```bash
python -m market_build.behavior_graph.cli build \
  --canonical-user-events outputs/market_build/canonical_user_events.parquet \
  --market-products outputs/market_build/market_products.parquet \
  --output-dir outputs/market_build/behavior_graph
```

给一批已经物化的 Case shelf 加 pre-t0 graph 关系：

```bash
python -m market_build.behavior_graph.cli case \
  --case-shelf /path/to/case_shelf.parquet \
  --market-products outputs/market_build/market_products.parquet \
  --product-user-cumulative outputs/market_build/behavior_graph/product_user_cumulative.parquet \
  --pair-cumulative outputs/market_build/behavior_graph/pair_cumulative.parquet \
  --output-dir outputs/case_build/behavior_graph
```

`population_size`、`population_source`、graph threshold 都属于 benchmark 研究配置，代码支持但不在主流程里假装已经最终冻结。

## 7. 下游接口

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

behavior_graph/product_user_cumulative.parquet
behavior_graph/pair_cumulative.parquet
+ case_shelf.parquet
        ↓
behavior_graph case stage
        ↓
case_graph_features.parquet
        ↓
Case shelf graph-aware ranking / audit / Quality Gate
```

未冻结事项见 [`TODO.md`](TODO.md)；行为图自己的事项见 [`behavior_graph/TODO.md`](behavior_graph/TODO.md)。
