# 复核 idle 行为并运行 body-sway 结构探针

本指南面向已经发布 P3 mesh、P5 retarget 和 P9 reviewed-motion bundle 的维护者。目标是从同一条精确输入链生成 idle 行为候选，记录人工决定，再为 `body_sway` 生成 `BodySwayProbeReport v1`。

这三条命令都是只读编译：它们不会发布 bundle、更新 `latest` 或写入 state tree。`--document-only` 只让 stdout 输出 canonical 文档；它不是“通过”开关。

## 1. 固定七个地址

先确认 P3、P5 和 P9 地址已经由各自 verifier 通过，并记录同一来源链上的七个完整 SHA-256：

| 输入 | 命令参数 |
| --- | --- |
| reviewed Layer Manifest | `--layer-manifest-sha256` |
| P3 rig | `--p3-rig-sha256` |
| P3 mesh bundle | `--p3-bundle-sha256` |
| P5 MotionInstance v1 | `--motion-instance-sha256` |
| P5 retarget bundle | `--motion-retarget-bundle-sha256` |
| P9 MotionInstance v2 | `--motion-instance-v2-sha256` |
| P9 reviewed-motion bundle | `--reviewed-motion-bundle-sha256` |

不要使用缩写 SHA、`latest`、目录首项或相邻文件推断。P10 exact loader 会读取 Layer Manifest、P3、P5、P9 四个精确地址，重放 P9，并拒绝交叉链混用。

在仓库根目录准备环境与占位变量；把尖括号内容替换为真实命令输出，不要照抄为地址：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$StateRoot = (Resolve-Path .\workspace).Path
$Project = "<project-id>"

$LayerManifest = "<64-hex-layer-manifest-sha256>"
$P3Rig = "<64-hex-p3-rig-sha256>"
$P3Bundle = "<64-hex-p3-bundle-sha256>"
$P5Instance = "<64-hex-motion-instance-sha256>"
$P5Bundle = "<64-hex-motion-retarget-bundle-sha256>"
$P9InstanceV2 = "<64-hex-motion-instance-v2-sha256>"
$P9Bundle = "<64-hex-reviewed-motion-bundle-sha256>"
```

Windows PowerShell 5 的重定向可能产生 UTF-16。用 UTF-8 no-BOM 保存 canonical stdout，并且总是在写文件前检查退出码：

```powershell
function Write-Utf8NoBom {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Text
  )
  $FullPath = [System.IO.Path]::GetFullPath($Path)
  $ParentPath = [System.IO.Path]::GetDirectoryName($FullPath)
  $null = [System.IO.Directory]::CreateDirectory($ParentPath)
  [System.IO.File]::WriteAllText(
    $FullPath, $Text, [System.Text.UTF8Encoding]::new($false)
  )
}
```

## 2. 编译 P10.0 候选

```powershell
$CandidatesText = (& python -m autospine_workbench compile-idle-behavior-candidates $Project `
  --layer-manifest-sha256 $LayerManifest `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --motion-instance-v2-sha256 $P9InstanceV2 `
  --reviewed-motion-bundle-sha256 $P9Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "idle candidate compile failed" }
Write-Utf8NoBom .\review\idle-behavior-candidates.json $CandidatesText
```

检查 `features` 和 `summary`。当前 v1 总是列出 `blink`、`body_sway`、`hair_spring`、`mouth` 四项：

- `body_sway` 只有在四根 canonical 躯干骨及其 P5 目标映射完整时才是 `candidate`；
- `blink`、`mouth` 缺少独立运行时视觉状态，因此保持 `unobservable`；
- `hair_spring` 依据 setup 证据为 `unobservable` 或 `unsupported`，当前没有独立 hair DOF/physics；
- candidate 只是提议，不包含决定、runtime timeline、生成 raster 或视觉结论。

若 `body_sway.availability` 不是 `candidate`，先修复其 `reason_codes` 指出的 setup/映射问题；不要伪造 `candidate_id`。

## 3. 记录 P10.1 人工决定

不要编辑 candidate 文档。新建 `review/idle-behavior-review-input.json`，其顶层只能包含 `review` 与 `decisions`。当前 `body_sway` 需要人工给出参数，因此没有 `accept`：

- `adjust` 携带参数并保持 `probe_status: pending_probe`；
- `reject` 或 `unobservable` 的 `payload` 必须为 `null`，且 `probe_status` 为 `not_applicable`；
- decision 必须精确复制 candidate 的 `candidate_id`，并穷尽 candidate 行；
- `per_bone_*` 必须按 candidate 的 `proposal.target_bone_ids` 顺序排列。

下面的数字只演示合同形状，不是安全范围或推荐动画参数。复制后必须由人工按角色重填；`0..10` 度只是输入语法包络，不是 mesh、连续时间或视觉安全证据：

```json
{
  "review": {
    "method": "human",
    "status": "completed",
    "revision": 1
  },
  "decisions": [
    {
      "candidate_id": "<copy-exact-body-sway-candidate-id>",
      "feature_id": "body_sway",
      "action": "adjust",
      "reason_code": "human-parameterized",
      "payload": {
        "cycles": 2,
        "per_bone_amplitude_deg": [
          {"bone_id": "pelvis-spine", "value": 1.0},
          {"bone_id": "spine-chest", "value": 1.0},
          {"bone_id": "chest-neck", "value": 0.5},
          {"bone_id": "neck-head", "value": 0.5}
        ],
        "per_bone_phase_fraction": [
          {"bone_id": "pelvis-spine", "value": 0.0},
          {"bone_id": "spine-chest", "value": 0.25},
          {"bone_id": "chest-neck", "value": 0.5},
          {"bone_id": "neck-head", "value": 0.75}
        ]
      },
      "probe_status": "pending_probe"
    }
  ]
}
```

编译与 exact candidate 绑定的 canonical decision：

```powershell
$DecisionText = (& python -m autospine_workbench compile-idle-behavior-decision `
  --candidates .\review\idle-behavior-candidates.json `
  --review-input .\review\idle-behavior-review-input.json `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "idle decision compile failed" }
Write-Utf8NoBom .\review\idle-behavior-decision.json $DecisionText
```

输入链、候选算法或 candidate 字节发生变化后，旧 decision 会因 SHA 绑定过期而失败，不会静默复用。

## 4. 编译 P10.2 body-sway 探针

只有唯一的 `body_sway / adjust / pending_probe` 决定能进入该命令。再次传入同一组七个地址，是为了重放 exact P3/P5/P9 链并重新编译候选；本地 candidate 必须与重编结果的 canonical 字节一致，decision 必须通过 candidate-aware 绑定检查。

```powershell
$ProbeText = (& python -m autospine_workbench compile-body-sway-probe $Project `
  --layer-manifest-sha256 $LayerManifest `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --motion-instance-v2-sha256 $P9InstanceV2 `
  --reviewed-motion-bundle-sha256 $P9Bundle `
  --candidates .\review\idle-behavior-candidates.json `
  --decision .\review\idle-behavior-decision.json `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "body-sway probe compile failed" }
Write-Utf8NoBom .\review\body-sway-probe-report.json $ProbeText
```

不使用 `--document-only` 时，CLI wrapper 的 `status` 是 `completed_diagnostic`，并附带输入路径与三个输出 SHA。它只表示诊断编译完成，不表示 report、动画或发布门禁通过。

## 5. 解读七项 checks

`BodySwayProbeReport v1` 按固定顺序包含七项检查：

| `check_id` | 含义 | 可能的特殊状态 |
| --- | --- | --- |
| `loop_closure` | loop clip 的可见端点 pose 是否闭合 | 非 loop 为 `not_applicable` |
| `fk_finite` | 全部采样 tick、全部 rig bone 的 FK 是否有效 | `passed` / `rejected` |
| `sampled_mesh_deformation` | mesh 的面积比、翻转与边长拉伸采样结果 | 无 mesh 为 `not_applicable` |
| `sampled_canvas_containment` | region/mesh 采样顶点是否留在画布内 | `passed` / `rejected` |
| `shared_index_internal_continuity` | mesh 的共享索引拓扑是否保持内部连续 | 无 mesh 为 `not_applicable` |
| `inter_attachment_seams` | attachment 之间的接缝 | 固定为 `unobservable`，尚无 reviewed seam anchors |
| `visual_quality` | 官方 runtime 中的最终外观 | 固定为 `unobservable`，需要人工 runtime preview |

前五项中的任一可计算结构检查被拒绝时，report 顶层 `status` 为 `structural_rejected`；否则为 `manual_visual_required`。无论哪种情况，`release_gate.status` 都是 `blocked`。修复结构拒绝后仍必须在明确版本的官方 runtime 中人工检查接缝、遮挡、轮廓与观感。

每个可计算 check 的 `failure_count` 是失败采样 tick 数，不是 attachment×tick 事件数。`evidence_sha256` 和 `sample_stream_sha256` 是 compiler seal；报告没有嵌入所有行，因此不能只凭这些摘要哈希独立重放探针。

## 6. 不要用 sample SHA 判断 loop

代表性行的 `sample_sha256` 使用 `autospine-body-sway-representative-sample/v1`，哈希内容包括 `tick`、base/overlay/combined rotations 和 root translation。因此 loop 起点与终点即使 pose 完全相同，其 tick 不同，`sample_sha256` 也应不同。

loop 检查另行计算不含 tick 的 endpoint pose-state SHA（domain 为 `autospine-body-sway-endpoint-pose-state/v1`），比较可见姿势后再封入 `loop_closure.evidence_sha256`。不要把两个 endpoint 的 `sample_sha256` 不相等解读为 loop 失败；以 `checks[].check_id == "loop_closure"` 的状态为准。

## 7. 当前能力边界

P10.2 只对固定离散 schedule 采样 setup-local base motion 与人工 body-sway overlay，再检查结构几何。它明确不：

- 生成 MotionInstance v3、Spine timeline 或可发布动画；
- 证明采样点之间的连续时间安全、输入幅度的安全范围或 attachment 接缝安全；
- 证明 raster truth 或视觉质量；
- 替代明确版本的官方 runtime 加载、人工预览与截图回归。

合同参考：[IdleBehaviorCandidates v1](../schemas/idle-behavior-candidates-v1.schema.json)、[IdleBehaviorDecision v1](../schemas/idle-behavior-decision-v1.schema.json)、[BodySwayProbeReport v1](../schemas/body-sway-probe-report-v1.schema.json)。
