# Case quality TODO

## 必须用真实 Case 分布冻结的阈值

- 最小 shelf 商品数 / competitor 数；
- 最小 Case 用户数；
- 最小 GT1 正例数；
- 最小 GT2 market-positive 数；
- 可接受的 `none_rate` 范围；
- focal future activity / market pre-t0 activity 的门槛。

当前代码已经支持这些字段和配置入口，但默认不替研究者决定数字。

## Keepa / 外部销量

需要新增独立的数据获取与整理阶段，最终只需产出：

```text
case_candidate_id
<external signal columns...>
```

即可接入本层。

待确定：

1. 用 BSR 哪个时间窗口作为 case screening；
2. 是否要求完整历史价格 / BSR 覆盖；
3. 外部销量代理只用于筛 Case，还是也进入最终商品级评测；
4. Amazon 大类间 BSR 是否可直接比较，若不可则只做 Market 内 / category 内标准化。

## 质量门槛版本化

正式 benchmark 冻结后，`quality_rules.json` 应作为 benchmark 配置文件保存，并给出规则版本号。之后改阈值应产生新 benchmark version，不覆盖旧结果。
