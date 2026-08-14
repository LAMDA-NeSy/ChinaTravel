# ChinaTravel

[English](README.md) | [简体中文](README.zh-CN.md)

**ChinaTravel：面向语言智能体、支持组合约束验证的开放式真实旅行规划基准**
（ICLR 2026）

ChinaTravel 是一个真实旅行规划基准，包含结构化沙盒数据、自然语言需求、
可执行 DSL 约束、常识验证和偏好评分。

[![项目主页](https://img.shields.io/badge/项目主页-访问-blue)](https://www.lamda.nju.edu.cn/shaojj/chinatravel/)
[![论文](https://img.shields.io/badge/论文-查看-red)](https://arxiv.org/abs/2412.13682)
[![数据集](https://img.shields.io/badge/数据集-HuggingFace-yellow)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
[![TPC@IJCAI2026](https://img.shields.io/badge/竞赛-TPC%40IJCAI2026-green)](https://chinatravel-competition.github.io/IJCAI2026/)

## 赛后完整发布

`next` 是计划在审阅完成后替代当前 `main` 的候选集成分支，目前尚未成为默认分支。
它整合了 TPC@IJCAI 2026 比赛期间及赛后的工程工作：

- 重构后的 OpenAI-compatible 模型运行时，同时支持 Chat Completions 和
  Responses API；
- 通过 `--lang zh` 和 `--lang en` 显式选择中文或英文查询与沙盒；
- 比赛期间全部正式测评修复，包括实体落库、活动时间顺序、交通验证、餐次统计、
  硬约束执行、无效结果计分、确定性数据加载及测评缓存；
- 模块化合成数据生成器、约束目录、独立审计与发布导出流程；
- 中译英 DSL/Query 翻译、规则与 LLM 联合审计、选择性修复、保守重审和人工裁决工具；
- 可复现的英文沙盒规范化导出工具。

本分支不包含比赛私有测试集、生成后的私有数据、API 密钥或本地模型输出。

## 更新日志

### 2026.08

- 开源模块化合成数据生成 pipeline，包括约束与模板目录、可控采样 profile、seed plan
  验证、独立数据审计和仅包含 Query 的发布导出工具；
- 整合比赛期间的测评修复，包括实体落库、时间顺序、交通、餐次、硬约束执行、
  无效结果计分、双语规范化、确定性加载和性能缓存；
- 加入重构后的 OpenAI-compatible runtime、双语 Agent 环境、翻译审计与修复流程、
  英文沙盒修复导出工具以及中英文文档。
- 将机器相关的示例路径替换为仓库相对且已被 Git 忽略的 `artifacts/`，方便在不同
  环境中直接运行。

## 目录结构

| 路径 | 用途 |
| --- | --- |
| `chinatravel/` | Agent、双语沙盒、DSL 和测评器核心代码 |
| `agent_env/` | 结构化工具、CLI/HTTP/MCP 适配及 split harness |
| `synthetic_query_generation/` | 合成 Query 生成与独立审计 |
| `scripts/` | 翻译、修复和沙盒导出工具 |
| `tests/` | 测评、语言、DSL 和数据工具回归测试 |
| `run_exp.py`、`run_tpc.py` | Agent 运行入口 |
| `eval_exp.py`、`eval_tpc.py` | 标准测评与 TPC 测评入口 |

## 安装

`pyproject.toml` 要求 Python 3.12 或更高版本。

使用 `uv`：

```bash
uv sync
source .venv/bin/activate
```

或使用 Conda 和 pip：

```bash
conda create -n chinatravel python=3.12
conda activate chinatravel
pip install -r requirements.txt
```

从 [Google Drive](https://drive.google.com/drive/folders/1bJ7jA5cfExO_NKxKfi9qgcxEbkYeSdAU)
或 [南京大学云盘](https://box.nju.edu.cn/d/dd83e5a4a9e242ed8eb4/) 下载官方沙盒数据，
并放置为：

```text
chinatravel/environment/database/       # 中文沙盒
chinatravel/environment/database_en/    # 英文沙盒
```

运行时所选语言的沙盒必须存在。为保持向后兼容，标准运行和测评脚本默认使用中文；
英文数据必须显式传入 `--lang en`。

## 模型运行时

可以使用 `deepseek`、`gpt-4o`、`glm4-plus` 等内置别名，也可以直接指定任意
OpenAI-compatible 服务提供的模型名。

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://your-provider.example/v1"

# chat：OpenAI-compatible Chat Completions，默认模式
# responses：OpenAI Responses API
export CHINATRAVEL_OPENAI_WIRE_API="chat"

# 可选：服务端使用的 token 上限参数名
export CHINATRAVEL_OPENAI_TOKEN_LIMIT_ARG="max_tokens"
```

其他可用环境变量：

- `CHINATRAVEL_OPENAI_MODEL`：没有传入 `--llm` 时使用的默认模型；
- `CHINATRAVEL_OPENAI_API_KEY`：优先于 `OPENAI_API_KEY` 的密钥；
- `CHINATRAVEL_OPENAI_BASE_URL`：优先于 `OPENAI_BASE_URL` 的地址；
- `CHINATRAVEL_OPENAI_RAISE_ERRORS=1`：调试时直接抛出服务端错误；
- `CHINATRAVEL_OPENAI_STRICT_TOOLS=1`：输出严格 OpenAI 工具 schema。

Responses 模式要求 `openai>=1.66.0`。密钥只能放在环境变量或已忽略的本地配置中。

## 运行 Agent

运行英文或中文 split：

```bash
python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang en

python run_exp.py \
  --splits easy \
  --agent LLMNeSy \
  --llm provider/model-name \
  --lang zh
```

仅在算法明确需要 Oracle 标注时使用：

```bash
python run_exp.py \
  --splits human \
  --agent LLM-modulo \
  --llm provider/model-name \
  --refine_steps 10 \
  --oracle_translation \
  --lang en
```

`--oracle_translation` 会向算法暴露 `hard_logic_py` 和 `hard_logic_nl`；正常的
选手可见运行不应开启。Query 文件必须使用当前 JSON schema；如果存在
`hard_logic_py`，它必须是 JSON 列表，不能是字符串编码的列表。

结果保存在 `results/<method>/`。

## 测评

结果、Query 和沙盒必须使用同一种语言：

```bash
python eval_exp.py --splits human --method YOUR_METHOD --lang en
python eval_tpc.py --splits tpc_phase1 --method YOUR_METHOD --lang en
```

TPC 测评器会报告 schema、常识、硬约束、FPR 和偏好指标。未通过必要有效性检查的
结果，在对应偏好平均分中按零分计入，偏好分不能绕过无效行程。

加固后的测评器还会检查：

- POI 和交通实体是否真实存在于沙盒；
- 活动是否按时间顺序排列且不重叠，交通出发时间是否合法；
- 城际交通是否出现在正确位置，以及位置约束是否错误匹配交通；
- 免费酒店早餐每天最多计入一次；
- 中英文概念值是否规范，并兼容必要的历史别名；
- DSL 是否安全执行，以及历史单引号 POI 名称是否正确解析。

## Agent 环境与 Harness

`agent_env` 提供 Python、CLI、HTTP、MCP、Chat Completions tool call 和
Responses function call 接口。

```bash
python -m agent_env --lang en tools
python -m agent_env --lang en call attractions_keys '{"city":"Shanghai"}'
CHINATRAVEL_LANG=en python -m agent_env.mcp_stdio
```

按 split 运行 harness：

```bash
cp agent_env/config.toml.example agent_env/config.toml
python agent_env/scripts/solve_script_with_harness.py
```

示例配置默认使用英文。本地 `config.toml` 已被忽略，因为其中可能包含服务密钥。
OpenCode、Codex、断点续跑、输出文件、HTTP 和 MCP 的详细说明见
[Agent 环境中文文档](agent_env/README.zh-CN.md)。

## 合成 Query 生成

生成器只从已经有效的 seed plan 中采样可执行约束；每条候选约束和最终约束组合
都会再次验证，并生成可审计的 manifest。

以下命令默认从仓库根目录执行，生成文件统一写入仓库相对且已被 Git 忽略的
`artifacts/`。在其他环境集成时可以显式替换为所需输出位置。

```bash
python -m synthetic_query_generation seed-queries \
  --output-dir artifacts/synthetic/seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026

python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir artifacts/synthetic/generated \
  --num-records 100 \
  --lang en \
  --seed 2026 \
  --copy-seed-plans

python -m synthetic_query_generation.audit \
  --dataset-dir artifacts/synthetic/generated \
  --expected-records 100 \
  --profile full \
  --lang en
```

约束族和单个模板 key 都可以独立启用、禁用或提高采样优先级。详细说明见
[合成 Query 生成中文文档](synthetic_query_generation/README.zh-CN.md)。

## 翻译与数据修复

翻译流程支持 OpenAI-compatible Chat Completions、自定义 `base_url`、请求头、
模型参数、并发数和通过 `extra_body` 添加的 JSON 顶层请求字段。它结合规则与 LLM
审计，只修改审计策略明确选中的记录。

```bash
cp translation_api_config.example.json translation_api_config.json
export TRANSLATION_API_KEY="your-key"

python scripts/build_translation_assets.py
python scripts/audit_phase1_translations.py
python scripts/repair_phase1_translations.py
```

详细说明见[翻译与审计中文文档](scripts/TRANSLATION_PIPELINE.zh-CN.md)。

导出规范化英文沙盒时，不会修改原始数据库：

```bash
python scripts/export_fixed_sandbox.py artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --archive artifacts/sandbox/ChinaTravel_sandbox_en_fixed.zip
```

压缩包包含 manifest、修改报告和校验和。见
[修复版沙盒导出说明](scripts/SANDBOX_EXPORT.md)。

## 测试

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

回归测试覆盖双语传播、Query 解析、测评实体落库与计分、时间顺序、早餐限制、性能缓存、
DSL 安全控制流、合成约束和翻译修复。

## 文档

- [英文 README](README.md)
- [环境数据](chinatravel/environment/readme.md)
- [约束验证](chinatravel/symbol_verification/readme.md)
- [Agent 环境](agent_env/README.zh-CN.md)
- [合成 Query 生成](synthetic_query_generation/README.zh-CN.md)
- [翻译与审计](scripts/TRANSLATION_PIPELINE.zh-CN.md)
- [修复版沙盒导出](scripts/SANDBOX_EXPORT.md)
- [赛后版本验证报告](docs/RELEASE_VALIDATION.md)
- [TPC@AIC 2025](TPC@AIC2025/readme.md)

## 历届比赛

- [TPC@IJCAI 2026](https://chinatravel-competition.github.io/IJCAI2026/)
- [TPC@IJCAI 2025](https://chinatravel-competition.github.io/IJCAI2025/)

## 联系方式

如有问题，请联系 [Jie-Jing Shao](mailto:shaojj@lamda.nju.edu.cn)、
[Bo-Wen Zhang](mailto:221900200@smail.nju.edu.cn) 或
[Xiao-Wen Yang](mailto:yangxw@lamda.nju.edu.cn)。

## 引用

```bibtex
@inproceedings{shao2026chinatravel,
  title     = {ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents},
  author    = {Jie-Jing Shao and Bo-Wen Zhang and Xiao-Wen Yang and Baizhi Chen and Siyu Han and Pang Jinghao and Wen-Da Wei and Guohao Cai and Zhenhua Dong and Lan-Zhe Guo and Yu-Feng Li},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026},
  url       = {https://openreview.net/forum?id=0YRVlxY9BH}
}
```
