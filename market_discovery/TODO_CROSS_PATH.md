# TODO：Cross-path 合并（尚未实现）

位置：与本目录的 Market Discovery 衔接，代码以后从 `AmazonReviewrepo` v5 的 `market_merge` **搬过来再砍薄**，现在先只写口径。

Discovery 按 Amazon **类目路径**各自定义 local market。不同 path 上会出现「其实是同一个购买对象」的市场。v5 现有 cross-path 会做精确同名 + LLM 同义词 + complete-link 聚类，范围偏宽。本仓后续只要一层很窄的合并。

## 目标

只合并 **名称已经是同一回事、只是写法/格式不一样** 的市场。
不根据商品重叠、不根据 LLM 自由发明同义词去并市场。

## 允许合并的情况

视为「名称完全一致」的，例如：

- 大小写：`Phone_Case` / `phone_case`
- 分隔符：`phone-case` / `phone_case` / `phone case`
- 多余空白、首尾空格、重复下划线
- Unicode 兼容形（NFKC）之后相同

规范化后字符串相等 → **直接合并**，不必问 LLM。

## 最多再加的一步：简单相似 + LLM 复核

规范化之后仍不相等的 pair，可以算一个很便宜的字面相似度（如规范化标签的编辑距离 / token Jaccard）。

- 低于阈值：不是候选，不送 LLM
- 超过阈值：只把这个 pair 交给 LLM，问一句「是不是同一个 product object 的两种写法」
- LLM 说是，才合并；说不是或不确定，保持两个市场

LLM 不得：

- 提出新的市场名
- 以「都是手机配件」这类上位概念为由合并
- 把 `phone_case` 和 `phone_cover` 这类近义（若规范化后仍不同）自动当成同名；只有过了相似度阈值且 LLM 明确判定「只是格式/叫法」才可以

第一版实现时，相似度阈值先写进配置，不写死。宁可漏并，不要错并。

## 明确不做

- v5 那种开放的同义词发现、complete-link 一大团并在一起
- 用商品集合重叠、共同 ASIN、共同 path 当合并证据
- 一次合并超过一对（先 pair-wise；真要并三个，必须每个 pair 都过关）
- 改 Market Discovery 的打分规则或 prompt

## 建议输入 / 输出（实现时再落文件）

输入：Discovery 的 `local_market_definitions` / `first_market`（每个 path 上的 `market_label`）。

输出设想：

- `cross_path/markets_after_merge.parquet`
- 一份审计：哪些是规范化后直接并的，哪些是过阈值后 LLM 判是的，哪些被 LLM 拒绝

人工审核可以后补，第一版不作为硬门。

## 实现顺序

1. 从 v5 `market_merge` 把能用的读写结构拷过来
2. 删掉同义词 / complete-link 那几支
3. 先接通「规范化后全等 → 合并」
4. 再加相似度阈值 + pair 级 LLM
5. 用几个已知同名异写、近义不应并的例子看审计表
