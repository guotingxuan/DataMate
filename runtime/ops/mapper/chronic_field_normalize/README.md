# chronic_field_normalize

作用：便携式字段归一化算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `data/processed/clean_tables/`

输出文件：
- `data/processed/normalized_tables/`
- `data/processed/field_normalize_report.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_field_normalize/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_field_normalize --params '{}'
```

当前定位：慢病链路第 3 步。

与后续 Nexent/MCP 工具的关系：归一化表是 SQLite 装载、指标分析和图谱结构化建模的重要前置输入。
