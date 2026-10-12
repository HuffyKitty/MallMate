# MallMate 离线评估模块

当前评估不需要 API Key，也不会调用 LangGraph 或通义千问。它为后续模型评估建立一条可重复的确定性基线。

## 数据划分

| 数据集 | 开发集 | 留出集 | 评估内容 |
|---|---:|---:|---|
| 意图 | 40 | 20 | 10 类意图、4 档紧急度、Macro-F1 |
| 检索 | 24 | 12 | Recall@5、MRR、NDCG@5 |
| 售后规则 | 12 | 6 | 资格、决策码、凭证与人工要求完全匹配 |

开发集用于日常改进。留出集只在版本冻结后运行，避免根据最终答案反复调规则。所有时间相关用例都固定 `evaluation_time`，保证不同日期运行结果一致。

## 运行方式

在项目根目录执行：

```powershell
& .\.venv\Scripts\python.exe .\evals\runner.py --split dev
```

版本冻结后再运行：

```powershell
& .\.venv\Scripts\python.exe .\evals\runner.py --split holdout
```

JSON 报告写入 `evals/reports/`。脚本在任一门槛未达到时返回退出码 1，便于以后接入 CI。

## 当前边界

- 意图评估测试规则基线，尚未测试 Qwen、Embedding 投票或多轮上下文。
- 检索评估测试 BM25 基线，尚未接入 ChromaDB 向量召回、RRF 和重排。
- 规则评估测试纯函数，尚未重放数据库事务、工具超时和 LangGraph 轨迹。
- 当前数据全部为人工设计的合成数据，正式指标必须加入脱敏真实咨询并由至少两人复核标注。

下一阶段会增加 `agent_workflow`、权限、提示注入、工具故障、回答引用正确性和 LLM-as-Judge 数据集，并把模型、Prompt、知识库、规则和代码提交版本一并写入报告。
