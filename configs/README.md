# configs

这里放 **正式 benchmark 版本冻结时需要保存的研究配置模板**。

当前有：

```text
quality_rules.example.json
benchmark_version.example.json
```

模板里的 `null / UNFROZEN` 表示研究口径还没由真实数据分布确定，不能直接当正式 benchmark 参数。

正式发布时建议复制成版本目录，例如：

```text
configs/v1/
├── benchmark_version.json
└── quality_rules.json
```

并保证 `benchmark_version.json` 记录：Market Discovery 版本、population policy、Case 用户阈值、GT outcome policy、Quality 规则、split strategy/seed、外部信号版本和 schema version。
