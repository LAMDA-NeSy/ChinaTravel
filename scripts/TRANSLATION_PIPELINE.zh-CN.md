# 翻译与审计流程

[English](TRANSLATION_PIPELINE.md) | [简体中文](TRANSLATION_PIPELINE.zh-CN.md)

该目录保留了 Phase 1 中文到英文的数据翻译、校验、选择性修复和人工裁决流程。
API 密钥只从环境变量读取，不应写入配置文件。

## 配置

```bash
cp translation_api_config.example.json translation_api_config.json
export TRANSLATION_API_KEY="your-key"
```

使用 `--no-api` 时，字典和记录处理阶段不会加载 API 配置文件，也不需要 API key。

`translation_api_config.json` 已被 Git 忽略。配置支持：

- 自定义 OpenAI-compatible `base_url` 和 Chat Completions 路径；
- API key 环境变量名、鉴权头和额外请求头；
- 模型、并发数、超时和重试次数；
- `temperature`、token 上限及其字段名；
- 通过 `extra_body` 合并到请求 JSON 顶层的额外字段；
- 翻译、审计、修复和思考模式重审分别覆盖 API 参数。

## 完整流程

1. 从中英文沙盒建立 DSL 字典，并翻译 Query：

   ```bash
   python scripts/build_translation_assets.py
   ```

2. 运行确定性规则与 LLM 联合审计：

   ```bash
   python scripts/audit_phase1_translations.py
   ```

3. 只修复审计策略选中的记录，并再次验证：

   ```bash
   python scripts/repair_phase1_translations.py
   ```

4. 对 LLM 判错项进行保守的两阶段重审，或导出人工检查表：

   ```bash
   python scripts/reaudit_phase1_translations.py
   python scripts/export_phase1_translation_review.py
   ```

5. 应用人工裁决，生成最终数据目录：

   ```bash
   python scripts/apply_phase1_human_adjudication.py
   ```

`repair_translated_dsl.py` 是独立的确定性工具，用于根据中文权威源重建语法无效的
英文 DSL。每个脚本都支持路径覆盖；使用 `--help` 查看具体参数。

## 最小修改原则

审计报告中的可疑项不会自动全部改写。修复流程只选择配置状态、LLM 判定和验证条件
共同满足的记录；保守重审会将无法确定的情况保留为 `manual_review`。所有变更应通过
manifest 或人工裁决报告追踪。
