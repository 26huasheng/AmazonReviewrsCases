# AmazonReviewrsCases

Amazon Reviews 2023 上的 SEMS benchmark 数据构造仓库。

本仓现在已经按 **Market → Cases** 的新设计拆成完整数据链，负责从 Amazon Reviews 基础数据一路构造到最终 benchmark 目录；模拟器本体仍在其它仓库。

最终 schema 见 [`SCHEMA.md`](SCHEMA.md)，全局尚未冻结的研究口径见 [`TODO.md`](TODO.md)。

---

# 1. 核心结构

```text
MARKET
├── Market definition
├── 长期商品 universe
├── shared population
├── shared user history
│
└── CASES
    ├── focal product
    ├── t0
    ├── evaluation window
    ├── t0 shelf
    ├── selected user ids
    └── Ground Truth
        ├── GT1: 已知发生市场内选择 -> product
        └── GT2: 全部 Case 用户 -> product / none
                                ↓
                         demand / share / rank
```

Market 是相对稳定的竞争空间；Case 是一个具体新品在某个时间点进入该 Market 的真实历史事件。

一个 Market 可以有很多 Case，不再把 `focal + 几个 competitor` 当成 Market 本身。

---

# 2. 完整数据流程

```text
Amazon Reviews / v5 upstream data
        │
        ├──────────────────────────────┐
        │                              │
        ▼                              ▼
population_scan                  market_discovery
大类用户基础扫描                   path-local Market 发现
        │                              │
        │                              ▼
        │                    规范化后同名 cross-path merge
        │                         （不调用 LLM）
        │                              │
        └──────────────┬───────────────┘
                       ▼
                  Final Market
                       │
                       ▼
                  market_build
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   Market products   shared users   user history indexes
                       │
                       ▼
                  case_build
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 Case Discovery      t0 Shelf      Case Population
        │                             │
        └──────────────┬──────────────┘
                       ▼
                  Ground Truth
                  GT1 + GT2
                       │
                       ▼
                  Quality Gate
                       │
                       ▼
                  Accepted Cases
                       │
                       ▼
                benchmark_split
                       │
                       ▼
                benchmark_export
                       │
                       ▼
                  benchmark_data/
```

---

# 3. 当前模块与状态

| 模块 | 职责 | 当前状态 |
|---|---|---|
| `population_scan/` | 大类用户基础盘点 | **已有代码** |
| `market_discovery/` | path-local Market Discovery + 安全 cross-path 合并 | **已有代码** |
| `market_build/` | Market 商品资产、共享 population、统一用户事件与历史累计索引 | **已有代码** |
| `case_build/` | Case discovery、shelf、用户选择、GT、Quality Gate | **已有代码** |
| `benchmark_split/` | learning / validation / evaluation 划分 | **已有代码** |
| `benchmark_export/` | 跨表校验 + 最终 Market→Cases 目录物化 | **已有代码** |

“已有代码”表示数据接口和主要计算逻辑已经设计并落仓；具体研究阈值仍以各目录 `TODO.md` 为准。

---

# 4. `population_scan/`：大类人口扫描

输入一个 Amazon 大类用户事件源，输出：

```text
users.parquet
summary.json
```

一行一个用户：

```text
source_partition
user_id
n_events
n_products
n_verified_purchases
first_event_date
last_event_date
```

这一层只看完整大类历史做基础盘点，不做 Market / Case 筛选，不看 future GT。

支持普通 CSV / Parquet，也兼容 `AmazonReviewrepo@v5` 的 `rating_event_store/`。

详细见 [`population_scan/README.md`](population_scan/README.md)。

---

# 5. `market_discovery/`：最终 Market 定义

path-local Discovery 主流程迁自 `AmazonReviewrepo@v5`，继续使用已有 LLM 定义 + 确定性 title assignment 机制。

Cross-path 阶段已经改成固定窄规则：

```text
同一 source_partition
+ market_label 规范化后完全相等
→ 直接合并
```

例如：

```text
Phone_Case
phone-case
phone case
```

都会变成：

```text
phone_case
```

Cross-path 不再调用大模型，不做开放同义词发现、embedding merge、complete-link clustering。

最终输出：

```text
final_market.parquet
final_market.csv
```

详细见 [`market_discovery/README.md`](market_discovery/README.md)。

---

# 6. `market_build/`：Market 共享资产

Final Market 确认后，这一层生成：

```text
market_products.parquet
market_population.parquet
canonical_user_events.parquet
user_event_store/
user_history_cumulative.parquet
user_category_history_cumulative.parquet
user_market_history_cumulative.parquet
```

## Market Population

支持：

```text
population_source = category
population_source = global
```

并支持按固定 seed 做确定性用户抽样。

这里选的是 **Market shared population**，不根据任何 Case 的未来购买 / 评论结果选用户。

## 用户历史索引

为了后面大量不同 `t0` 查询，用户历史提前累计成：

```text
全局历史
大类历史
Market 历史
```

Case 不复制完整用户轨迹。

详细见 [`market_build/README.md`](market_build/README.md)。

---

# 7. `case_build/`：完整 Case 构造

## 7.1 Case Discovery

商品侧主要复用 v5 的时间与累计计算：

```text
Final Market
    ↓
Market 商品时间轴
    ↓
每个商品作为 candidate focal
    ↓
t0 = first_rating_date
    ↓
evaluation window
```

每个结构完整的新品进入事件都先保留成 candidate case。

旧 v5 的：

```text
一个时间段只取一个 focal
post90>=50
competitor>=5
```

不再在这里提前筛。

主要输出：

```text
case_candidates.parquet
case_candidates_evaluable.parquet
```

## 7.2 t0 Shelf

一个商品成为 competitor 需要：

```text
同 Market
product_id != focal
first_rating_date < t0
last_rating_date >= t0
```

通过商品累计表 + ASOF 计算：

```text
pre_t0_review_count
pre_t0_rating_mean
pre_t0_recent_review_count
```

当前不写死 Top-150、8 CORE + 8 RESERVE 等旧规则。

## 7.3 Case Population

目录：[`case_build/population/`](case_build/population/README.md)

```text
Market shared population
+ Case t0
        ↓
pre-t0 user features
        ↓
threshold scan
        ↓
eligibility
        ↓
fixed case users
```

主要特征：

```text
history_product_count
days_since_last_event
category_history_product_count
market_history_product_count
relation_stratum
```

用户集合在 future GT 查询之前固定。

## 7.4 Ground Truth

目录：[`case_build/ground_truth/`](case_build/ground_truth/README.md)

GT2：

```text
全部 Case 用户
user -> product / none
```

GT1：

```text
GT2 positives
user -> target_product
```

GT2 聚合：

```text
product -> demand_count / demand_share / rank
```

还支持从完整 shelf future 评论量生成辅助：

```text
review_activity_truth.parquet
```

## 7.5 Quality Gate

目录：[`case_build/quality/`](case_build/quality/README.md)

汇总：

```text
商品侧质量
用户数
GT1 正例数
GT2 market-positive / none
focal demand
future review activity
外部 Keepa / BSR signal（可选）
```

输出：

```text
quality_metrics.parquet
quality_decisions.parquet
accepted_cases.parquet
rejected_cases.parquet
```

结构完整性固定检查；具体研究阈值全部配置化。

---

# 8. `benchmark_split/`

只读取：

```text
market_id
case_candidate_id
t0
```

不使用 GT 数值决定 split。

支持：

```text
market_holdout
    整个 Market held out

temporal_within_market
    同 Market 早期 learning、后期 evaluation

hybrid
    unseen-market evaluation
    + seen-market temporal evaluation
```

输出只保存 Market / Case 引用。

详细见 [`benchmark_split/README.md`](benchmark_split/README.md)。

---

# 9. `benchmark_export/`

最终把所有构建长表做跨表一致性校验，再物化成 `SCHEMA.md` 定义的目录。

导出前检查：

- Case ID 唯一；
- focal 在 shelf 恰好一行；
- GT2 覆盖全部 Case users；
- GT2 target 都在 shelf；
- GT1 == GT2 positives；
- `market_truth` 与 GT2 聚合一致；
- split 一一覆盖 accepted cases。

最终：

```text
benchmark_data/
├── markets/
│   └── <market_id>/
│       ├── market_manifest.json
│       ├── products.parquet
│       ├── population/
│       │   ├── users.parquet
│       │   └── interactions.parquet
│       └── cases/
│           └── <case_id>/
│               ├── case_manifest.json
│               ├── shelf.parquet
│               ├── users.parquet
│               └── ground_truth/
│                   ├── choice_truth.parquet
│                   ├── population_truth.parquet
│                   └── market_truth.parquet
└── splits/
    ├── learning.json
    ├── validation.json
    └── evaluation.json
```

详细见 [`benchmark_export/README.md`](benchmark_export/README.md)。

---

# 10. 从 v5 继续复用的部分

当前新仓库没有重复重写已有成熟逻辑，主要继续使用 / 改造了：

```text
market_discovery/*
product_time_summary
rating daily aggregation
Market-product timeline
active competitor interval sweep
focal / Market pre-t0 cumulative features
competitor time qualification
product cumulative review counts
ASOF pre-t0 features
truth future-event join
market review activity ranking
```

主要删掉的是和旧 benchmark 强绑定的 selection policy：

```text
每时间段 top-1 focal
固定 post90 hard gate
固定 competitor hard gate
Top-150
8 CORE + 8 RESERVE
旧 packaging 层级
```

---

# 11. 当前目录

```text
AmazonReviewrsCases/
├── README.md
├── SCHEMA.md
├── TODO.md
├── requirements.txt
├── paths.py
├── utils.py
│
├── population_scan/
│   ├── README.md
│   ├── TODO.md
│   └── ...
│
├── market_discovery/
│   ├── README.md
│   ├── TODO_CROSS_PATH.md
│   └── ...
│
├── market_build/
│   ├── README.md
│   ├── TODO.md
│   └── ...
│
├── case_build/
│   ├── README.md
│   ├── TODO.md
│   ├── population/
│   ├── ground_truth/
│   ├── quality/
│   └── ...
│
├── benchmark_split/
│   ├── README.md
│   ├── TODO.md
│   └── ...
│
└── benchmark_export/
    ├── README.md
    ├── TODO.md
    └── ...
```

研究口径还没冻结的地方统一通过 TODO + 配置接口保留；已经确定的层级、时间语义、GT 两层结构和数据职责不再混回旧 pipeline。
