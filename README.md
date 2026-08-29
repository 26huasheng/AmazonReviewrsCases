# AmazonReviewrsCases

第一版仓库骨架。本仓承接 Amazon Reviews 大类数据上的 **case 出厂之后、以及为 case / 评测服务的数据集扫描**，不重复 `AmazonReviewrepo` v5 里的市场发现与打包产线。

当前状态：只有文档，没有可运行代码。

## 仓库范围

| 放这里 | 不放这里 |
|--------|----------|
| 大类级人口 / 用户扫描 | Market Discovery、cross-path |
| 后续 case 批次说明与评测入口（待定） | temporal split、竞品池、packaging |
| 与 SEMS case 包衔接的说明 | 模拟器本体（FW 仓） |

造 case 的 pipeline 仍在 `AmazonReviewrepo`（`v5`）。本仓从「已经有某个 Amazon 大类的数据文件」出发，补数据集侧的统计与后续评测资产。

## 当前目录

```text
README.md                 本文件
population_scan/          大类人口扫描（先只有说明文档）
  README.md
```
