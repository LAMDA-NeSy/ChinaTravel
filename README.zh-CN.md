<center>
  <h1>[ICLR'26] ChinaTravel：面向语言智能体、支持组合约束验证的开放式真实旅行规划基准</h1>
</center>

[English](README.md) | [简体中文](README.zh-CN.md)

ChinaTravel 是一个真实旅行规划基准，包含结构化沙盒数据、自然语言需求、
可执行 DSL 约束、常识验证和偏好评分。

[![项目主页](https://img.shields.io/badge/项目主页-访问-blue)](https://www.lamda.nju.edu.cn/shaojj/chinatravel/)
[![论文](https://img.shields.io/badge/论文-查看-red)](https://openreview.net/forum?id=0YRVlxY9BH)
[![Query 数据](https://img.shields.io/badge/Query-HuggingFace-yellow)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel)
[![Query 数据](https://img.shields.io/badge/Query-ModelScope-blue)](https://modelscope.cn/datasets/Cbphcr/ChinaTravel)
[![沙盒数据](https://img.shields.io/badge/沙盒-HuggingFace-orange)](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox)
[![沙盒数据](https://img.shields.io/badge/沙盒-ModelScope-blue)](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox)
[![TPC@IJCAI2026](https://img.shields.io/badge/竞赛-TPC%40IJCAI2026-green)](https://chinatravel-competition.github.io/IJCAI2026/)
[![TPC@IJCAI2025](https://img.shields.io/badge/竞赛-TPC%40IJCAI2025-green)](https://chinatravel-competition.github.io/IJCAI2025/)
[![TPC@AIC2025](https://img.shields.io/badge/竞赛-TPC%40AIC2025-green)](TPC@AIC2025/readme.md)

## 🏆 新闻

### TPC@IJCAI 2026

ChinaTravel 入选 IJCAI 2026 Travel Planning Challenge 官方基准。该赛事面向具有实际
约束的旅行规划任务，重点评估智能体系统的综合规划能力。详见
[赛事官网](https://chinatravel-competition.github.io/IJCAI2026/)。

### TPC@IJCAI 2025

ChinaTravel 入选 IJCAI 2025 Travel Planning Challenge 官方基准。该赛事邀请参赛者
开发能够处理复杂约束与真实旅行规划场景的语言智能体。详见
[赛事官网](https://chinatravel-competition.github.io/IJCAI2025/)。

### TPC@AIC 2025

ChinaTravel 同时支持了 AIC 2025 Travel Planning Challenge。赛事设置、测评指标、
提交格式和测评环境保留在[赛事归档](TPC@AIC2025/readme.md)中。

## 📝 更新日志

### 2026.08

2026.08 版本是 ChinaTravel 在比赛结束后的正式维护版本，统一整合了
TPC@IJCAI 2026 期间及赛后完善的基准、测评器、双语环境和数据工具：

- OpenAI-compatible 模型运行时，同时支持 Chat Completions 和 Responses API；
- 通过 `--lang zh` 和 `--lang en` 显式选择中文或英文 Query 与沙盒；
- 完整的测评加固，包括实体落库、活动时间顺序、交通验证、餐次统计、硬约束执行、
  无效结果计分、确定性数据加载和测评缓存；
- 模块化合成 Query 生成，包括约束目录、可控采样、独立审计和仅包含 Query 的发布
  导出流程；
- 中译英 DSL/Query 翻译，包括规则与 LLM 联合审计、选择性修复、保守重审和人工
  裁决流程；
- 可复现的规范化英文沙盒导出、同步发布于 Hugging Face 和魔搭的 Query 与沙盒数据，
  以及发布校验和；
- 使用仓库相对且已被 Git 忽略的 `artifacts/` 目录，便于在不同环境中运行本地流程。

比赛专用的生成数据和私有测试 split 另行分发。仓库不包含 API 密钥或本地模型输出。

### 2025.09

- 发布 TPC@IJCAI 2025 DSL 赛道冠军方案。感谢
  [@evergreenee](https://github.com/evergreenee) 的贡献。

### 2025.06

- 修复常识约束测评中的错误收集逻辑。
- 修复纯神经 Agent 流程。
- 修复 Hugging Face 数据集加载。
- 完善语法验证的异常处理。

### 2025.05

- 更新适配最新版本的日志。
- 发布 TPC 测评代码。

### 2025.04

- 增加本地 Query 加载能力：非默认的 `--splits NAME` 会读取
  `chinatravel/evaluation/default_splits/NAME.txt`，其中逐行列出待加载的 Query 文件。
- 在[测评文档](chinatravel/symbol_verification/readme.md)中发布详细约束分类。
- 引入带真实符号验证器的 LLM-modulo baseline，参考 *Robust Planning with Compound
  LLM Architectures: An LLM-Modulo Approach* 及其
  [开源实现](https://github.com/Atharva-Gundawar/LLM-Modulo-prompts)。
- 增加 Qwen3-8B 和 Qwen3-4B 本地推理支持。

## 📦 数据发布

| 资源 | Hugging Face | 魔搭 |
| --- | --- | --- |
| Query 数据集 | [LAMDA-NeSy/ChinaTravel](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel) | [Cbphcr/ChinaTravel](https://modelscope.cn/datasets/Cbphcr/ChinaTravel) |
| 双语沙盒 | [LAMDA-NeSy/ChinaTravel-Sandbox](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox) | [Cbphcr/ChinaTravel-Sandbox](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox) |

魔搭仓库镜像官方 Hugging Face Query 与沙盒数据。两个 Query 仓库均提供 Phase 1
splits，以及完整的 2,000 条 `TPC2026_phase2` 数据和其中 100 条
`competition_test` split。

## 🗂️ 目录结构

| 路径 | 用途 |
| --- | --- |
| `chinatravel/` | Agent、双语沙盒、DSL 和测评器核心代码 |
| `agent_env/` | 结构化工具、CLI/HTTP/MCP 适配及 split harness |
| `synthetic_query_generation/` | 合成 Query 生成与独立审计 |
| `scripts/` | 翻译、修复和沙盒导出工具 |
| `tests/` | 测评、语言、DSL 和数据工具回归测试 |
| `run_exp.py`、`run_tpc.py` | Agent 运行入口 |
| `eval_exp.py`、`eval_tpc.py` | 标准测评与 TPC 测评入口 |

## 🚀 安装

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

从 [Hugging Face](https://huggingface.co/datasets/LAMDA-NeSy/ChinaTravel-Sandbox)
或[魔搭](https://modelscope.cn/datasets/Cbphcr/ChinaTravel-Sandbox)下载官方双语沙盒数据，
并放置为：

```text
chinatravel/environment/database/       # 中文沙盒
chinatravel/environment/database_en/    # 英文沙盒
```

> [!IMPORTANT]
> `next` 分支必须配合当前官方沙盒版本使用。运行时不再自动修正旧版
> 英文概念标签或 POI 别名；旧 `database_en` 快照不受支持，可能导致工具返回值不同或
> 测评失败。Query、plan 和 DSL 中的实体名称必须与安装的沙盒完全一致。

运行时所选语言的沙盒必须存在。为保持向后兼容，标准运行和测评脚本默认使用中文；
英文数据必须显式传入 `--lang en`。

## 🤖 模型运行时

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

## ▶️ 运行 Agent

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

## 📊 测评

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
- 实体名称和概念值是否与当前沙盒中的规范值完全一致；
- DSL 是否安全执行，以及历史单引号 POI 名称是否正确解析。

## 🛠️ Agent 环境与 Harness

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

## 🧩 合成 Query 生成

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

## 🌐 翻译与数据修复

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

维护者如需将旧英文快照迁移为规范发布格式，可使用离线导出工具；它不会修改源数据库：

```bash
python scripts/export_fixed_sandbox.py artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --archive artifacts/sandbox/ChinaTravel_sandbox_en_fixed.zip
```

普通用户应直接下载 Hugging Face 或魔搭上的当前版本。维护工具生成的压缩包包含
manifest、修改报告和校验和，详见[修复版沙盒导出说明](scripts/SANDBOX_EXPORT.md)。

## ✅ 测试

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

回归测试覆盖双语传播、Query 解析、测评实体落库与计分、时间顺序、早餐限制、性能缓存、
DSL 安全控制流、合成约束和翻译修复。

## 📚 文档

- [英文 README](README.md)
- [环境数据](chinatravel/environment/readme.md)
- [约束验证](chinatravel/symbol_verification/readme.md)
- [Agent 环境](agent_env/README.zh-CN.md)
- [合成 Query 生成](synthetic_query_generation/README.zh-CN.md)
- [翻译与审计](scripts/TRANSLATION_PIPELINE.zh-CN.md)
- [修复版沙盒导出](scripts/SANDBOX_EXPORT.md)
- [赛后版本验证报告](docs/RELEASE_VALIDATION.md)
- [TPC@AIC 2025](TPC@AIC2025/readme.md)

## 🏆 历届比赛

- [TPC@IJCAI 2026](https://chinatravel-competition.github.io/IJCAI2026/)
- [TPC@IJCAI 2025](https://chinatravel-competition.github.io/IJCAI2025/)

## 🙏 致谢

感谢 [Stefan Schneider](https://github.com/stefanbschneider) 和 Team
fabiundstefan，包括 [Fabian Missbrenner](https://github.com/fabufab)，以负责任的方式
披露并详细记录测评器和计分问题。他们的反馈直接推动了本版本对时间顺序、交通、
餐次和有效性验证的完善。

同时感谢
[@450112489](https://github.com/450112489)、
[@zihaocheng-buaa](https://github.com/zihaocheng-buaa)、
[@277CPS](https://github.com/277CPS)、
[@DuanchuWang](https://github.com/DuanchuWang)、
[@evergreenee](https://github.com/evergreenee)、
[@yishu031031](https://github.com/yishu031031) 和
[@luck-lak](https://github.com/luck-lak) 对数据、测评、prompt、安装流程和文档提出的
可操作反馈；感谢 [@ploract](https://huggingface.co/ploract) 和
[@lucmek](https://huggingface.co/lucmek) 协助修正 Hugging Face Query 数据，并感谢
[Niels Rogge](https://github.com/NielsRogge) 建议在 Hugging Face 公开发布沙盒数据。

## ✉️ 联系方式

如有问题，请联系 [Jie-Jing Shao](mailto:shaojj@lamda.nju.edu.cn)、
[Bo-Wen Zhang](mailto:221900200@smail.nju.edu.cn) 或
[Xiao-Wen Yang](mailto:yangxw@lamda.nju.edu.cn)。

## 📌 引用

```bibtex
@inproceedings{shao2026chinatravel,
  title     = {ChinaTravel: An Open-Ended Travel Planning Benchmark with Compositional Constraint Validation for Language Agents},
  author    = {Jie-Jing Shao and Bo-Wen Zhang and Xiao-Wen Yang and Baizhi Chen and Siyu Han and Pang Jinghao and Wen-Da Wei and Guohao Cai and Zhenhua Dong and Lan-Zhe Guo and Yu-Feng Li},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026},
  url       = {https://openreview.net/forum?id=0YRVlxY9BH}
}
```
