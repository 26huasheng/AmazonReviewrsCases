# behavior_graph

这一目录负责把 Amazon Reviews 中的 **用户—商品共评关系** 用到 Final Market 内的竞品筛选。

正式 benchmark 的定位现在已经收紧：

```text
Final Market 决定竞争范围
+t0 决定当时哪些商品在场
+behavior_graph 只在竞品过多时帮助 focal 选更近的竞品
```

**不再根据二部图分裂 Final Market，也不在正式 Case 里做连通分量分组。**

## 1. 已有预实验

此前 Electronics 上做过完整时期共评投影实验：

```text
同一个 Amazon leaf category
两端商品各自 n_users >= 100
shared_users >= 5
```

约 62.71M 个原始共评商品对最终筛到 27,457 条同 leaf 强边。这个实验说明已有语义 Market 与用户共评行为大体相容，同时 Market 内存在明显的近邻关系。

完整时期连通分量结果现在只保留作 **audit / 研究复现**，不参与正式历史 Case 的竞品选择。

## 2. 正式生产逻辑

### 2.1 Pair 只在 Final Market 内生成

先把用户对一个商品的重复事件压成：

```text
source_partition
market_id
user_id
product_id
leaf_category
first_event_date
```

然后只在：

```text
同一个 Final Market
+同一个 leaf_category
+同一个 user_id
```

内部生成商品 pair。

因此正式构建不再先对整个 Amazon 大类制造全局共评 pair。

### 2.2 共评关系严格使用 pre-t0

用户第一次碰到 A、B 的日期分别为：

```text
first_A_date
first_B_date
```

这个用户对 A-B 共同用户数的贡献从：

```text
pair_event_date = max(first_A_date, first_B_date)
```

开始生效。

累计后得到：

```text
market_id
product_a
product_b
event_date
shared_users_cumulative
```

某个历史 Case 只查询：

```text
event_date < t0
```

所以不会使用 t0 之后的用户行为。

## 3. 固定 Case 竞品规模：K = 16

当前 benchmark 第一版已经冻结：

```text
max_competitors = 16
```

也就是：

```text
一个 Case 最多 1 个 focal + 16 个 competitor
```

选择机制固定为：

```text
t0 时有效 competitor 数 <= 16
→ 全部保留

 t0 时有效 competitor 数 > 16
→ 启动 focal-centered 共评筛选
```

## 4. 超过 16 个时怎么选

只计算 focal 与每个 competitor 的关系，不需要计算整个 shelf 的连通分量。

强共评 competitor 定义沿用预实验：

```text
same leaf_category
focal_users_pre_t0 >= 100
competitor_users_pre_t0 >= 100
shared_users_pre_t0 >= 5
```

然后：

```text
1. 强共评 competitor 优先
2. 如果强共评 competitor > 16
   → 按 shared_users_pre_t0 从高到低取前 16
3. 如果强共评 competitor < 16
   → 强共评全部保留
   → 剩余名额按 pre_t0_recent_review_count 从高到低补
   → 再以 pre_t0_review_count、product_id 做确定性 tie-break
```

例如：

```text
原始 competitor = 43
强共评 competitor = 9

→ 9 个强共评全部留下
→ 再按近期活跃度补 7 个
→ 最终 16 个 competitor
```

## 5. 这三个信号各自负责什么

```text
Market
→ 谁属于同一个竞争范围

t0 时间资格
→ 当时谁已经存在且仍有观测活动

focal-centered 共评
→ 竞品太多时谁和 focal 的真实用户更重合

pre_t0_recent_review_count
→ 共评关系不足以填满 16 个时补谁
```

小 Market / 小 shelf 完全不会被二部图切碎：只要竞品数不超过 16，就全部保留。

## 6. 主要输出

长期累计索引：

```text
product_user_cumulative.parquet
pair_cumulative.parquet
```

Case 选择中间表：

```text
_work/case_focal_coreview_features.parquet
```

一行一个 Case × competitor，包含：

```text
case_candidate_id
market_id
focal_product_id
product_id
t0
same_leaf
focal_users_pre_t0
competitor_users_pre_t0
shared_users_pre_t0
strong_coreview_pre_t0
```

正式截断后的 shelf：

```text
case_shelf_selected.parquet
```

额外记录：

```text
competitor_pool_size
competitor_cap                 # 16
selection_triggered
selection_rank
selection_reason               # focal / within_cap / strong_coreview / activity_fill
```

## 7. Full-period audit

`full_graph_edges.parquet`、`full_graph_components.parquet` 等仍可以保留，用于复现 / 审计此前二部图实验。

它们的作用只限于研究分析，不会决定历史 Case 的 shelf。

## 8. 关键原则

1. Final Market 不因共评图重新分裂。
2. 正式 pair 只在同一个 Final Market 内生成。
3. 任何影响 Case 的共评统计都必须严格 `< t0`。
4. competitor 数 `<=16` 时全部保留。
5. competitor 数 `>16` 时才启动共评筛选。
6. 强共评阈值第一版固定为 `100 / 5`。
7. 用户对同一商品多次评论只贡献一个 user-product membership。
