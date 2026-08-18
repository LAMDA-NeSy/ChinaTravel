# ChinaTravel Agent 环境

[English](README.md) | [简体中文](README.zh-CN.md)

该目录将 ChinaTravel 官方环境包装为适合 Agent 调用的结构化接口。`run_exp.py`、
`eval_exp.py` 和 `eval_tpc.py` 仍然是正式运行与测评的依据。

## 提供的能力

- `ChinaTravelEnvAdapter`：延迟加载 `WorldEnv` 的 Python API；
- CLI：支持一次性调用和交互式调用；
- stdio MCP：供支持 MCP 的 Agent 客户端连接；
- HTTP JSON 服务：供其他进程调用；
- OpenAI Chat Completions 和 Responses 工具 schema/结果转换；
- split harness：调用 OpenCode 或 Codex，保存 plan，并逐条测评。

## 前置条件

```bash
pip install -r requirements.txt
```

根据语言准备沙盒：

```text
chinatravel/environment/database/       # zh
chinatravel/environment/database_en/    # en
```

必须使用 [Hugging Face 当前官方沙盒](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox)。
旧沙盒快照不受支持；运行时会直接使用沙盒中的实体名称和概念标签，不再自动替换历史别名。

## CLI

列出工具并进行结构化调用：

```bash
python -m agent_env --lang en tools
python -m agent_env --lang en call attractions_keys '{"city":"Shanghai"}'
python -m agent_env --lang zh call attractions_keys '{"city":"上海"}'
```

调用原始 `WorldEnv` 命令接口：

```bash
python -m agent_env --lang en world "attractions_keys('Shanghai')"
```

不带子命令会进入交互模式：

```bash
python -m agent_env --lang en
```

## MCP

```bash
CHINATRAVEL_LANG=en python -m agent_env.mcp_stdio
```

`CHINATRAVEL_LANG` 支持 `en` 和 `zh`，同时控制 Query 语言、沙盒数据库和测评语言。
建议优先调用 `attractions_select`、`restaurants_nearby`、`goto`、
`intercity_transport_select` 等结构化工具；只有在确有需要时才使用
`china_travel_world_command`。

## Split Harness

创建不会被 Git 跟踪的本地配置：

```bash
cp agent_env/config.toml.example agent_env/config.toml
```

`[run]` 中的主要字段：

| 字段 | 含义 |
| --- | --- |
| `split` | 要处理的 split 名称 |
| `lang` | `en` 或 `zh` |
| `harness` | `opencode` 或 `codex` |
| `method` | 结果目录名；为空时自动生成 |
| `work_dir` | harness 工作目录 |
| `tool_python` | 调用环境工具使用的 Python 命令 |
| `uid` | 只运行指定 UID |
| `limit` | smoke test 数量，`0` 表示不限制 |
| `resume` | 跳过已有结果 |
| `no_run_harness` | 不启动 Agent，仅解析已有输出 |
| `plan_file` | 直接使用指定 plan 文件 |

运行：

```bash
python agent_env/scripts/solve_script_with_harness.py
```

常见覆盖参数：

```bash
python agent_env/scripts/solve_script_with_harness.py --lang en --uid <uid>
python agent_env/scripts/solve_script_with_harness.py --harness opencode --model provider/model
python agent_env/scripts/solve_script_with_harness.py --harness codex --model model-name
python agent_env/scripts/solve_script_with_harness.py --resume
```

没有显式指定 `method` 时，结果目录名为 `<model>-<split>-<harness>`。输出包括：

- `results/<method>/<uid>.json`：最终 itinerary；
- `agent_env/runs/<method>/<split>_<uid>/`：提示词和原始日志；
- 同目录的 `evaluation.json`：单条测评结果；
- `agent_env/runs/<method>/<split>_summary.json`：split 汇总。

Harness 内部会加载 Oracle 字段用于测评，但会在调用选手 Agent 前移除这些字段。
解析失败会保存为全 false 的单条结果，并在汇总中记录失败数量。

## HTTP

```bash
python -m agent_env.http_server --lang en --host 127.0.0.1 --port 8765
```

```bash
curl http://127.0.0.1:8765/tools

curl -X POST http://127.0.0.1:8765/call \
  -H 'Content-Type: application/json' \
  -d '{"tool":"attractions_keys","arguments":{"city":"Shanghai"}}'
```

## 边界

该包装层负责沙盒访问、工具协议转换和 harness 运行，不替代正式 scorer。最终结果应使用
`eval_exp.py` 或 `eval_tpc.py`，并传入与 Query、沙盒一致的 `--lang`。
