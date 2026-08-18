# 合成 Query 生成

[English](README.md) | [简体中文](README.zh-CN.md)

该模块从已经有效的 seed plan 中采样新的可执行约束，生成更复杂的 ChinaTravel
Query。生成代码、约束模板和审计工具已公开，但生成后的比赛私有数据不在仓库中。

## 流程

1. 采样仅包含起点、终点、天数和人数的基础 Query；
2. 使用 UrbanTrip 或其他 planner 得到可行 seed plan；
3. 从 plan 中采样一定能被该 plan 满足的 DSL 约束；
4. 使用模板生成对应自然语言；
5. 分别验证每条候选约束和最终约束组合；
6. 写出数据、manifest 和可选的 seed plan 副本；
7. 独立执行数据、DSL、沙盒和覆盖率审计。

每条记录包含标准字段：`uid`、`start_city`、`target_city`、`days`、
`people_number`、`hard_logic_py`、`hard_logic_nl` 和 `nature_language`。
审计版本还包含 `source_plan_uid`、`seed_plan_path` 和 `generation_profile`。

所有示例命令均从仓库根目录执行，并写入已被 Git 忽略的仓库相对目录
`artifacts/`。CLI 也接受调用方显式传入的其他相对或绝对路径，生成器本身不绑定
任何机器专用输出路径。

## 模块结构

| 文件 | 用途 |
| --- | --- |
| `cli.py` | CLI 参数与校验 |
| `pipeline.py` | 生成 API、采样和 manifest |
| `models.py` | 配置与候选约束数据结构 |
| `templates.py` | 中英文模板与标签 |
| `catalog.py` | 约束语义及发布 profile |
| `constraints.py` | 独立注册的约束生成器 |
| `validation.py` | 硬约束和常识验证包装 |
| `audit.py` | 独立数据审计 |
| `export_release.py` | 只包含公开 Query 字段的导出 |
| `release_wording.py` | 幂等的赛后英文表述澄清 |

## 生成基础 Query

```bash
python -m synthetic_query_generation seed-queries \
  --output-dir artifacts/synthetic/seed_queries \
  --num-records 100 \
  --lang en \
  --seed 2026
```

使用 planner 处理这些 Query，并将输出 plan JSON 放到同一结果目录。

## 从 Plan 生成复杂 Query

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir artifacts/synthetic/generated \
  --num-records 100 \
  --lang en \
  --seed 2026 \
  --copy-seed-plans
```

输出结构：

```text
<output-dir>/
  data/<uid>.json
  seed_plans/<uid>.json
  manifest.json
```

查看当前生成器和约束 key：

```bash
python -m synthetic_query_generation list-generators
```

按约束族控制：

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir artifacts/synthetic/budget_only \
  --num-records 20 \
  --only-generators budget,transport \
  --no-or-constraints
```

按模板 key 控制：

```bash
python -m synthetic_query_generation from-plans \
  --plans-dir results/seed_planner \
  --output-dir artifacts/synthetic/subset \
  --num-records 100 \
  --only-constraint-keys trip_days,people_number,total_budget,attraction_time_window \
  --exclude-plan-prefixes synthetic
```

`--exclude-plan-prefixes` 用于避免将合成 plan 递归作为新 seed。也可以通过
`--priority-constraint-keys` 和 `--min-priority-constraints` 控制每条数据中重点
约束的最小数量。

## 当前约束范围

生成器支持行程天数和人数、POI 精确名称、景点/餐馆/酒店类型、房间与票数、
市内交通方式与次数、步行距离、市内交通时长、出租车数量、城际交通方式与时间、
按天 POI 与活动数量、餐次、酒店数量、免费景点、时间窗口、景点时长、同日配对、
跨类别顺序、总预算和分项预算，以及两个有效原子约束组成的 OR 约束。

## 新增约束

在 `templates.py` 中添加自然语言模板和元数据，在 `constraints.py` 中注册独立
generator，并返回 `ConstraintCandidate`。候选约束必须能在 seed plan 上执行且为真，
否则会在进入采样池前被丢弃；最终组合写盘前还会再次验证。

## 语言

```bash
--lang en
--lang zh
--lang auto
```

`auto` 根据 seed plan 城市名称判断语言。实体名称严格保留 seed plan 中的写法。

## 独立审计与发布

```bash
python -m synthetic_query_generation.audit \
  --dataset-dir artifacts/synthetic/generated \
  --expected-records 100 \
  --profile full \
  --lang en
```

审计会检查 schema、重复签名、规范概念值、自然语言顺序、DSL 执行、seed plan
grounding、常识约束和约束覆盖率，并输出 `audit/audit_report.json` 和
`audit/constraint_dsl_catalog.md`。

审计通过后导出只包含公开字段的数据：

```bash
python -m synthetic_query_generation.export_release \
  --dataset-dir artifacts/synthetic/generated \
  --output-dir artifacts/synthetic/generated/release \
  --expected-records 100
```

seed plan、生成元数据和源路径不会进入 release 目录。

完整 Phase 2 数据发布到 Hugging Face 前，使用更严格的 JSONL 导出器：

```bash
PYTHONPATH=. python scripts/export_phase2_hf.py \
  --dataset-dir artifacts/phase2_complete \
  --output artifacts/phase2_hf/phase2.csv \
  --report artifacts/phase2_hf/phase2_audit_report.json \
  --expected-records 2000 \
  --records-per-shard 1000
```

该导出器会明确包含式 OR、人民币单位、市内交通作用范围、按主交通方式统计的
行程次数以及活动必须完整落入时间窗的语义。仅当 OR 的某个原子分支已经作为同一
Query 的独立硬约束出现时，才删除该冗余 OR；这一逻辑恒等变换不会改变可行 plan
集合。新的采样流程会在选约束阶段直接避免此类 OR/原子分支组合。
