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
              ├── Market 内共评累计索引
              └── full-period audit graph
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

## 5. Behavior Graph：只服务竞品过多时的筛选

`behavior_graph/` 负责 Final Market 内的共评关系。

正式用途固定为：

```text
Final Market 定义竞争边界
+t0 决定当时谁在场
+共评关系只在 competitor pool > 16 时帮助 focal 选更近的竞品
```

不根据 graph component 分裂 Final Market。

### Pair 范围

正式 pair 只在：

```text
同 Final Market
+同 leaf category
```

内部生成。

### Pre-t0 累计

用户对 A-B pair 的共同用户贡献从：

```text
max(first_A_date, first_B_date)
```

开始生效。Case 查询严格使用：

```text
event_date < t0
```

主要长期索引：

```text
product_user_cumulative.parquet
pair_cumulative.parquet
```

### 固定竞品上限

```text
K = 16 competitors
```

规则：

```text
competitor 数 <= 16
→ 全部保留

competitor 数 > 16
→ focal-centered pre-t0 共评筛选
```

强共评定义：

```text
same leaf
focal_users_pre_t0 >= 100
competitor_users_pre_t0 >= 100
shared_users_pre_t0 >= 5
```

选择顺序：

```text
强共评优先
→ shared_users_pre_t0 降序
→ 不足16时按 pre_t0_recent_review_count 补齐
→ pre_t0_review_count / product_id tie-break
```

最终输出：

```text
case_shelf_selected.parquet
```

一个 Case 最多：

```text
1 focal + 16 competitors
```

### Full-period audit

完整时期 strong edges / connected components 仍保留做研究审计和此前 Electronics 预实验复现，但不参与历史 Case 的正式选择。

详细见 [`behavior_graph/README.md`](behavior_graph/README.md)。

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

给一批完整 Case shelf 做最终最多16竞品的选择：

```bash
python -m market_build.behavior_graph.cli case \
  --case-shelf /path/to/case_shelf.parquet \
  --market-products outputs/market_build/market_products.parquet \
  --product-user-cumulative outputs/market_build/behavior_graph/product_user_cumulative.parquet \
  --pair-cumulative outputs/market_build/behavior_graph/pair_cumulative.parquet \
  --output-dir outputs/case_build/behavior_graph
```

默认即使用：

```text
min_endpoint_users = 100
min_shared_users = 5
max_competitors = 16
```

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
+ 完整 case_shelf.parquet
        ↓
behavior_graph case stage
        ↓
case_shelf_selected.parquet
        ↓
Case Population / GT / Quality / Export
```

未冻结事项见 [`TODO.md`](TODO.md)；行为图自己的工程事项见 [`behavior_graph/TODO.md`](behavior_graph/TODO.md)。
