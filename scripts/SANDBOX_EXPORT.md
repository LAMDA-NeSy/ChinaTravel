# Fixed English Sandbox Export / 修复版英文沙盒导出

[English](#english) | [简体中文](#简体中文)

## English

`export_fixed_sandbox.py` creates a new, distributable `database_en` snapshot
with canonical English concept labels. It never edits the source directory.
The examples run from the repository root and write under the Git-ignored,
repository-relative `artifacts/` directory.

```bash
python scripts/export_fixed_sandbox.py artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --archive artifacts/sandbox/ChinaTravel_sandbox_en_fixed.zip
```

Use `--source <database_en>` to export from a non-default source. Both the
output directory and optional archive path must not already exist.

The exporter canonicalizes only these fields:

- attraction `type`;
- restaurant `cuisine`;
- accommodation `featurehoteltype`.

This includes known casing and synonym mismatches such as `cafe` versus
`coffee shop`, `university campus` versus `University campus`, and
`Swimming pool` versus `Swimming Pool`. `Bistro Sola` is handled as a runtime
compatibility alias for the canonical POI name `Sola Bistro`; the static row is
already canonical and is not duplicated.

Output layout:

```text
<release>/
  database_en/
  FIXES.md
  manifest.json
  SHA256SUMS
```

Validation checks that file lists, CSV columns, and row counts are unchanged;
only documented concept fields differ; no configured alias remains; and all
non-target files are byte-identical. The ZIP preserves the release directory
as its root entry.

## 简体中文

`export_fixed_sandbox.py` 会从现有 `database_en` 创建一份可分发的规范化英文沙盒，
不会修改源目录。以下命令从仓库根目录执行，输出写入已被 Git 忽略的仓库相对目录
`artifacts/`。

```bash
python scripts/export_fixed_sandbox.py artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --archive artifacts/sandbox/ChinaTravel_sandbox_en_fixed.zip
```

如果源数据库不在默认位置，可使用 `--source <database_en>`。输出目录和压缩包路径
都必须不存在，避免意外覆盖已有数据。

脚本只规范化三个字段：

- 景点 `type`；
- 餐馆 `cuisine`；
- 酒店 `featurehoteltype`。

修复包括 `cafe`/`coffee shop`、`university campus`/`University campus`、
`Swimming pool`/`Swimming Pool` 等同义或大小写不一致。`Bistro Sola` 在运行时映射为
权威名称 `Sola Bistro`；静态沙盒中该 POI 已经正确，因此不会新增重复行。

导出目录包含数据库、`FIXES.md`、`manifest.json` 和逐文件 `SHA256SUMS`。导出时会
验证文件列表、CSV 列和行数保持不变，只有声明的概念字段发生修改，所有非目标文件
与源文件逐字节一致，并确保没有残留的非规范别名。

## Hugging Face release / Hugging Face 发布包

After producing the fixed English snapshot, `export_hf_sandbox.py` combines it
with the repository's Chinese database into a bilingual Hugging Face dataset
release. The output contains evaluator-compatible raw ZIP archives,
viewer-friendly Parquet configs, checksums, and a dataset card. It does not edit
either source database.

```bash
python scripts/export_hf_sandbox.py artifacts/hf_sandbox_release \
  --english-source artifacts/sandbox/ChinaTravel_sandbox_en_fixed/database_en \
  --english-metadata-dir artifacts/sandbox/ChinaTravel_sandbox_en_fixed \
  --release-version 2026.08
```

Both source directories must have the same relative file layout. The exporter
also verifies canonical English concept labels, equal bilingual table counts,
and Parquet round trips before writing `release_manifest.json`.

生成修复版英文快照后，可使用 `export_hf_sandbox.py` 将其与仓库中的中文数据库
组合成 Hugging Face 双语发布包。输出同时包含兼容测评器目录结构的原始 ZIP、便于
Hub Viewer 浏览的 Parquet config、校验和、数据卡和发布清单；两个源数据库均不会被
修改。脚本会检查中英文文件布局、英文概念标签、双语表行数和 Parquet 回读结果。
