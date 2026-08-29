# 大类人口扫描（population_scan）

本目录只做一件事：对着 **某一个 Amazon 大类的数据集文件** 做扫描，盘点「这个大类里出现过哪些用户、每人买过（交互过）多少次」。

先写文档，代码后补。扫描结果是大类级人口表，不是单个 SEMS case 包。

## 1. 要回答的问题

给定一个大类（例如 `Home_and_Kitchen`），从该大类已落盘的数据文件里得到：

1. 哪些用户在这个大类里留下过购买 / 评分记录
2. 每个用户的次数（以及建议一并记下的附属计数）

这里的「购买」在 Amazon Reviews 2023 里 **不是订单流水**。公开数据是评论 / 评分事件。本扫描默认用「一条 user–product 评分（或评论）记录」作为一次交互；若源文件带 `verified_purchase`，再单独计「标记为已购买」的次数。文档和以后的表头都要写清口径，避免被当成真实 GMV 订单。

## 2. 扫描对象

对象是 **一个 Amazon 大类的源文件**，不是全站混合、也不是已经打好的 case 包。

优先读 v5 产线已经在用的同类输入（路径以 `AmazonReviewrepo` 数据根为准，本仓不复制数据）：

```text
benchmark/0core/rating_only/<Category>.csv          # 轻量：user、item、rating、timestamp
raw/meta_categories/meta_<Category>.jsonl           # 商品元数据，本扫描不是主输入
raw/review_categories/<Category>.jsonl              # 全文评论；需要 verified_purchase / 文本时才扫
```

第一版实现建议只扫 `rating_only`：文件小，足够得到「用户集合 + 次数」。`verified_purchase` 只有全文 JSONL 才稳定有，作为第二档可选扫描。

一次运行只处理一个大类。大类名与 Amazon Reviews 2023 的 category 文件名一致。

## 3. 建议产出（代码落地时再写表）

最小表：每个大类一张用户汇总。

| 字段 | 含义 |
|------|------|
| `source_partition` | 大类名，如 `Home_and_Kitchen` |
| `user_id` | 数据集里的用户键 |
| `n_events` | 该用户在本大类的评分数 / 交互次数 |
| `n_products` | 该用户在本大类碰过多少不同商品 |
| `n_verified_purchases` | `verified_purchase=true` 的条数；源文件没有则为空 |
| `first_event_date` | 本大类内最早一条记录的日期 |
| `last_event_date` | 本大类内最晚一条记录的日期 |

另外需要一份大类级摘要，方便后面接人口先验或抽样子：

- 用户总数
- 交互总次数
- 人均次数、分位数（p50 / p90 / p99）
- 只出现 1 次的用户占比
- 扫描了哪些源文件、行数、去重规则

文件名以后再定，原则是：**一个大类一份用户表 + 一份 summary**，不要和 case 工作区混放。

## 4. 计数口径（实现时必须写进 summary）

需要事先钉死，否则同一大类会扫出两套数：

- **事件键**：`rating_only` 里同一用户对同一商品多条评分，默认 **每条都计 1 次**。若源数据已按 user–item 去重，在 summary 里标明。
- **用户键**：用数据里的 `user_id`（或 rating 文件对应列），不做跨类合并。
- **商品键**：与 v5 一致，优先 `parent_asin`；源文件只有 `asin` 时在 summary 注明。
- **时间**：只用于 `first_event_date` / `last_event_date`，本扫描不做 t0、也不按 case 窗口裁剪。
- **verified**：有则另计一列，不替代 `n_events`。

本扫描 **不做**：

- 市场划分、cross-path、focal / 竞品选择
- 匿名化、打 case 包
- 拟合 `population_prior.json` 里的收入/家庭联合分布（那是另一份 reference；本扫描只提供「这个大类里实际出现过的用户有多厚」）

## 5. 在整体里的位置

```text
Amazon 大类源文件
        ↓
 population_scan     ← 本目录（大类人口表）
        ↓
 后续可用处（都不在本目录实现）
   - 看这个大类有没有足够的活跃用户
   - 给 L2 / 人群行为真值抽样本框
   - 对照 SEMS 的 population_prior 是否和真实用户厚度匹配
```

它和 `AmazonReviewrepo` v5 并行：v5 用同一批源文件造 case；这里用同一批源文件数人。两者都读大类文件，互不替代。

## 6. 实现备忘（先不写代码）

- 输入只认单个 `--category`，与 v5 的大类名对齐。
- 默认读 `rating_only`；需要购买标记再加全文档。
- 输出落在本仓运行时的数据目录，不把几十 GB 的原始 JSONL 提交进 git。
- 用户表会很大，用 Parquet；summary 用 JSON 即可。
