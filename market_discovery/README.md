# market_discovery

从 `AmazonReviewrepo` 分支 `v5`、路径 `sems_market_pipeline/market_discovery/` **原封不动**拷来，与 `population_scan/` 并列。

源 commit：`f7f66bc89f1023644f28461002290fbcf60a1573`

本目录代码仍使用原来的相对导入（`from ..utils`、`from ..paths`）。仓库根目录因此多了两份同样未改的依赖文件：`utils.py`、`paths.py`。没有改发现逻辑。

还不是独立可跑的新产线入口；输入仍是 v5 的 `product_core.parquet`。
