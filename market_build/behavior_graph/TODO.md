# TODO：Behavior Graph

这里记录共评图还没有冻结的研究口径和工程优化。当前代码优先把“发现逻辑”完整落下来，不要求立即作为正式 Case 筛选硬规则。

## 1. 强边阈值是否继续冻结为 100 / 5

当前默认沿用 Electronics 实验：

```text
endpoint users >= 100
shared users >= 5
same leaf category
```

正式 benchmark 前需要在多个 Amazon 大类上统计：

- eligible product 数；
- pair 数；
- strong-edge 数；
- component size 分布；
- isolated 比例；
- 每个 Final Market 内 graph component 数量；
- graph component 与 Final Market 的重叠率。

如果不同大类密度差异非常大，再考虑大类自适应阈值；第一版先保持固定规则，便于和已有实验对照。

## 2. leaf category 的正式来源

当前从 `market_products.category_path` 的最后一级派生 `leaf_category`。

需要确认正式全量数据里：

- category_path 是否总是完整；
- 一个 product 是否可能出现多个 path；
- 是否要直接复用此前二部图实验里的 `product_nodes.leaf_category` canonical 表。

如果已有更稳定的 leaf canonical 表，优先把它作为显式输入，避免在这里重复解释 category path。

## 3. Pair 构造的规模优化

当前逻辑是：

```text
user-product first membership
-> 同 user + 同 leaf 自连接
-> product_a < product_b
```

这是定义上最直接的实现，但高活跃用户在同 leaf 内碰过很多商品时会产生 O(k^2) pair。

后续性能优化可以做：

- 按 leaf / user bucket 分块；
- 先筛 full-period endpoint users >= 100；
- 对超大 leaf 单独分区；
- 用 DuckDB 临时目录 / external sort；
- 如果必要，复用此前 `copreview_projection` 实验已经产出的 pair 表。

不能为了性能随意限制“每个用户最多贡献 N 个商品”，因为那会改变图定义。

## 4. Pre-t0 component 的使用方式

当前已经支持：

```text
Case 当前 shelf
+ pre-t0 strong edges
-> Case 内连通分量
```

并生成：

```text
direct_strong_edge
same_component
isolated
same_market_other
```

正式 benchmark 需要决定 graph 关系的用途：

### 方案 A：只做特征

完整 shelf 全保留，只把 graph relation 提供给模拟器 / quality audit。

### 方案 B：shelf 太大时作为截断优先级

```text
direct strong edge
> same component
> same market other
```

层内再按 t0 前近期活动量排序。

当前更推荐 B 作为“大 Market 需要截断时”的机制，但在真实 shelf size 分布出来前不写死 Top-K。

## 5. 跨 leaf 的同 Market 商品

当前 graph pair 只在 same leaf 内生成，这是对已有实验的严格延续。

因此同一 Final Market 如果包含多个 leaf：

- 语义上仍属于同 Market；
- 跨 leaf 商品不会形成 graph strong edge；
- 在 Case 中归入 `same_market_other`。

需要后续审计这种情况是否很多。如果很多，先分析 Market / leaf 的关系，再决定是否需要额外的跨 leaf 行为相似度；不要直接取消 same-leaf 限制。

## 6. 完整时期图与 Case 图的口径隔离

必须一直保持：

```text
full-period graph -> audit only
pre-t0 graph -> Case features / shelf logic
```

禁止把 `full_graph_components.parquet` 直接 join 到历史 Case 作为竞品筛选依据。

## 7. 用户行为的含义

Amazon Reviews 里的用户事件是评分 / 评论观测，不等同于完整购买流水。

所以：

```text
shared_users
```

准确含义是：

> 同一批用户在观测数据中都对两个商品留下过目标交互。

文档和论文中应写“共评 / 共交互行为图”，不要把它表述成完整真实购买共现图。

## 8. 与此前 Electronics 实验结果的正式复现

当前 README 记录了此前实验口径和关键数字：

```text
62.71M raw co-review pairs
-> 27,457 same-leaf strong edges
```

后续如果原始输出目录仍在机器上，建议把：

```text
outputs/copreview_projection/Electronics/amazon_graph_markets/
```

里的旧结果和新 `full_graph_*` 产物做一次字段级对照，并把差异原因记录成 audit 文件。
