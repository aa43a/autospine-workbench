# 编译并验证 region-only RigIR

本指南用于把一个已复核 revision 固定为 Layer Manifest，编译 P2 region-only RigIR，并运行可复现的 setup probes。它不生成 mesh、权重、IK、动画或 Spine 版本导出。

## 前置条件

- 已在项目目录执行 `$env:PYTHONPATH = (Resolve-Path .\src).Path`。
- See-through audit 与图层 PNG 可从工作区读取。
- 每个需要保留的非空图层都已人工确认语义、角色左右和画布内 pivot；自动目标骨不合适或无法唯一解析时，已显式选择目标骨。
- 需要排除的图层已明确设为 `exclude`。

在工作台的“图层”模式逐层检查字段，然后点击“确认语义、Pivot 与目标骨”，最后保存校正以产生新 revision。按钮会把当前目标骨固定为显式 override；只切换可见性不会确认其他字段。对于 bilateral `split` 图层，先发布内容寻址预览，在“切分预览审查”中确认左右子图，再保存 accept/reject 决定。算法或 config 变化会把旧决定标为 stale。

```powershell
python -m autospine_workbench publish-split-previews seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

## 1. 发布固定 Layer Manifest

```powershell
python -m autospine_workbench materialize-manifest seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

保存输出中的 `manifest_sha256`。bundle 位于：

```text
workspace/builds/<project-id>/layer-manifests/<manifest-sha256>/
```

如果 manifest 的 QA 包含 `SEMANTIC_REVIEW_REQUIRED`、`PIVOT_REVIEW_REQUIRED`、`BONE_BINDING_REVIEW_REQUIRED`，或者 generated split child 因缺少 current accept 决定仍为 unreviewed，返回 UI 完成对应复核。预物化 source 上的 `SPLIT_NOT_MATERIALIZED` 不能进入严格 RigIR。其中 `BONE_BINDING_REVIEW_REQUIRED` 表示当前语义无法解析出目标骨。不要把诊断模式当作验收捷径。

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

`bundle_sha256` 同时绑定 canonical `rig.json`、`run-manifest.json`、`probes.json` 与 `setup-render.json`；后者再绑定 renderer、encoder、RGBA 与 exact PNG SHA。相同输入和算法会复用相同地址；编译器、探针 runner 或 setup 实现变化不会静默覆盖旧报告。发布和复用都会验证完整 region inventory 与每个原始 PNG 字节哈希。

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

## 4. 验证固定 setup golden

人工目视批准 `setup.png` 后，把 PNG 与 `autospine-setup-golden` 合同作为普通源文件提交。不要从当前输出自动更新 expected。只读验证命令为：

```powershell
python -m autospine_workbench verify-setup-golden `
  .\workspace\builds\seethrough_output\rig-ir\<rig-sha256>\<bundle-sha256> `
  .\tests\goldens\p2-setup\seethrough_output.approved.json
```

退出码 `0` 为通过，`1` 为合法但视觉/身份不匹配，`2` 为 bundle、golden 或路径不可信。验证器会拒绝即使合成像素不变的被遮挡 region 篡改、透明 RGB 改写与 PNG 重编码。

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
