# chronic_report_pack

作用：便携式报告打包算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `outputs/reports/day6_indicator_results.json`
- `data/graph/graph_summary.json`

输出文件：
- `outputs/reports/day7_analysis_report.html`
- `outputs/reports/day7_analysis_report.md`
- `outputs/charts/chart_index.html`
- `outputs/reports/day7_report_export_report.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_report_pack/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_report_pack --params '{}'
```

当前定位：慢病链路第 11 步。

与后续 Nexent/MCP 工具的关系：`chroniccare_report_summary`、`chroniccare_agent_run` 和 Streamlit 展示入口都会继续复用这些真实产物。
