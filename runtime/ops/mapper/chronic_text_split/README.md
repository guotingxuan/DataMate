# chronic_text_split

作用：便携式文本切分算子入口。当前目录可独立迁移，运行时不再依赖 `integrations/datamate/shared.py` 或 `datamate_ops` 包路径。

输入文件：
- `data/processed/text_clean/`

输出文件：
- `data/processed/chunks/`
- `data/processed/text_split_report.json`

单独运行示例：

```bash
python integrations/datamate/operators/chronic_text_split/process.py --project-root . --export-path outputs/day14/operator_runs/chronic_text_split --params '{}'
```

当前定位：慢病链路第 4 步。

与后续 Nexent/MCP 工具的关系：chunks 会继续支持实体抽取、关系抽取与图谱前置处理。
