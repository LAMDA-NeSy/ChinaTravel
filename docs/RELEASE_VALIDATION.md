# Post-Competition Release Validation / 赛后版本验证

Validation date: 2026-08-13

## Automated Checks

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q chinatravel agent_env scripts synthetic_query_generation tests
```

- Unit regression tests: 38 passed.
- Translation and audit entrypoints: all `--help` imports passed.
- Example translation configuration: parsed by both translation and audit
  loaders.
- Fixed sandbox ZIP: passed `unzip -t`; archive SHA-256 is recorded outside the
  repository with the distributed artifact.

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

- 38 项单元回归测试全部通过，所有发布工具均可正常导入。
- UrbanTrip Phase 1 的 1000 条已有结果完成全链路评分，没有中断。
- 其中 33 条为空行程，28 条的 `itinerary` 不是列表；这些结果均按无效处理，不能获得
  偏好分，不构成评分绕过。
- 500 条 seed-checked 合成数据的伪结果在 schema、常识和硬约束上全部通过，说明当前
  生成器、沙盒实体和 evaluator 一致。
- 偏好指标不是有效性判定，即使 FPR 为 100，总分也不一定是 100。
