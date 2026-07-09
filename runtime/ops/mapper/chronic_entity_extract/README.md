# chronic_entity_extract

作用：便携式实体抽取算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `data/processed/chunks/`

输出文件：
- `data/processed/entities/`
- `data/processed/entity_extract_report.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_entity_extract/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_entity_extract --params '{}'
```

当前定位：慢病链路第 5 步。

与后续 Nexent/MCP 工具的关系：实体目录是关系抽取、三元组校验和图谱构建的直接输入。
