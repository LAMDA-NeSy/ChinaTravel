# Post-Competition Release Validation / 赛后版本验证

Validation date: 2026-08-18

## Automated Checks

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

- Unit regression tests: 41 passed.
- Translation and audit entrypoints: all `--help` imports passed.
- Example translation configuration: parsed by both translation and audit
  loaders.
- Fixed sandbox ZIP: passed `unzip -t`; archive SHA-256 is recorded outside the
  repository with the distributed artifact.
- The installed English sandbox contains no legacy values in attraction `type`,
  restaurant `cuisine`, or accommodation `featurehoteltype`.
- Runtime concept-label and POI-name alias rewriting is disabled; the current
  Hugging Face sandbox is required.

## Generated Data Audit

The 2,000-record Phase 2 dataset was re-audited after removing runtime sandbox
aliases. The audit used the current canonical English sandbox and current
`next` code:

- records checked: 2,000;
- unique signatures: 2,000;
- constraint coverage: 53 / 53;
- seed-plan DSL and commonsense failures: 0;
- audit errors: 0;
- audit warnings: 0.

## End-to-End Evaluation

Three existing English result sets were evaluated with the current
`eval_tpc.py` implementation.

| Data/results | Records | Mic.EPR | Mac.EPR | C-LPR | FPR | Overall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| UrbanTrip probe | 10 | 100.0000 | 100.0000 | 98.0000 | 90.0000 | 90.4617 |
| UrbanTrip Phase 1 | 1000 | 97.0536 | 93.6000 | 91.9002 | 86.3000 | 86.2740 |
| Seed-plan pseudo results on generated data | 500 | 100.0000 | 100.0000 | 100.0000 | 100.0000 | 96.4178 |

Commands:

```bash
python eval_tpc.py --splits urbantrip_probe10 \
  --method UrbanTrip_probe10_en --lang en

python eval_tpc.py --splits TPC_IJCAI_2026_phase1 \
  --method UrbanTrip_TPCLLM_en_oracletranslation --lang en

python eval_tpc.py --splits urbantrip_timing_500_seedchecked \
  --method SeedPlanPseudoSeedChecked_en --lang en
```

The 500-record seed-plan run is the generator consistency check: every plan
passed schema, commonsense, and generated hard constraints. Its overall score
is below 100 only because DAV, ATT, and DDR are preference metrics rather than
validity checks.

The Phase 1 result folder contained 33 explicit empty itineraries and 28 records
whose `itinerary` was not a list. They were treated as invalid and could not
contribute preference score. Empty itineraries produced caught validator
exceptions in the diagnostic log but did not interrupt evaluation or create a
scoring bypass.

## 中文结论

- 41 项单元回归测试全部通过，所有发布工具均可正常导入。
- 运行时已移除英文概念标签和 POI 名称的历史别名替换，必须使用 Hugging Face 当前
  规范沙盒。
- 使用当前代码和规范沙盒重新审计 2000 条 Phase 2 数据，53 种约束全部覆盖，seed
  plan 的 DSL 与常识检查均通过，错误和警告均为 0。
- UrbanTrip Phase 1 的 1000 条已有结果完成全链路评分，没有中断。
- 其中 33 条为空行程，28 条的 `itinerary` 不是列表；这些结果均按无效处理，不能获得
  偏好分，不构成评分绕过。
- 500 条 seed-checked 合成数据的伪结果在 schema、常识和硬约束上全部通过，说明当前
  生成器、沙盒实体和 evaluator 一致。
- 偏好指标不是有效性判定，即使 FPR 为 100，总分也不一定是 100。
