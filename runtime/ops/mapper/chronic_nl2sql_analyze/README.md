# chronic_nl2sql_analyze

作用：便携式 NL2SQL 分析算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `data/sqlite/chroniccare.db`
- `outputs/reports/day6_analysis_questions.json`

输出文件：
- `outputs/reports/day6_sql_candidates.json`
- `outputs/reports/day6_nl2sql_eval_report.json`
- `outputs/reports/day6_indicator_results.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_nl2sql_analyze/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_nl2sql_analyze --params '{}'
```

当前定位：慢病链路第 10 步。

与后续 Nexent/MCP 工具的关系：`chroniccare_analysis_questions` 和 `chroniccare_analysis_query` 工具直接消费这里的真实分析产物。
