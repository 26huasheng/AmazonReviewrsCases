# behavior_graph

这一目录负责把 Amazon Reviews 中的 **用户—商品行为关系** 转成 Final Market 内的商品共评图，并给历史 Case 提供严格的 `pre-t0` 行为关系特征。

它的定位固定为：

- Market Discovery 定义语义上的市场边界；
- behavior_graph 描述同一个 Market 内商品之间真实用户行为有多接近；
- 图不会重新定义 Final Market；
- 图可以用于 Market 审计，也可以在 Case shelf 里标记“核心竞品 / 近邻竞品”。

## 1. 已有实验口径

此前在 Electronics 上做过一次完整时期共评投影实验。口径为：

```text
同一个 Amazon leaf category
两端商品各自 n_users >= 100
shared_users >= 5
```

对通过强边条件的商品对，在每个 leaf 内做连通分量；size >= 2 的连通分量形成 graph group，没有强边的合格商品记为 isolated。

该实验从约 62.71M 个共评商品对筛到 27,457 条同 leaf 强边。这个结果用于说明：已有语义 Market 与真实用户共评结构总体相容，同时 Market 内仍可能存在更紧的行为子群。

完整时期图只适合做 **审计 / 研究分析**，不能直接参与历史 Case 的 shelf 选择，因为完整时期图包含 t0 之后的用户行为。

## 2. 两套结果

### 2.1 Full-period audit graph

使用完整观测期：

```text
all user-product interactions
    -> user-product first interaction
    -> same-leaf product pairs
    -> shared-user counts
    -> strong edges
    -> connected components
```

用途：

- 对照 Final Market 与行为图的一致性；
- 统计一个语义 Market 内有几个明显行为子群；
- 统计 strong-edge / isolated 比例；
- 复现此前 Electronics 实验。

这套图允许使用完整时期数据，因为它只做 benchmark 构建侧审计，不作为历史 Case 的可见输入。

### 2.2 Pre-t0 cumulative graph

真正给 Case 用的图必须只使用 t0 以前已经发生的行为。

先把用户第一次碰到商品的时间压成：

```text
user_id, product_id, first_event_date
```

同一个用户同时碰过 A、B 时，这个用户对 A-B 共评边的贡献生效时间定义为：

```text
pair_event_date = max(first_A_date, first_B_date)
```

例如：

```text
U1: A=2020-01-01, B=2020-06-01
=> U1 从 2020-06-01 起才算 A-B 的共同用户
```

把所有用户贡献按日期累计后，可以得到：

```text
product_a
product_b
event_date
shared_users_cumulative
```

某个 Case 给定 `t0` 后，只需 ASOF 查询：

```text
shared_users_pre_t0
```

不需要为每个 Case 重新扫描全量用户记录。

## 3. 默认强边规则

默认保留此前实验的保守规则：

```text
same leaf_category
focal_users_pre_t0 >= 100
competitor_users_pre_t0 >= 100
shared_users_pre_t0 >= 5
```

`100 / 5` 集中放在 `config.py`，以后如果需要根据全量分布调整，只改版本配置。

Full-period audit 也使用同一套默认阈值，便于和此前实验口径对照。

## 4. 在 Case shelf 里的使用方式

Case shelf 的基本资格仍由商品时间条件决定：

```text
same Final Market
product_id != focal
first_rating_date < t0
last_rating_date >= t0
```

behavior graph 不负责先删除这些商品，而是给 shelf 增加关系特征：

```text
shared_users_pre_t0
focal_users_pre_t0
competitor_users_pre_t0
jaccard_pre_t0
overlap_min_pre_t0
direct_strong_edge_pre_t0
same_component_pre_t0
graph_relation
```

`graph_relation` 解释为：

```text
direct_strong_edge
same_component
same_market_other
isolated
```

因此当前设计是：

```text
Market 决定语义竞争边界
时间资格决定 t0 时谁在场
Graph 决定谁与 focal 行为上更近
活跃度决定当时谁更重要
```

如果以后因为 shelf 太大需要 Top-K，推荐优先级：

```text
1. focal 直接 strong-edge 商品
2. focal 同 graph component 商品
3. 同 Market 其他商品
```

每层内部再按 `pre_t0_recent_review_count` / `pre_t0_review_count` 等 t0 前特征排序。当前模块只生成关系和分层，不写死最终 Top-K。

## 5. 目录

```text
behavior_graph/
├── README.md
├── TODO.md
├── __init__.py
├── config.py
├── user_product.py
├── pair_events.py
├── cumulative.py
├── components.py
├── audit.py
├── case_features.py
└── pipeline.py
```

## 6. 主要中间表

### `user_product_first.parquet`

```text
source_partition
user_id
product_id
leaf_category
first_event_date
```

一个用户对一个商品只保留第一次观测时间。

### `product_user_cumulative.parquet`

```text
source_partition
product_id
event_date
users_cumulative
```

表示截至某一天一个商品累计有多少不同用户。

### `pair_user_events.parquet`

```text
source_partition
leaf_category
product_a
product_b
user_id
pair_event_date
```

一行表示一个用户何时开始成为 A、B 的共同用户。

### `pair_cumulative.parquet`

```text
source_partition
leaf_category
product_a
product_b
event_date
shared_users_cumulative
```

给 Case 做 `pre-t0` ASOF 查询。

### `full_graph_edges.parquet`

完整时期强边，仅用于审计。

### `full_graph_components.parquet`

完整时期连通分量，仅用于审计。

### `graph_market_overlap.parquet`

把 full-period component 映射回 Final Market，统计 component × Market 的商品重叠。

### `case_graph_features.parquet`

给 Case shelf 使用：

```text
case_candidate_id
market_id
focal_product_id
product_id
t0
shared_users_pre_t0
focal_users_pre_t0
competitor_users_pre_t0
jaccard_pre_t0
overlap_min_pre_t0
direct_strong_edge_pre_t0
same_component_pre_t0
graph_relation
```

## 7. 关键原则

1. Full-period graph 可以看未来，只做审计。
2. 任何真正影响历史 Case 的 graph feature 必须只使用 `< t0` 数据。
3. Final Market 仍是一级市场定义，graph component 不改名为 Market。
4. graph 先作为竞品接近度特征，不直接替代完整 shelf。
5. 用户对同一商品多次评论只贡献一个 user-product membership，避免重复计数。
6. pair 只在同 leaf 内生成，避免跨最细 Amazon 类目的共评关系把图连脏。
7. pair 构造时可以用“完整时期总用户数 < 100 的商品永远不可能成为强边端点”做安全预剪枝；这个剪枝不会给历史 Case 引入未来正信息，只排除永远达不到阈值的商品。
