# AmazonReviewrsCases

第一版仓库骨架。本仓承接 Amazon Reviews 大类数据上的 **case 出厂之后、以及为 case / 评测服务的数据集扫描**，不重复 `AmazonReviewrepo` v5 里的整条打包产线。

当前状态：以文档为主；`market_discovery/` 是从 v5 原样拷过来的代码（主流程文件仍在补齐）。

## 仓库范围

| 放这里 | 不放这里 |
|--------|----------|
| 大类级人口 / 用户扫描 | temporal split、竞品池、packaging |
| Market Discovery（v5 原样拷贝） | 模拟器本体（FW 仓） |
| Cross-path 窄合并（先只有 TODO） | v5 那套开放同义词 + complete-link |
| 后续 case 批次说明与评测入口（待定） | |

## 当前目录

```text
README.md
population_scan/                 大类人口扫描（先只有说明）
market_discovery/                v5 Market Discovery 原样拷贝
  TODO_CROSS_PATH.md             下一步：只并格式不同的同名市场
utils.py
paths.py
```
