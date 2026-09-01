# TODO：Market Discovery / Cross-path 剩余项

Cross-path 的正式第一版规则已经实现：

```text
同一 source_partition
+ market_label 安全格式规范化后完全相等
→ 自动合并
```

当前实现不调用任何 cross-path merge LLM。

已覆盖的格式差异包括：

- 大小写；
- 空格 / `-` / `_` 等分隔符；
- 重复分隔符；
- 首尾空白；
- Unicode NFKC 兼容形。

例如：

```text
Phone_Case
phone-case
phone case
```

都会合并到：

```text
phone_case
```

## 还需要做的事情

### 1. 在真实全量输出上跑一次 merge audit

代码和单元测试已经有了，但还需要在正式 Market Discovery 全量结果上检查：

- merge 前后 market 数量；
- 每个 merge group 的原始 labels；
- 每个 merge group 涉及的 paths；
- 合并后的 product union 是否符合预期。

对应审计文件已经预留：

```text
cross_path_exact_merge_audit.json
cross_path_exact_merge_summary.json
```

### 2. 观察是否真实出现当前规范化覆盖不到的纯格式变体

当前不会自动处理无法安全恢复词边界的形式，例如：

```text
smartwatch
smart_watch
```

也不会处理：

```text
phone_case
phone_cases

phone_case
phone_cover
```

这些可能是词形变化、命名习惯，也可能已经涉及语义判断。第一版先保留成两个 market，避免误并。

如果全量 audit 证明存在大量明确的 **纯格式问题**，再针对具体模式增加确定性 normalization rule；不引入开放式 LLM semantic merge。

### 3. 搬/改更多 v5 regression tests

目前已经补了 cross-path normalized exact merge 的单元测试。

后续还可以从 `AmazonReviewrepo@v5` 继续迁：

```text
test_market_discovery_and_merge.py
test_market_scoring.py
```

迁移时只改 import 和已经变化的 cross-path 预期，不改核心 path-local scoring contract。

## 明确不列入 TODO

以下内容已经决定不做：

- LLM 同义词合并；
- semantic embedding merge；
- complete-link 聚类；
- 商品集合重叠驱动的自动 merge；
- 为了减少 market 数量主动扩大合并范围。
