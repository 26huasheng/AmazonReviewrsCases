# benchmark_split

这一层只在 **accepted cases 已经确定以后** 划分 learning / validation / evaluation。它只看：

```text
market_id
case_candidate_id
t0
```

不读取 GT，因此 split 不会因为结果好坏发生选择偏差。

## 支持三种策略

### 1. `market_holdout`

按 `market_id + seed` 稳定哈希分 Market：

```text
某个 Market 的全部 Case -> 同一个 split
```

evaluation 中的 Market 在 learning 阶段完全没出现，对应强的 unseen-market generalization。

### 2. `temporal_within_market`

每个 Market 内按 `t0` 排序：

```text
早期 Case -> learning
中间 Case -> validation
后期 Case -> evaluation
```

同一 Market 的后期 Case 用于 seen-market temporal generalization。

### 3. `hybrid`

先按 Market 哈希留出一部分 unseen evaluation markets；其它 seen markets 再按时间切 learning / validation / later evaluation。

这能在一套 split 里同时保留：

```text
unseen_market
seen_market_temporal
```

两种 evaluation regime。

## 输出

```text
<output-dir>/
├── split_assignments.parquet
├── learning.json
├── validation.json
├── evaluation.json
└── split_summary.json
```

`split_assignments.parquet`：

```text
case_candidate_id
market_id
t0
split_name
evaluation_regime
```

三个 JSON 只保存 Market / Case 引用，不复制 Case 数据。

## 运行

```bash
python -m benchmark_split.cli \
  --accepted-cases outputs/quality/accepted_cases.parquet \
  --strategy hybrid \
  --unseen-market-fraction 0.2 \
  --learning-fraction 0.7 \
  --validation-fraction 0.1 \
  --output-dir outputs/splits
```

比例只是配置接口，正式 benchmark 数字仍需要冻结。见 [`TODO.md`](TODO.md)。
