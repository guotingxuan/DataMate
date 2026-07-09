# chronic_sqlite_loader

作用：便携式 SQLite 装载算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `data/processed/normalized_tables/`

输出文件：
- `data/sqlite/chroniccare.db`
- `data/processed/sqlite_loader_report.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_sqlite_loader/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_sqlite_loader --params '{}'
```

当前定位：慢病链路第 9 步。

与后续 Nexent/MCP 工具的关系：SQLite 数据库是 `analysis/query`、NL2SQL 评测和报告洞察的直接数据底座。
