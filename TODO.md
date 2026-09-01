# Repository-level TODO

这份文件只记录会影响整个 benchmark 版本的未冻结研究口径。各模块自己的实现细节见对应目录 `TODO.md`。

## 1. Population 版本参数

需要在真实用户漏斗统计后冻结：

- Market population 来源：`category` / `global` / 两套 setting；
- Market shared population 目标规模；
- Case 用户 `min_history_products`；
- Case 用户最大 recency；
- 每个 Case 目标用户数；
- category / market relation 的最终分层抽样比例。

对应：

```text
population_scan/TODO.md
market_build/TODO.md
case_build/population/TODO.md
```

## 2. Shelf / 商品侧资格

需要真实 Market / Case 分布后冻结：

- shelf 是否需要上限；
- 极大 Market 的截断规则；
- 最近活动量是否做硬门槛；
- Keepa availability 是否增强首评 / 末评活跃区间代理；
- `price_at_t0` 的历史价格取值规则。

对应：`case_build/TODO.md`。

## 3. GT outcome policy

同一用户在 evaluation window 内命中多个 shelf 商品时，目前代码实现 `first_observed_event`，正式 benchmark 需要确认是否冻结这一规则。

对应：`case_build/ground_truth/TODO.md`。

## 4. Case Quality Gate

结构性校验已经固定；研究阈值需要基于完整 Case 分布冻结：

```text
min shelf / competitor
min selected users
min GT1 users
min GT2 market-positive
max none rate
focal / market activity thresholds
Keepa / BSR screening
```

正式规则应保存成版本化 `quality_rules.json`。

对应：`case_build/quality/TODO.md`。

## 5. Benchmark Split

需要冻结 headline benchmark 的 split regime：

- 强调 unseen-market：`market_holdout`；
- 同时保留 unseen + seen-market temporal：`hybrid`；
- learning / validation / evaluation 比例；
- unseen Market 比例。

对应：`benchmark_split/TODO.md`。

## 6. 发布 / evaluator 隔离

需要在最终评测系统确定后冻结：

- held-out evaluation GT 的存放与访问边界；
- 公开版用户 ID 匿名化；
- Market population 完整 history 是按 Market 物化，还是用共享 event store + manifest 引用降低体积；
- 是否增加 weekly / cumulative derived truth。

对应：`benchmark_export/TODO.md`。

## 7. 外部数据

Keepa / BSR 获取逻辑当前通过 `quality --external-signals` 预留了稳定接口，尚未把具体付费 API 客户端写入本仓。

外部数据层最终至少要定义：

```text
case_candidate_id
product_id（需要时）
signal timestamp / window
BSR / sales proxy / historical price
coverage / missing status
```

外部信号首先服务 Case 筛选；是否进入正式评测指标另行冻结。

---

## 已经固定、不要重新讨论的主结构

```text
Market
├── 长期商品 universe
├── shared population / user history
└── Cases
    ├── focal
    ├── t0
    ├── t0 shelf
    ├── selected user ids
    └── GT
        ├── GT1: positive user -> product
        └── GT2: all selected users -> product / none
                         ↓
                    market demand ranking
```

以及：

- Market Discovery 的 cross-path 只做规范化后同名合并，不调用 LLM；
- `t0` 当前由 focal 首评时间近似；
- Case population 必须在 future GT 查询前固定；
- split 在 accepted cases 之后做，且不读取 GT 数值决定归属；
- 最终文件由 `benchmark_export/` 按 `SCHEMA.md` 物化。
