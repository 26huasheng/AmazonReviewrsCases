# benchmark_split TODO

## 需要冻结

1. headline benchmark 最终采用 `market_holdout` 还是 `hybrid`。
2. unseen Market 比例。
3. validation 是否正式保留，以及比例。
4. seen-market temporal evaluation 在每个 Market 至少需要多少个 accepted cases 才有意义。

## 需要补的约束

- 如果后续 Market 有人工语义族 / 上位类标签，可增加 group-aware holdout，避免极近义 Market 跨 split。
- 如果同一商品因为数据修订出现在多个 Market，需要在 split 前由 schema validator 直接报错，不能靠 split 修复。

## 固定原则

- split 在 Case 质量筛选之后做；
- 不使用 GT 数值、focal 排名或模型表现来决定 split；
- split 只保存引用，不复制数据；
- frozen split 应和 seed / strategy / fractions 一起版本化。
