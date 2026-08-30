# 复核 idle 行为并运行 body-sway 结构探针

本指南面向已经发布 P3 mesh、P5 retarget 和 P9 reviewed-motion bundle 的操作者与维护者。目标是从同一条精确输入链生成 idle 行为候选，记录人工决定，再为 `body_sway` 生成 `BodySwayProbeReport v1` 与零权威的 `BodySwayCanvasAdjustmentCandidates v1`。

普通操作者优先使用 P10.1 设置页和 P10.2 自动结构探针页；CLI 三条命令仍是专业复验流程。P10.1 候选重放与草稿零写入，三个决定按钮还要经过显示项目、动作、决定和后果的二次确认；只有“确认并提交”才会把 decision 追加到 candidate-bound revision history。P10.2 根据当前 head 自动重放并编译确定性报告，同次详情还生成 P10.2a `0/8…8/8` 统一 gain 诊断。两者全程只读，不要求第二次人工批准、选择文件或填写 SHA。`--document-only` 只让 stdout 输出 canonical 文档；它不是“通过”开关。

## 普通操作：不用文件或 SHA

启动工作台后打开：

<http://127.0.0.1:8765/idle-behavior-review.html>

1. 页面只列出已经完成 P9 human adoption、且能由内容身份闭合到 reviewed-motion bundle 的项目/动作。存在唯一或确定性推荐项时会自动选择；同一项目/clip 若有多个合法决定，页面不会按时间或 `latest` 猜测，必须由你选择具体版本。
2. 等待“精确重放完成”。服务冷启动会完整读取并验证 P3/P5/P9；同一服务进程内的后续请求可以复用非权威 exact-chain 缓存，但每次命中仍会读取全部受保护文件字节重算 seal。普通模式不会要求你选择 JSON 或填写 SHA。
3. 查看行为可用性。当前真实样本的 `body_sway` 可形成候选；`blink`、`mouth` 和 `hair_spring` 会按证据显示“不可观测”或“不支持”，页面不会为它们生成假动作。
4. 在角色 composite 上查看四骨 setup 示意，使用播放/暂停和时间轴比较草稿。普通参数只控制循环次数、下躯干摆幅、颈头摆幅和逐节相位延迟；“高级详情”才显示四骨数组与精确身份。
5. 页面给出的低幅值只是 `unvalidated_draft`，用于减少手填数字，不是安全范围、Spine Runtime 结果或视觉批准。拖动时间轴、播放完整一遍或修改参数都不会自动提交。
6. 勾选页面中的人工确认后，点击“保存 P10.1，下一步运行结构探针”“不使用身体摆动”或“当前无法判断”。三者都会先打开二次确认弹窗，逐项列出项目、动作、决定类型和后果。按 Esc、点击遮罩或点击“取消”都会关闭弹窗且不发送 POST、不写 revision。只有点击“确认并提交”才携带显式 intent 与 `explicit_confirmation=true`；服务端会再次重编 P10.0、读取 current history/head，然后以 CAS 追加标准 `human / completed` P10.1 decision。保存参数记录 `adjust / pending_probe`；另外两项分别记录 `reject / not_applicable` 或 `unobservable / not_applicable`，不会进入 P10.2。
7. 成功回执只表示 candidate-bound decision 已记录。`adjust` 仍是 `pending_probe`；点击回执中的“打开 P10.2 自动结构探针”即可把同一 package 交给下一页。它不证明连续时间、动态接缝、官方 Runtime、raster 或发布权。

若提交返回 revision conflict，刷新页面读取 current head 后再次确认。网络结果不确定时不要盲目重复修改：先刷新历史；字节相同的安全重试会复用既有 revision，不同内容不会覆盖已占用的 slot。

进程内 exact-chain cache 只加速 immutable P3/P5/P9 chain 的读取，不缓存候选决定历史、current head 或 CAS。P10.2 详情与 P10.2a 草稿交接另共享一个有界 derived cache；它只在 state root、完整 exact package/address、candidate SHA、current revision/decision SHA 以及 probe/canvas profile SHA 全部相同时复用 report/adjustment/preview。每个请求仍在缓存查找/编译前后执行 exact replay 和 current-head 检查。两类缓存都不落盘、不跨进程、不授予 authority；命中不是人工确认，也不能证明 revision 永远是 current head。服务重启后的冷发现、首次请求或新 key 仍会完整重放并可能较慢。

## 普通操作：P10.2 自动结构探针

打开：

<http://127.0.0.1:8765/body-sway-probe.html>

1. 页面读取所有 P10 package 的**当前** P10.1 head，只在恰好一个 package 为 `adjust / pending_probe` 时自动推荐它；URL 中的 `package_id` 或你在下拉框中的明确选择优先。历史上曾经可探测、但当前已经拒绝或标记不可观测的 revision 不会被静默复用。
2. 服务端自动重放精确 Layer Manifest/P3/P5/P9/P10.0，并读取 candidate-bound 的 exact P10.1 decision。编译前后再次读取 current head；中途出现新 revision 时返回冲突，页面要求重新读取，不把旧报告冒充当前结果。
3. 等待七项检查卡出现。页面把 loop、FK、mesh、画布和共享索引列为自动结构项，把 attachment 接缝与 Runtime 视觉列为后续门禁；默认界面不显示 SHA，也不要求逐项批准。
4. 使用角色合成图、四骨时间轴和有界采样见证查看结果。见证只是帮助理解 canonical report 的离散采样投影，不穷尽全部 tick，也不替代七项报告。
5. 若结果为“结构拒绝”，先查看 P10.2a 的统一 gain 诊断。`0/8` 只用于判断不加 body-sway 时是否仍越界，不能被保存为 body-sway 参数。若存在一个**非零**且 sampled canvas/geometry 同时通过的 `unvalidated_draft`，可把它带回 P10.1；仍须由你明确确认并保存新 revision，再回本页重跑 P10.2。若没有这种候选，应修复画布、attachment/骨绑定或上游动作，不能靠页面自动批准。若结果为“需要 Runtime 视觉复核”，也只表示前五项 sampled structural checks 未拒绝，下一步仍须准备官方 Spine Runtime capture 和 P10.3 人工视觉证据。

P10.2 页面加载、切换项目、拖动时间轴和下载技术备份均为零写入。报告下载文件名包含项目、clip 和报告哈希前缀，以免两份样本互相覆盖；正常工作流不依赖该下载。无论结构结果为何，`release_gate` 都保持 `blocked`。

真实样本 B `seethrough_output_5` 是“不能只调小幅度”的实例：reviewed gain `8/8` 有 `334/334` 个画布失败 tick，`0/8` 仍有 `333/334` 个，主要涉及 `layer-006-objects`、`layer-000-back-hair` 与 `layer-008-hand-r`。该样本没有可用的纯参数 draft，当前必须保持 P10.3 fail closed。

## 专业流程：显式七地址与 canonical JSON

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

当前 P10.2a 候选由自动 package 详情与 P10.2 页面在同次重放中提供；它不是另一条人工批准命令，也不会由 `compile-body-sway-probe` 自动发布 P10.1 revision。专业复验仍以 canonical P10.2 report 为准，任何 P10.2a draft 都必须回到 P10.1 显式确认后再运行本命令。

## 5. 解读七项 checks

`BodySwayProbeReport v1` 按固定顺序包含七项检查：

| `check_id` | 含义 | 可能的特殊状态 |
| --- | --- | --- |
| `loop_closure` | loop clip 的可见端点 pose 是否闭合 | 非 loop 为 `not_applicable` |
| `fk_finite` | 全部采样 tick、全部 rig bone 的 FK 是否有效 | `passed` / `rejected` |
| `sampled_mesh_deformation` | mesh 的面积比、翻转与边长拉伸采样结果 | 无 mesh 为 `not_applicable` |
| `sampled_canvas_containment` | region/mesh 采样顶点是否留在画布内 | `passed` / `rejected` |
| `shared_index_internal_continuity` | mesh 的共享索引拓扑是否保持内部连续 | 无 mesh 为 `not_applicable` |
| `inter_attachment_seams` | attachment 之间的接缝 | 固定为 `unobservable`；P10.2 合同不消费或验证 P10.5c reviewed anchors，即使项目已有静态锚点也不据此推断动态接缝 |
| `visual_quality` | 官方 runtime 中的最终外观 | 固定为 `unobservable`，需要人工 runtime preview |

前五项中的任一可计算结构检查被拒绝时，report 顶层 `status` 为 `structural_rejected`；否则为 `manual_visual_required`。无论哪种情况，`release_gate.status` 都是 `blocked`。修复结构拒绝后仍必须在明确版本的官方 runtime 中人工检查接缝、遮挡、轮廓与观感。

每个可计算 check 的 `failure_count` 是失败采样 tick 数，不是 attachment×tick 事件数。`evidence_sha256` 和 `sample_stream_sha256` 是 compiler seal；报告没有嵌入所有行，因此不能只凭这些摘要哈希独立重放探针。

## 6. 解读 P10.2a 画布调整候选

`BodySwayCanvasAdjustmentCandidates v1` 在不改变周期、相位和上游 base motion 的前提下，把已复核四骨幅度统一乘以离散 gain `0/8…8/8`，并在同一 schedule 上比较两类结果：

- sampled canvas 是否通过；
- sampled geometry 是否通过。

整个文档是 `candidate_only` 的零权威诊断。固定网格只回答九个离散点，不证明相邻点、连续时间或 Runtime 安全。`0/8` 即使通过，也不能代表一个 body-sway 动作；只有非零点的两类检查都通过，才可能出现 `unvalidated_draft`。该 draft 只能减少重新输入参数的工作量，不能跳过 P10.1 二次确认、current-head CAS 或新一轮 P10.2。

若 `0/8` 也失败，应优先检查基础动作、画布余量、attachment 的 setup rectangle/mesh、目标骨和绑定方向。此时继续减小 body-sway 幅度没有意义；必须修复这些结构输入。

## 7. 不要用 sample SHA 判断 loop

代表性行的 `sample_sha256` 使用 `autospine-body-sway-representative-sample/v1`，哈希内容包括 `tick`、base/overlay/combined rotations 和 root translation。因此 loop 起点与终点即使 pose 完全相同，其 tick 不同，`sample_sha256` 也应不同。

loop 检查另行计算不含 tick 的 endpoint pose-state SHA（domain 为 `autospine-body-sway-endpoint-pose-state/v1`），比较可见姿势后再封入 `loop_closure.evidence_sha256`。不要把两个 endpoint 的 `sample_sha256` 不相等解读为 loop 失败；以 `checks[].check_id == "loop_closure"` 的状态为准。

## 8. 当前能力边界

P10.2 只对固定离散 schedule 采样 setup-local base motion 与人工 body-sway overlay，再检查结构几何；P10.2a 只在同一离散 schedule 上比较统一 gain。它们明确不：

- 生成 MotionInstance v3、Spine timeline 或可发布动画；
- 证明采样点之间的连续时间安全、输入幅度的安全范围或 attachment 接缝安全；
- 证明 raster truth 或视觉质量；
- 替代明确版本的官方 runtime 加载、人工预览与截图回归。

当前 P10.3 视觉页仍要求精确 project/preview/bundle/artifact 地址。未来可规划从 `package_id` 自动闭合七个 SHA、生成 temporary preview、在操作者显式确认 Runtime 许可与本次启动后异步 capture，并自动带入 exact 地址；这条 package-centric 自动编排尚未实现，也不能绕过逐 case 视觉确认。

合同参考：[IdleBehaviorCandidates v1](../schemas/idle-behavior-candidates-v1.schema.json)、[IdleBehaviorDecision v1](../schemas/idle-behavior-decision-v1.schema.json)、[BodySwayProbeReport v1](../schemas/body-sway-probe-report-v1.schema.json)、[BodySwayCanvasAdjustmentCandidates v1](../schemas/body-sway-canvas-adjustment-candidates-v1.schema.json)。
