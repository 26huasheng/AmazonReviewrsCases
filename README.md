# AmazonReviewrsCases

Amazon Reviews 2023 上的 SEMS benchmark 数据构造仓库。

本仓负责从 Amazon Reviews 基础数据出发，完成：

1. 用户基础人口扫描；
2. Market Discovery 与 market 整理；
3. Market-level population 构造；
4. Market 内新品进入 Case 的发现与筛选；
5. Case 用户选择；
6. 两层 Ground Truth 构造；
7. benchmark learning / validation / evaluation split。

最终数据以 **Market → Cases** 为核心层级组织。

- **Market**：一个相对稳定的竞争市场定义，维护长期商品 universe 和共享 population。
- **Case**：某个新品在该 Market 中于特定时间点进入市场的一次真实历史事件，拥有自己的 focal、`t0`、shelf、用户子集和 Ground Truth。

详细最终产物格式见 [`SCHEMA.md`](SCHEMA.md)。

## 1. 总体流程

```text
Amazon Reviews 2023
        │
        ├────────────────┐
        │                │
        ▼                ▼
population_scan     market_discovery
大类用户基础扫描      path-local market 发现
        │                │
        │                ▼
        │       exact normalized-name merge
        │          （cross-path，不调用 LLM）
        │                │
        └────────┬───────┘
                 ▼
             Final Market
                 │
                 ├── Product Universe
                 ├── Shared Population
                 │
                 ▼
            Case Discovery
                 │
                 ├── focal product
                 ├── t0
                 ├── case shelf
                 └── evaluation window
                 │
                 ▼
          Case User Selection
                 │
                 ├── GT1
                 └── GT2
                 │
                 ▼
           Case Quality Gate
                 │
                 ▼
            Accepted Cases
                 │
                 ▼
           Benchmark Split
      learning / validation / evaluation
```

## 2. Market

Market 是 benchmark 的一级组织单位。

一个 Market 维护：

- `market_id` / `market_name`；
- 来源 Amazon 大类与 category path；
- 长期商品 universe；
- 共享 population 与用户历史；
- Market 内发现出的 accepted cases。

同一个 Market 可以包含多个 Case：

```text
market_smart_watch/
├── case_2021_x/
├── case_2022_y/
└── case_2023_z/
```

多个 Case 可以拥有不同的 focal、`t0`、货架和用户子集，同时复用 Market 层的商品与人口基础资产。

### 2.1 Market Discovery

`market_discovery/` 已经从 `AmazonReviewrepo@v5` 迁入完整 path-local discovery 主流程，并在末尾直接生成 `final_market.parquet/csv`。

Cross-path 合并采用固定窄规则：

```text
同一 source_partition
+ market_label 规范化后完全相等
→ 合并
```

例如：

```text
Phone_Case
phone-case
phone case
```

统一为：

```text
phone_case
```

Cross-path 阶段不调用 LLM，不做 synonym / embedding / semantic clustering。详细规则见 [`market_discovery/README.md`](market_discovery/README.md)。

## 3. Case

Case 表示一次真实的新品进入市场事件。

每个 Case 至少由以下内容确定：

- `case_id`；
- `market_id`；
- `focal_product_id`；
- `t0`；
- evaluation window；
- `t0` 时刻的实际商品 shelf；
- 从 Market population 中选择出的用户；
- GT1；
- GT2。

当前使用 focal 商品的首评时间近似 `t0`。Case 按自己的 `t0` 截断商品历史和用户历史；future 数据只用于评测窗口完整性、质量统计和 Ground Truth。

### 3.1 商品侧 Case Build

`case_build/` 已经接入 v5 中可复用的商品时间、区间累计和 ASOF 逻辑，当前完成：

```text
Final Market
    ↓
Market 商品时间轴
    ↓
每个商品形成候选新品进入事件
    ↓
case_candidates.parquet
    ↓
指定一批 Case
    ↓
t0 shelf + pre-t0 商品统计
```

当前保留：

- `t0 = first_rating_date`；
- evaluation window 完整性检查；
- t0 时活跃 competitor 数统计；
- 同 Market 商品的 `first_rating_date < t0`、`last_rating_date >= t0` 时间资格；
- 商品累计评论量 / 累计评分和；
- ASOF 计算 `pre_t0_review_count`、`pre_t0_rating_mean`；
- 最近窗口活动量统计。

当前没有继续使用 v5 的：

```text
每个时间段只留 1 个 focal
post90 >= 50 硬门槛
competitor >= 5 硬门槛
Top-150 截断
8 CORE + 8 RESERVE
```

Shelf 物化要求显式传入 Case 表，避免超大 Market 对全部候选 Case 直接做 `case × product` 展开。详细接口和剩余事项见 [`case_build/README.md`](case_build/README.md) 与 [`case_build/TODO.md`](case_build/TODO.md)。

## 4. Population

### 4.1 `population_scan/`

`population_scan/` 负责大类级、case-agnostic 的基础人口扫描，主要回答：

- 一个 Amazon 大类中出现过哪些用户；
- 每个用户历史交互有多丰富；
- 用户总体的交互次数和商品数分布；
- 用户最早和最晚活动时间。

该阶段不做最终 case-level 用户筛选、`t0` 截断、future GT 查询和 population sampling。

### 4.2 Market Population

Market 确认以后，为 Market 建立共享 population。Market 下多个 Case 共用这份 population 与用户历史，Case 只保存自己最终选择的 `user_id`。

### 4.3 Case User Selection

Case 的 focal、`t0` 和 shelf 确认以后，按照 `t0` 以前的用户历史执行 eligibility filtering 和 population sampling。

主要筛选维度包括：

- `t0` 前历史厚度；
- `t0` 前最近活动时间；
- 当前 category / market 相关性。

正式阈值先通过 population statistics / threshold scan 确定，再在 benchmark 中冻结。

## 5. Ground Truth

### GT1 — Conditional Individual Choice

已知用户在该 Case 中发生了市场内商品选择，预测其实际选择的商品。

```text
user_id -> target_product_id
```

GT1 中每个用户都有确定商品答案，不包含 `none`。

核心问题：**已知这个人会买，他会买哪个商品？**

### GT2 — Population Choice and Market Ranking

从 Case 预先确定的完整用户集合开始，每个用户的真实结果为：

```text
user_id -> product_id / none
```

其中 `none` 表示 evaluation window 内没有观测到该用户对当前 shelf 商品的目标交互。

GT2 聚合后得到：

- 每个商品的 demand count；
- demand share；
- 商品 ranking。

核心问题：**这一批人中谁会进入市场、会选择哪个商品，最终市场需求如何分配？**

## 6. Case Quality Gate

候选 Case 正式进入 benchmark 前需要检查：

- focal 是否满足新品定义；
- evaluation window 是否完整；
- `t0` 时 shelf 是否有效；
- 可用 population 是否充足；
- GT1 样本是否充足；
- GT2 是否具有足够市场交互；
- focal 与 competitor 的历史数据是否满足模拟输入要求；
- 需要时结合外部 BSR / sales proxy 做额外筛选。

## 7. Self-Evolving Benchmark Split

Case 构造完成以后再划分实验用途，split 与 Case 数据本身分离。

支持：

- learning / evolution cases；
- validation cases；
- held-out evaluation cases；
- seen-market temporal evaluation；
- held-out market evaluation。

split 文件只记录 Market / Case ID，不复制 Case 数据。

## 8. 当前与计划目录

```text
AmazonReviewrsCases/
├── README.md
├── SCHEMA.md
├── requirements.txt
├── paths.py
├── utils.py
│
├── population_scan/              # 已有定义：大类人口基础扫描
├── market_discovery/             # 已有代码：local discovery + exact cross-path merge
├── case_build/                   # 已有代码：商品时间轴 / Case discovery / t0 shelf
├── tests/                        # discovery + case_build 回归测试
│
├── market_build/                 # 计划：共享 population 与 Market 资产组织
└── benchmark_split/              # 计划：learning / validation / evaluation split
```

模拟器本体不属于本仓。
