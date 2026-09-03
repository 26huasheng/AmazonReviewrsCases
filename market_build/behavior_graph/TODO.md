# TODO：Behavior Graph

正式 Case 的第一版用途已经冻结：**不分裂 Final Market，只在竞品池超过 16 时做 focal-centered pre-t0 共评筛选。**

已经固定：

```text
max_competitors = 16
min_endpoint_users = 100
min_shared_users = 5
pair scope = same Final Market + same leaf
Case visibility = event_date < t0
```

选择顺序固定为：

```text
强共评优先
→ shared_users_pre_t0 降序
→ 不足 16 时按 pre_t0_recent_review_count 补
→ pre_t0_review_count / product_id tie-break
```

下面只保留尚未影响第一版语义的事项。

## 1. leaf category 的正式来源

当前从 `market_products.category_path` 最后一级派生 `leaf_category`。

后续确认全量数据里：

- category_path 是否总是完整；
- 一个 product 是否可能出现多个 path；
- 是否直接复用此前二部图实验里的 canonical `product_nodes.leaf_category`。

如果有更稳定的 leaf canonical 表，可以替换输入来源，不改变 16 个竞品的选择规则。

## 2. Pair 构造性能

当前定义：

```text
user-product first membership
→ 同 Market + 同 leaf + 同 user 内自连接
→ product_a < product_b
```

高活跃用户在同一 Market/leaf 内碰过很多商品时仍可能产生 O(k^2) pair。

可做的纯工程优化：

- Market / leaf 分块；
- user bucket 分块；
- 完整时期 endpoint users >=100 安全预剪枝；
- DuckDB external sort / 临时目录；
- checkpoint / resume。

不能用“每个用户最多贡献 N 个商品”这种会改变图定义的近似。

## 3. 预实验复现

此前 Electronics 预实验记录：

```text
62.71M raw co-review pairs
→ 27,457 same-leaf strong edges
```

如果旧输出仍在机器：

```text
outputs/copreview_projection/Electronics/amazon_graph_markets/
```

可以继续与新 full-period audit 产物对照。

注意新正式生产 pair 已经限制在 Final Market 内，因此 full-period audit 数字不要求逐字复现旧的全 leaf 大类扫描结果；旧结果主要作为阈值和方法预实验依据。

## 4. Amazon Reviews 行为含义

`shared_users` 的准确含义是：同一批用户在 Amazon Reviews 观测数据中都对两个商品留下过评分 / 评论事件。

它不能被表述成完整购买流水中的真实共同购买人数。

---

第一版不再讨论：

```text
Market 是否按 component 分裂
behavior group 是否成为正式市场层级
小 Market 分裂后怎么补竞品
component-based Top-K
```

这些都已经从正式 Case 构建逻辑中删除。
