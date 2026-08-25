# 编译并验证 region-only RigIR

本指南用于把一个已复核 revision 固定为 Layer Manifest，编译 P2 region-only RigIR，并运行可复现的 setup probes。它不生成 mesh、权重、IK、动画或 Spine 版本导出。

## 前置条件

- 已在项目目录执行 `$env:PYTHONPATH = (Resolve-Path .\src).Path`。
- See-through audit 与图层 PNG 可从工作区读取。
- 每个需要保留的非空图层都已人工确认语义、角色左右和画布内 pivot；自动目标骨不合适或无法唯一解析时，已显式选择目标骨。
- 需要排除的图层已明确设为 `exclude`。

在工作台的“图层”模式逐层检查字段，然后点击“确认语义、Pivot 与目标骨”，最后保存校正以产生新 revision。按钮会把当前目标骨固定为显式 override；只切换可见性不会确认其他字段。当前版本不会把 `split` 决定物化为多个 region，因此存在 `split` 的项目不能通过 P2 严格门禁。

## 1. 发布固定 Layer Manifest

```powershell
python -m autospine_workbench materialize-manifest seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

保存输出中的 `manifest_sha256`。bundle 位于：

```text
workspace/builds/layer-manifest/<project-id>/<manifest-sha256>/
```

如果 manifest 的 QA 包含 `SEMANTIC_REVIEW_REQUIRED`、`PIVOT_REVIEW_REQUIRED`、`BONE_BINDING_REVIEW_REQUIRED` 或 `SPLIT_NOT_MATERIALIZED`，返回 UI 完成对应复核。其中 `BONE_BINDING_REVIEW_REQUIRED` 表示当前语义无法解析出目标骨。不要把诊断模式当作验收捷径。

## 2. 严格编译

```powershell
python -m autospine_workbench compile-rig seethrough_output `
  --layer-manifest-sha256 <manifest-sha256> `
  --workspace .. `
  --state-root .\workspace
```

成功输出会给出 resolved snapshot、manifest、run manifest、RigIR、probe report 和 bundle 的 SHA。发布目录为：

```text
workspace/builds/<project-id>/rig-ir/<rig-sha256>/<bundle-sha256>/
```

`bundle_sha256` 同时绑定 canonical `rig.json`、`run-manifest.json` 与 `probes.json`。相同输入和算法会复用相同地址；编译器或探针 runner 变化不会静默覆盖旧报告。

## 3. 独立重跑 probes

```powershell
python -m autospine_workbench run-probes seethrough_output `
  --layer-manifest-sha256 <manifest-sha256> `
  --workspace .. `
  --state-root .\workspace `
  .\workspace\builds\seethrough_output\rig-ir\<rig-sha256>\<bundle-sha256>\rig.json
```

必须检查以下项目：

- source identity 与 revision/canvas/override provenance；
- bone parent links 与完整 local FK setup；
- region 到 bone、pivot、blend、opacity 与 draw order 的精确映射；
- setup 像素重建为 exact。

`run-probes` 的退出码为：`0` 通过、`1` 仍需人工复核、`2` 拒绝或输入错误。

## 诊断模式

严格编译因未复核字段失败时，可以临时添加 `--allow-manual-required` 检查编译器和 probes 的其余部分：

```powershell
python -m autospine_workbench compile-rig seethrough_output `
  --layer-manifest-sha256 <manifest-sha256> `
  --allow-manual-required `
  --workspace .. `
  --state-root .\workspace
```

诊断 bundle 会永久记录该开关，并保留 `manual_required` 状态。它适合定位问题，但不满足 P2 的进入 P3 条件。
