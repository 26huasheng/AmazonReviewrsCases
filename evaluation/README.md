# evaluation

这一层是 benchmark 的评测入口，不包含模拟器本体。它把模拟器 / agent 输出与 GT1、GT2、商品需求排名对齐。

## 1. 用户侧预测接口

最小预测表：

```text
case_candidate_id
user_id
predicted_outcome_product_id
```

其中：

```text
商品 ID -> 预测该用户选择该 shelf 商品
NULL    -> 预测 none
```

也兼容列名 `predicted_product_id`。

## 2. GT1 指标

在 GT1 正例用户上计算：

```text
gt1_choice_accuracy
```

即已知真实发生市场内目标行为时，模型预测的商品是否正确。

## 3. GT2 指标

在全部 Case population 上计算：

```text
gt2_outcome_accuracy
market_entry_accuracy
actual_market_positive
predicted_market_positive
market_positive_count_abs_error
```

因此能同时看：

```text
会不会进入市场
+
进入以后商品分配是否正确
```

## 4. 商品级需求 / 排名

如果不额外提供 market prediction，代码直接把用户预测聚合成每个商品的 predicted demand count。

也可以单独提供：

```text
case_candidate_id
product_id
predicted_demand_count
```

或 `predicted_demand_score / predicted_rank`。

商品侧当前计算：

```text
Kendall tau
NDCG
true / predicted demand total
demand total absolute error
```

最终 `case_metrics.parquet` 把用户侧与商品侧指标合在一起。

## 5. Split 对齐

可选传入：

```text
split_assignments.parquet
```

输出会带：

```text
split_name
evaluation_regime
```

后续可以分别汇总：

```text
seen_market_temporal
unseen_market
```

## 6. 运行

```bash
python -m evaluation.cli \
  --population-truth /path/to/population_truth.parquet \
  --choice-truth /path/to/choice_truth.parquet \
  --market-truth /path/to/market_truth.parquet \
  --individual-predictions /path/to/predictions.parquet \
  --split-assignments /path/to/split_assignments.parquet \
  --output-dir outputs/evaluation
```

当前指标是确定性选择 / 排名的第一版接口。概率预测、校准和文本 Turing test 等扩展见 [`TODO.md`](TODO.md)。
