# evaluation TODO

## 概率预测接口

当前 evaluator 先支持确定性的：

```text
user -> product / none
```

后续如果模拟器输出概率，需要增加：

- `P(buy | u, M)` 的 Brier / log loss / calibration；
- `P(product | buy, u, M)` 的 top-k / log loss；
- 完整 `P(user -> product)` 的概率评分。

## 商品级指标

当前有 Kendall tau、NDCG、需求总量绝对误差。后续可选增加：

- Spearman；
- top-k overlap；
- demand share MAE / JS divergence；
- focal rank error；
- 和 `review_activity_truth` / 外部 BSR ranking 的辅助对照。

## 文本评测

0820 设计里的 review text Turing test 还没有进入当前两层数值 GT evaluator。需要在后续明确：

- 文本生成任务输入；
- 真人 / 模拟评论抽样方式；
- judge 模型与人工评测协议；
- 是否作为主 benchmark 指标还是独立附加实验。

## 汇总方式

需要冻结最终论文报告口径：

- macro by Case；
- macro by Market；
- 按用户数 weighted；
- seen-market temporal / unseen-market 分开报告。

当前代码输出 per-case 指标和简单平均，保留足够字段供后续重算汇总。
