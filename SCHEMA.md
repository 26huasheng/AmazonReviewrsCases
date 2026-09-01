# SEMS Benchmark Data Schema

本文件定义 `AmazonReviewrsCases` 最终 benchmark 产物的核心层级与字段。当前版本以 **Market → Cases** 为主结构，并把共享资产放在 Market 层，把具体新品进入事件放在 Case 层。

## 1. 总体目录

```text
benchmark_data/
├── markets/
│   ├── <market_id>/
│   │   ├── market_manifest.json
│   │   ├── products.parquet
│   │   ├── population/
│   │   │   ├── users.parquet
│   │   │   └── interactions.parquet
│   │   └── cases/
│   │       ├── <case_id>/
│   │       │   ├── case_manifest.json
│   │       │   ├── shelf.parquet
│   │       │   ├── users.parquet
│   │       │   └── ground_truth/
│   │       │       ├── choice_truth.parquet
│   │       │       ├── population_truth.parquet
│   │       │       └── market_truth.parquet
│   │       └── ...
│   └── ...
└── splits/
    ├── learning.json
    ├── validation.json
    └── evaluation.json
```

## 2. Market 层

### 2.1 `market_manifest.json`

描述一个最终确认的 Market。

```json
{
  "market_id": "market_001",
  "market_name": "smart_watch",
  "source_partition": "Electronics",
  "source_market_ids": ["local_xxx", "local_yyy"],
  "source_category_paths": [
    ["Electronics", "Wearable Technology", "Smartwatches"]
  ],
  "n_products": 37,
  "n_population_users": 58214,
  "case_ids": ["case_001", "case_002", "case_003"]
}
```

字段：

| 字段 | 含义 |
|---|---|
| `market_id` | 最终 Market ID |
| `market_name` | Market 名称 |
| `source_partition` | Amazon Reviews 大类 |
| `source_market_ids` | Market Discovery / cross-path 前的来源 market IDs |
| `source_category_paths` | Market 来源 category paths |
| `n_products` | Market 长期商品 universe 大小 |
| `n_population_users` | Market 共享 population 大小 |
| `case_ids` | 当前 Market 下通过质量检查的 Case IDs |

Market manifest 不保存某个具体时间点的 focal、competitor 或 shelf。

### 2.2 `products.parquet`

Market 的长期商品 universe，一行一个商品。

| 字段 | 含义 |
|---|---|
| `product_id` | 商品键，优先使用 `parent_asin` / benchmark product id |
| `title` | 商品标题 |
| `source_partition` | Amazon 大类 |
| `category_path` | 商品 category path |
| `first_review_date` | 商品首评时间 |
| `first_available_date` | `Date First Available`，可获得时保存 |
| `store` | Amazon metadata 中的 store / 展示品牌字段，可获得时保存 |
| `metadata_available` | 是否存在可用 metadata |

`focal / competitor` 属于 Case 角色，不写在 Market 商品表中。

## 3. Market Population

### 3.1 `population/users.parquet`

Market 共享候选人口，一行一个用户。

第一版最小字段：

| 字段 | 含义 |
|---|---|
| `user_id` | Amazon Reviews 用户键 |

用户基础统计或画像字段以后可以扩展，但不在这里写与某个 Case `t0` 绑定的重复派生字段。

### 3.2 `population/interactions.parquet`

Market population 对应的可用用户交互轨迹。

| 字段 | 含义 |
|---|---|
| `user_id` | 用户键 |
| `product_id` | 商品键 |
| `timestamp` | 交互时间 |
| `rating` | 星级 |
| `source_partition` | 来源大类 |
| `verified_purchase` | 源数据有该字段时保存 |

Case 使用自己的 `t0` 对这份共享历史做时间截断，因此同一用户历史不在多个 Case 中重复保存。

## 4. Case 层

### 4.1 `case_manifest.json`

定义一次真实新品进入事件。

```json
{
  "case_id": "case_001",
  "market_id": "market_001",
  "focal_product_id": "B0XXXXX",
  "t0": "2022-09-15",
  "evaluation": {
    "start": "2022-09-15",
    "end": "2022-12-14",
    "days": 90
  },
  "n_shelf_products": 8,
  "n_selected_users": 2000,
  "quality_status": "accepted"
}
```

字段：

| 字段 | 含义 |
|---|---|
| `case_id` | Case ID |
| `market_id` | 所属 Market |
| `focal_product_id` | 本次新品 focal |
| `t0` | 新品进入时间锚点，当前由首评时间近似 |
| `evaluation.start` | GT evaluation window 起点 |
| `evaluation.end` | GT evaluation window 终点 |
| `evaluation.days` | evaluation window 长度 |
| `n_shelf_products` | `t0` 时实际 shelf 商品数 |
| `n_selected_users` | 本 Case 最终选择的用户数 |
| `quality_status` | 候选 Case 质量检查状态 |

### 4.2 `shelf.parquet`

本 Case 在 `t0` 时进入模拟的真实商品货架。

| 字段 | 含义 |
|---|---|
| `product_id` | 商品键 |
| `role` | `focal` / `competitor` |
| `pre_t0_review_count` | `t0` 前历史评论/评分交互量 |
| `pre_t0_rating_mean` | `t0` 前平均评分 |
| `price_at_t0` | `t0` 附近价格，可获得时保存 |

Market 的 `products.parquet` 保存长期 universe；`shelf.parquet` 保存这个 Case 在 `t0` 时实际进入模拟的商品集合。

### 4.3 `users.parquet`

本 Case 从 Market population 中最终选中的用户。

第一版只需要：

| 字段 | 含义 |
|---|---|
| `user_id` | 用户键 |

Case 不复制用户完整历史；运行时按 `case.t0` 截断 Market 层共享 history。

## 5. Ground Truth

### 5.1 GT1 — `ground_truth/choice_truth.parquet`

GT1 是 **Conditional Individual Choice**：已知用户在该 Case 中发生市场内商品选择，真实目标商品是什么。

| 字段 | 含义 |
|---|---|
| `user_id` | 用户键 |
| `target_product_id` | 真实选择商品 |
| `event_timestamp` | 对应目标交互时间 |

GT1 中每一行都有确定的 `target_product_id`，不包含 `none`。

### 5.2 GT2 — `ground_truth/population_truth.parquet`

GT2 覆盖本 Case `users.parquet` 中全部用户。

推荐最小字段：

| 字段 | 含义 |
|---|---|
| `user_id` | 用户键 |
| `outcome_product_id` | evaluation window 内真实市场内目标商品；无观测目标交互时为空 |
| `event_timestamp` | 有市场内目标交互时的对应时间；否则为空 |

语义：

```text
outcome_product_id = product_id  -> 该用户在 evaluation window 内命中该 shelf 商品
outcome_product_id = NULL        -> none
```

这里的 `none` 表示在 Amazon Reviews 观测数据中没有看到该用户对当前 shelf 商品产生目标交互。

### 5.3 `ground_truth/market_truth.parquet`

由 GT2 的 population outcomes 聚合得到商品级市场结果。

| 字段 | 含义 |
|---|---|
| `product_id` | shelf 商品 |
| `demand_count` | 命中该商品的 GT2 用户数 |
| `demand_share` | 在市场内有效选择中的份额 |
| `rank` | 按 `demand_count` 得到的商品排名 |

`none` 不作为商品参与 ranking。

可在 Case summary / manifest 中同时记录：

- `n_population`
- `n_market_positive`
- `n_none`
- `market_entry_rate`

## 6. GT1 与 GT2 的关系

GT1：

```text
已知发生市场内选择
user -> target_product
```

GT2：

```text
完整 Case population
user -> product / none
        ↓
aggregate demand
        ↓
market ranking
```

GT1 主要评估商品选择能力；GT2 同时覆盖是否发生市场内目标行为以及需求在商品间的分配。

## 7. Benchmark Split

Split 与 Market / Case 数据本身分离，只保存引用。

例如 `splits/learning.json`：

```json
{
  "split_name": "learning",
  "markets": [
    {
      "market_id": "market_001",
      "case_ids": ["case_001", "case_002"]
    },
    {
      "market_id": "market_002",
      "case_ids": ["case_004"]
    }
  ]
}
```

同一 schema 可支持：

- 同 Market 的早期 Case 用于 learning，后期 Case 用于 temporal evaluation；
- 整个 Market held out，用于 unseen-market evaluation。

## 8. 核心层级

```text
MARKET
├── market definition
├── product universe
├── shared population
├── shared user interactions
│
└── CASES
    ├── focal
    ├── t0
    ├── shelf
    ├── selected user_ids
    └── ground truth
        ├── GT1: user -> product
        └── GT2: user -> product / none
                       ↓
                  market ranking
```

该 schema 的核心原则是：Market 层保存可被多个 Case 复用的资产；Case 层只保存一次新品进入事件特有的时间、货架、用户选择与 Ground Truth。
