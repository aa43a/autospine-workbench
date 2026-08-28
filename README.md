# AutoSpine Workbench

AutoSpine Workbench 是一个本地人工复核与离线编译工作流，用于查看 See-through PSD 审计结果、校正图层语义和 setup 可见性、调整启发式关节，并保存带 revision 的 override。它不会修改 PSD、审计 JSON 或 PNG；主 authoring 页面写入 `workspace/overrides`，P10 人工复核使用各自独立的 revision namespace，离线 publish/compile 命令按阶段写入内容寻址的 analysis、motion、build 或 runtime 工件。

当前阶段是 **P10.7c-setup-regression**：独立的 P6 setup golden 只读对照机制已经交付，但当前目标仍是把“模型输出”变成可追溯、可复核的 authoring 输入，而不是直接宣称生成了可发布的 Spine 资产。

当前功能及入口以[功能与入口参考](docs/capability-reference.md)为准；尚未实现的能力、依赖和验收顺序见[后续开发路线](docs/development-roadmap.md)。

## 能做什么

- 从 `<workspace>/tmp/psd_audit/results/*/audit.json` 发现项目。
- 在统一画布坐标中查看参考合成图、独立图层与骨架覆盖。
- 检查空图层、未分类语义、低置信度关节和合成差异等 QA 信息。
- 覆盖图层语义、角色左右、setup 可见性、pivot 与 region 目标骨，并逐字段确认人工复核。
- 拖动或精确输入关节坐标，并恢复自动推断位置。
- 使用 optimistic concurrency 保存 override；过期 revision 不会覆盖新结果。
- 每次成功保存都写入 append-only revision 历史，并生成应用人工决定后的 resolved snapshot。
- 以独立 `Resolved Project v1` JSON Schema 和无第三方依赖的严格语义 validator 校验 snapshot 的内容哈希、候选/拆分 provenance、实体交叉引用与派生 QA；既有 r5/r7 历史哈希保持不变。
- 在界面加载内容寻址候选，比较画布标记、alpha 中轴线/接触证据，并记录 accept/adjust/reject/unobservable 决定。
- 候选决定绑定完整内容 SHA；算法输出变化不会把旧决定静默套用到新工件。
- 通过只读验证 API 检查画布、图层 ID、资产路径和骨架结构。
- 离线发布带 provenance 的关节候选、region-first Layer Manifest 与 region-only RigIR bundle。
- 把固定的 COCO17 检测转换为显式左右/镜像 provenance 的 canonical pose，并用人工复核四肢点生成诊断误差报告。
- 对 RigIR 执行跨引用、拓扑、权重、三角形及 timeline 语义验证；不支持特性会明确失败。
- 从精确 P3 bundle 编译四个 canonical 两骨 IK 手柄，固定弯曲方向、可达环和 setup-local 数值探针。
- 编译可复用的 setup-local MotionIR（内建 idle/wave 或显式映射 BVH），并从精确 P3/P4/Motion 地址生成带接触、运动学与 mesh 回归证据的不可变 MotionInstance bundle。
- 以 compiler 1.1.0 严格读取 Kimodo 双根 SOMA77 BVH，并让同一 MotionIR 穿过三 rig 与 Spine 4.2 bundle 兼容性门禁。
- 严格读取 Kimodo SOMA77 NPZ、独立 source sidecar 与显式 map，交叉验证矩阵 FK/关节位置，并发布可重建的五文件 MotionIR bundle。
- 从精确 P7 bundle 与显式静态正交相机生成保留深度、透视缩短和可观测性的 ProjectedMotionIR；候选尺度探针可复用于不同目标 rig，但不会静默生成 runtime scale 或 draw-order timeline。
- 从精确 P3/P5/P8 地址编译 foot-lock 和 depth-order 候选，经完整人工决定生成 reviewed policy、MotionInstance v2、Spine 4.2 v2 preview 与六文件不可变 P9 bundle；既有 v1 内容哈希不变。
- 从精确 Layer Manifest/P3/P5/P9 链编译 idle 行为候选和人工决定，并对调整后的 `body_sway` 生成七项采样结构检查；报告始终阻塞发布并要求官方 runtime 人工预览。
- 用操作者提供且已授权的官方 Spine 4.2.119 runtime 捕获固定 body-sway case，再通过精确四段地址在独立 UI/CLI/API 中逐帧复核，并以 CAS 追加不可变 revision；sampled approval 不会解除发布门禁。
- 把 P10.3c 当前 `sampled_visual_approved` head 以双快照只读重放为 `BodySwayReviewAdmission v1`，供后续安全分析使用；合同明确不授予永久 head authority 或发布权。
- 沿已复核四骨幅度向量的统一 gain 射线生成九个离散候选，并以有界区间细分覆盖每一对 sampled-linear preview key；只能授予预览数学模型的结构 claim，runtime、视觉范围、接缝和发布权仍保持阻塞。
- 从精确 Layer Manifest/P3 静态链编译六条四肢 attachment 接缝关系，输出 region/mesh locator 候选与完整算法 profile；只供人工比较，不自动选择锚点。
- 把完整 P10.4b2 proof 与精确 P10.5c bundle 接入双层 current-head 检查，在全部相邻 tick 和统一 gain 上证明 reviewed-anchor point 的 `4 px²` 工程距离代理；attachment 边界、raster/视觉、runtime 与发布仍保持阻塞。
- 把认证的 P10.5d probe 与其内嵌精确 P9 bundle 重新闭合为 P10.6a 版本中立 setup-local timeline 消费准入，并在纯编译前后重查视觉与接缝 current head；它不发出 MotionInstance v3 或 Spine timeline。
- 将完整 P10.6a 成功 wrapper 编译为 MotionInstance v3：只允许躯干四骨 rotation 覆盖，逐值保留 MIv2 root/marker/draw-order，并在发布前重查 current heads；三文件 bundle 可按 v3/bundle 双 SHA 历史复验，但不授予永久审批或 Spine 发布权。
- 从精确 MotionInstance v3 双 SHA 重放 P9/P5/P3 和源 PNG，用独立 Spine 4.2 adapter v3 发布 JSON/atlas/PNG/run/report 五文件 bundle；compile/store 重查 current heads，历史 verify 不读取 current heads，且 run 只授予 adapter emitted。
- 用操作者明确确认有权使用的官方 Spine Player 4.2.119，对精确 P10.7a bundle 执行固定 case、完整 setup attachment isolate 的捕获和 sampled raster 指标；证据可按双 SHA 复验，并可编译逐 case、逐 attachment 的人工决定，但不会授予连续时间、永久 head、发布或 release authority。
- 用 strict canonical 请求只读审计两份真实样本从精确 Manifest/P3 到 P10.7b 的八个 checkpoint；readiness v1 已冻结，第八项仍固定为 missing。审计不扫描 `latest` 或 current review head，不自动运行外部阶段、官方 Runtime、发布或写入，也不代替人审。
- 用独立的 P10.7c 命令把精确 P10.7b capture 中唯一的 opaque setup 帧与既有 P6 官方 Runtime approved golden 做零写入 RGBA 对照；命令不启动 Runtime、不修改批准图，也不授予发布权。
- 从精确 P3 或 P3/P5 地址导出、发布并重建验证固定 profile 的 Spine 4.2 JSON/atlas/PNG 五文件 bundle。

## 快速启动

要求 Windows PowerShell 与 Python 3.11 或更高版本。服务本身只使用 Python 标准库。

在 `autospine-workbench` 目录运行：

```powershell
.\run.ps1
```

脚本按以下顺序寻找 Python：

1. `-PythonExe` 参数；
2. `AUTOSPINE_PYTHON` 环境变量；
3. Codex bundled Python；
4. 系统 `python`；
5. Windows `py -3` launcher。

启动后建议先打开[功能入口中心](http://127.0.0.1:8765/workflow-hub.html)。它可以搜索和筛选全部 Web/CLI/规划入口；CLI 卡片只复制 `python -B -m autospine_workbench <command> --help` 帮助命令，不会让浏览器或服务端直接执行。源码模式下应先在当前 PowerShell 设置 `$env:PYTHONPATH = (Resolve-Path .\src).Path`。卡片中的仓库文档通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开；查看器只读获取 `/docs/<文件名>.md`，并按纯文本显示，不解析其中的 HTML。主绑定复核页面仍是 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。默认配置为：

- workspace：工作台目录的父目录；
- state root：`autospine-workbench/workspace`；
- web root：`autospine-workbench/web`；
- 监听地址：`127.0.0.1:8765`。

覆盖默认值：

```powershell
.\run.ps1 `
  -PythonExe "C:\Python312\python.exe" `
  -WorkspaceRoot "E:\proj\unusual\localset" `
  -StateRoot "E:\autospine-state" `
  -ListenHost "127.0.0.1" `
  -Port 9000
```

也可绕过脚本直接启动：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m autospine_workbench serve `
  --host 127.0.0.1 `
  --port 8765 `
  --workspace .. `
  --state-root .\workspace `
  --web-root .\web
```

服务拒绝绑定 `0.0.0.0` 或非 loopback 地址。它没有用户认证，不应通过反向代理、端口转发或防火墙规则暴露到局域网或公网。

## 输入目录

每个 audit 项目至少应包含：

```text
<workspace>/tmp/psd_audit/results/<project-id>/
├── audit.json
├── composite.png
├── embedded_composite.png
├── layers_contact_sheet.png
└── layers/
    └── *.png
```

文件名由 audit 字段提供，但后端只允许解析到该项目目录内的图片文件。audit 中的绝对路径、`..`、任意 URL 路径或未知 asset kind 都不能被用来读取工作区外文件。

若没有上述目录，服务仍可启动，但项目列表为空。

## 界面操作

本节说明默认的图层/关节 authoring 页面。所有入口可从[功能入口中心](http://127.0.0.1:8765/workflow-hub.html)打开。P10.3c 使用独立的 [Body-sway 视觉复核台](http://127.0.0.1:8765/body-sway-review.html)，P10.5b 使用独立的 [Seam Anchor 复核台](http://127.0.0.1:8765/seam-anchor-review.html)；两者都要求手工输入精确地址，不会继承当前项目或自动选择最新证据。逐帧流程见[复核 body-sway 官方 runtime 采样帧](docs/how-to-review-body-sway-runtime.md)和[复核静态接缝锚点](docs/how-to-review-seam-anchors.md)。

1. 在顶部选择项目。切换项目前若存在未保存修改，界面会要求确认。
2. 在“图层”模式搜索、选择、显示或隐藏图层；右侧可检查语义、角色左右、bbox、置信度和 QA。要让图层进入 P2 严格编译，还需设置画布内 pivot、选择目标骨，并点击“确认语义、Pivot 与目标骨”。
3. 在“关节”模式选择关节；若已发布候选，右侧“候选审查”会列出 artifact、候选方法、可观测性，并为带引用的候选显示固定几何证据。
4. 候选可接受、按当前坐标调整或拒绝；无可靠候选时可把当前关节标记为不可观测。adjust/reject/unobservable 必须填写理由；手工拖动会把该关节转为绝对人工坐标。
5. 使用参考图、骨骼、候选/几何覆盖、预览透明度和缩放控件比较 setup 状态。
6. 填写校正备注后点击“保存校正”，或按 `Ctrl+S`。

快捷键：

- 方向键：将所选关节移动 1 px；
- `Shift` + 方向键：移动 10 px；
- `Alt` + 方向键：移动 0.1 px；
- `0`：适配画布；
- `+` / `-`：缩放；
- `Ctrl+S`：保存。

保存时客户端发送当前 `base_revision`。如果另一会话已经保存，服务返回 HTTP `409 revision_conflict`；重新加载项目、复核新的 override，再重新应用修改。服务不会用 last-write-wins 静默覆盖。

保存开始后产生的新编辑不会被已完成请求清空。遇到 `409` 时，界面保留本地 draft，可先导出，再加载服务端最新 revision 并重放本地修改。

## Override 请求合同

`PUT /api/projects/{project_id}/overrides` 的 canonical 请求固定为：

```json
{
  "schema_version": "autospine-workbench.override/v3",
  "base_revision": 0,
  "joint_overrides": {
    "shoulder.left": {
      "x": 320.5,
      "y": 410.25,
      "confidence": 1.0,
      "reason": "reviewed against arm overlap"
    }
  },
  "joint_decisions": {
    "elbow.left": {
      "action": "accept",
      "candidate_artifact_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "candidate_id": "elbow.left.fusion.4aa35df3ca21"
    }
  },
  "split_decisions": {
    "layer-012-sleeves": {
      "action": "accept",
      "split_artifact_sha256": "89abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234567"
    }
  },
  "layer_overrides": {
    "layer-008-hand-r": {
      "canonical_role": "body.hand",
      "side": "right",
      "disposition": "keep",
      "pivot_xy": [455.0, 620.0],
      "visible": true,
      "notes": "角色自身右侧"
    }
  },
  "notes": "first review pass"
}
```

`joint_overrides` 是与候选算法无关的绝对人工坐标；`joint_decisions` 表示 accept、adjust、reject 或 unobservable，同一关节不能同时出现在两者中。accept 坐标由服务端从内容寻址候选工件派生，客户端不能提交。`split_decisions` 只接受 `accept`/`reject` 和完整 split artifact SHA；服务端会绑定算法、operation config、review target 与 current/stale 状态。`side` 使用 `left`、`right`、`center`、`bilateral` 或 `unknown`，始终表示角色自身左右。`visible` 只定义 setup/复核预览可见性，不会改写 PNG。关节与 pivot 必须是有限数，并位于画布内。完整语义见 [候选关节与切分决定参考](docs/candidate-decisions-reference.md)。

JSON Schema 位于：

- `schemas/override-patch-v3.schema.json`：当前在线 API 的 candidate/split-aware canonical patch；v1/v2 仅用于历史兼容，不能携带 split decision；
- `schemas/resolved-project-v1.schema.json`：resolved authoring snapshot 的严格结构、provenance、候选/拆分决定、派生 QA 与 canonical 内容地址；完整语义仍须经过 Python validator；
- `schemas/coco17-detections-v1.schema.json`：模型 runner 与通用四肢 adapter 的固定输入；
- `schemas/pose-observations-v1.schema.json`：外部姿态检测器的单角色、原画布观测输入；
- `schemas/pose-observations-v2.schema.json`：带 adapter、左右、视角和镜像 provenance 的 canonical pose；
- `schemas/pose-evaluation-v1.schema.json`：人工复核四肢点的阈值无关诊断报告；
- `schemas/joint-candidates-v1.schema.json`：可复现的关节候选、证据分数和来源；
- `schemas/alpha-geometry-evidence-v1.schema.json`：内容寻址的 layer component、alpha path/contact 与可观测性证据；
- `schemas/layer-manifest-v1.schema.json`：规范化 RGBA 图层与语义、offset、QA 的 authoring 合同；
- `schemas/rig-ir-v1.schema.json`：版本中立的骨骼、slot、attachment 与有限动画合同；
- `schemas/rig-compile-run-v1.schema.json`：一次确定性 region RigIR 编译的输入与编译器身份；
- `schemas/rig-setup-probes-v1.schema.json`：FK、pivot、父子关系、draw order 与像素重建探针报告；
- `schemas/rig-setup-render-v1.schema.json`：canonical setup PNG 的 renderer、encoder、RGBA 与 PNG 身份；
- `schemas/setup-golden-v1.schema.json`：经人工批准、只读验证的 setup 视觉 golden 合同；
- `schemas/mesh-*.schema.json` 与 `schemas/ik-target-*.schema.json`：P3 两骨 LBS 和 P4 离线 IK 的 run、probe 与视觉证据；
- `schemas/motion-ir-v1.schema.json`、`schemas/motion-instance-v1.schema.json` 与 `schemas/motion-target-profile-v1.schema.json`：P5 可复用动作、目标 rig 与烘焙实例合同；
- `schemas/motion-compile-run-v1.schema.json`、`schemas/bvh-*.schema.json` 与 `schemas/retarget-run-v1.schema.json`：内建/BVH 编译和重定向 provenance；
- `schemas/kimodo-npz-source-v1.schema.json`、`schemas/kimodo-npz-map-v1.schema.json` 与 `schemas/kimodo-npz-motion-compile-run-v1.schema.json`：正式 P7 原始 NPZ 解释、投影映射与可重建编译 provenance；
- `schemas/camera-model-v1.schema.json`、`schemas/projected-motion-ir-v1.schema.json`、`schemas/projected-motion-compile-run-v1.schema.json` 与 `schemas/projected-scale-probes-v1.schema.json`：P8 相机、3D→2D 投影证据、编译 provenance 与目标 rig 候选尺度探针；
- `schemas/motion-instance-v2.schema.json`、`schemas/motion-policy-decision-v1.schema.json`、`schemas/reviewed-motion-policy-v1.schema.json` 与 `schemas/reviewed-motion-bundle-run-v1.schema.json`：P9 人工决定、root/draw-order overlay、v2 instance 与六文件 bundle provenance；
- `schemas/idle-behavior-candidates-v1.schema.json`、`schemas/idle-behavior-decision-v1.schema.json` 与 `schemas/body-sway-probe-report-v1.schema.json`：P10.0–P10.2 idle 候选、人工参数决定与只读采样结构诊断；
- `schemas/body-sway-runtime-capture-v1.schema.json`、`schemas/body-sway-visual-review-*.schema.json`、`schemas/body-sway-review-admission-v1.schema.json`、`schemas/body-sway-amplitude-envelope-candidate-v1.schema.json` 与 `schemas/body-sway-continuous-preview-proof-v1.schema.json`：P10.3 runtime 证据、sampled visual revision、P10.4a 当前审批头准入、P10.4b1 离散幅度候选与 P10.4b2 连续预览模型证明；
- `schemas/seam-anchor-candidates-v1.schema.json`、`schemas/seam-anchor-review-decision-v1.schema.json`、`schemas/reviewed-seam-anchor-set-v1.schema.json` 与 `schemas/body-sway-dynamic-seam-probe-v1.schema.json`：P10.5a 六条静态接缝候选、P10.5b 候选/P3 绑定的人工 revision、P10.5c 固定六关系的已复核静态锚点集，以及 P10.5d 动态 reviewed-anchor proximity 工程代理；
- `schemas/body-sway-motion-consumer-admission-v1.schema.json`：P10.6a 完整 P10.5d/P9 source closure、unit-gain setup-local motion domain 与 compile-time 双 head seal；
- `schemas/motion-instance-v3.schema.json` 与 `schemas/motion-instance-v3-bundle-run-v1.schema.json`：P10.6b setup-local timeline、三文件 bundle provenance、能力边界与固定 blocked release gate；
- `schemas/spine42-v3-export-run-v1.schema.json` 与 `schemas/spine42-v3-export-report-v1.schema.json`：P10.7a 五文件 adapter bundle 的精确 P3/MIv3 来源、输出身份、能力边界与固定 blocked release gate；
- `schemas/spine42-v3-readiness-request-v1.schema.json` 与 `schemas/spine42-v3-readiness-report-v1.schema.json`：冻结的 P10.7b-readiness exact-address 预检合同；其第八项保持 `p6_setup_golden_comparison_not_declared`；
- `schemas/spine42-v3-setup-regression-request-v1.schema.json` 与 `schemas/spine42-v3-setup-regression-report-v1.schema.json`：独立 P10.7c P3/P6/P10.7a/capture/approved-golden 来源闭合、冻结 comparison profile、RGBA 指标与 path-free 内容身份；
- `schemas/motion-retarget-report-v1.schema.json` 与 `schemas/motion-mesh-regression-v1.schema.json`：P5 运动学、接触与逐帧 mesh 安全门禁。

Layer Manifest 与 RigIR 是下游流水线合同。当前 UI 负责逐层 authoring 与复核，离线命令负责生成 region-only RigIR；它不包含 mesh、权重或动画，也不会冒充某一 Spine 版本。RigIR 对不支持特性的策略固定为 `fail`，防止 constraint、mesh 或 timeline 被静默丢弃。

## 离线工件命令

先让源码包可被当前 PowerShell 会话发现：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

为项目发布审计启发式候选集：

```powershell
python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

把已固定的 COCO17 模型输出转换为 canonical pose v2：

```powershell
python -m autospine_workbench import-pose seethrough_output `
  .\inputs\seethrough_output.coco17.json `
  --workspace .. `
  --state-root .\workspace `
  --side-mapping as_reported `
  --view-orientation front `
  --mirror-state not_mirrored
```

已有规范化姿态观测时，可运行 pose + alpha 连通域软约束：

```powershell
python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace `
  --provider pose-alpha `
  --pose-observations .\inputs\seethrough_output.pose.json `
  --alpha-threshold 8
```

需要同时发布可回看的中轴线/接触证据时，改用 `pose-geometry`。命令会先校验三份文档，再按 pose → geometry → candidates 的 provenance 顺序发布：

```powershell
python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace `
  --provider pose-geometry `
  --pose-observations .\inputs\seethrough_output.pose.json `
  --alpha-threshold 8
```

每个 artifact 都由现有存储原子写入；若某一步发布失败，已发布的上游不可变 artifact 可复用，但不会继续发布下游。这是 provenance-safe 顺序，不是跨三个目录的事务。

用当前人工复核关节生成诊断误差报告：

```powershell
python -m autospine_workbench evaluate-pose seethrough_output `
  .\workspace\analysis\seethrough_output\pose-observations\<sha256>.json `
  --workspace .. `
  --state-root .\workspace
```

COCO17 准备、导入、融合和评估步骤见 [导入并评估 COCO17 四肢姿态](docs/how-to-import-and-evaluate-pose.md)；已有 canonical 输入、`pose-geometry` 和诊断样本发布见 [生成并复核四肢候选](docs/how-to-run-pose-alpha.md)；只读 artifact/API 合同见 [分析工件参考](docs/analysis-artifacts-reference.md)。

从当前已复核 revision 发布不可变的 region attachment bundle：

```powershell
python -m autospine_workbench materialize-manifest seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

若 bilateral 图层尚未绑定当前算法预览，先发布预览，在 UI 的“切分预览审查”中逐项接受或拒绝并保存，再重跑命令。算法版本、策略、实际组件面积、两种 assignment cost 与 margin 都进入 operation config/hash；旧算法决定会变为 stale，不能静默复用：

```powershell
python -m autospine_workbench publish-split-previews seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

把命令返回的 `manifest_sha256` 固定为输入，执行 P2 严格编译与 setup probes：

```powershell
python -m autospine_workbench compile-rig seethrough_output `
  --layer-manifest-sha256 <manifest-sha256> `
  --workspace .. `
  --state-root .\workspace
```

严格编译只接受已复核输入。排障时可加 `--allow-manual-required` 生成诊断 bundle；该开关会写入 run manifest，且探针状态仍为 `manual_required`，不能作为阶段验收。也可对一个固定 `rig.json` 独立重跑探针：

```powershell
python -m autospine_workbench run-probes seethrough_output `
  --layer-manifest-sha256 <manifest-sha256> `
  --workspace .. `
  --state-root .\workspace `
  .\workspace\builds\seethrough_output\rig-ir\<rig-sha256>\<bundle-sha256>\rig.json
```

严格 bundle 同时发布 `setup.png` 与 `setup-render.json`。人工批准代表性 setup 后，用只读 golden 门禁验证完整 bundle；验证器也会检查被遮挡 region、透明 RGB、原始 PNG 字节 SHA 与严格目录 inventory，而不只比较最终合成画面：

```powershell
python -m autospine_workbench verify-setup-golden `
  .\workspace\builds\seethrough_output\rig-ir\<rig-sha256>\<bundle-sha256> `
  .\tests\goldens\p2-setup\seethrough_output.approved.json
```

退出码 `0` 表示完全匹配，`1` 表示 bundle 与合法 golden 不同，`2` 表示 bundle、合同或输入不可信。命令不会自动更新 golden。

逐层复核、严格/诊断模式、退出码与 bundle 校验步骤见 [编译并验证 region-only RigIR](docs/how-to-compile-region-rig.md)。

在一个已验证的 P2 双 SHA 地址上编译、发布并完整读回 P3 两骨 mesh bundle：

```powershell
python -m autospine_workbench compile-mesh-rig seethrough_output `
  --base-rig-sha256 <p2-rig-sha256> `
  --base-bundle-sha256 <p2-bundle-sha256> `
  --state-root .\workspace
```

命令输出并固定 P2 rig/bundle、Layer Manifest、resolved snapshot 以及 P3 rig、run、probes、visuals、bundle 共 9 个 SHA-256。随后可只读重验这个精确地址：

```powershell
python -m autospine_workbench verify-mesh-bundle seethrough_output `
  --rig-sha256 <p3-rig-sha256> `
  --bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace
```

两个命令都不接受 `latest`。验证器会重编译精确 P2 输入、重跑权重/拓扑/动作探针和视觉渲染，并逐字节比较 canonical JSON 与 PNG；任何 identity 漂移、目录别名、链接、额外文件或非有限数都会 fail closed。工作台底部的“P3 Mesh 证据”只负责发现不可变地址，必须由用户依次选择 rig SHA、bundle SHA 并点击读取，才会显示相同的严格验证结果。

从一个已验证的 P3 双 SHA 地址编译四肢两骨 IK 目标、发布不可变 P4 bundle，并严格读回：

```powershell
python -m autospine_workbench compile-ik-targets seethrough_output `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace
```

命令固定完整的 9 项 P3 来源身份，以及 P4 profile、probes、bundle 三个 SHA-256。随后只读重验精确 P4 地址：

```powershell
python -m autospine_workbench verify-ik-bundle seethrough_output `
  --profile-sha256 <p4-profile-sha256> `
  --bundle-sha256 <p4-bundle-sha256> `
  --state-root .\workspace
```

P4 不接受 `latest` 或自动发现。严格 reader 会从精确 P3 来源重建 profile 与全部数值探针并逐字节比较。`kinematic_reach` 只表示两段骨长决定的运动学可达环；它不能覆盖 P3 动作探针给出的 mesh 视觉安全角。完整步骤和错误解释见 [编译并验证两骨 IK 目标](docs/how-to-compile-ik-targets.md)。

P5 将动作与目标 rig 分开内容寻址。内建 `idle`/`wave.left`、显式 BVH map、正式 Kimodo NPZ、目标重定向及只读复验分别使用 `compile-builtin-motion`、`compile-bvh-motion`、`compile-kimodo-motion`、`compile-motion-retarget` 与对应 verify 命令。所有命令只接受精确 SHA，不解析 `latest`；通用合同、固定地址、A/B 示例和排障步骤见 [编译、重定向并复验 P5 动画](docs/how-to-compile-motion.md)，Kimodo 的三输入边界见 [编译 Kimodo SOMA77 NPZ](docs/how-to-compile-kimodo-npz.md)。

正式 Kimodo NPZ bundle 可用以下入口发布与只读复验；编译命令不会搜索相邻 sidecar 或 map：

```powershell
python -m autospine_workbench compile-kimodo-motion `
  .\inputs\motion.npz .\inputs\motion.source.json .\inputs\motion.map.json `
  --state-root .\workspace

python -m autospine_workbench verify-kimodo-motion `
  --clip-sha256 <motion-ir-sha256> `
  --bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace
```

P8 从上述精确 P7 双 SHA 和一个显式 `camera.json` 发布三文件投影证据 bundle；验证命令会重放 P7 的原始 NPZ，再逐字节重建 P8。完整相机合同、固定地址、候选尺度探针和失败边界见 [编译并复验 P8 投影证据](docs/how-to-compile-projected-motion.md)。

```powershell
python -m autospine_workbench compile-projected-motion `
  .\inputs\camera.json `
  --motion-clip-sha256 <motion-ir-sha256> `
  --motion-bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace

python -m autospine_workbench verify-projected-motion `
  --projected-motion-sha256 <projected-motion-sha256> `
  --bundle-sha256 <projected-bundle-sha256> `
  --state-root .\workspace
```

P9 从精确 P3/P5/P8 身份发布候选，把人工决定编译为 reviewed root/draw-order policy，再生成 MotionInstance v2、Spine preview 和可独立复验的 bundle。全部交接使用精确 SHA，不解析 `latest`；完整 `--document-only` 操作见 [复核并发布 Kimodo 动作策略](docs/how-to-review-kimodo-motion-policy.md)。

P10.0–P10.2 从精确 Layer Manifest/P3/P5/P9 七 SHA 链先编译 idle candidates，再把独立人工 review input 编译为 decision，最后为唯一的 `body_sway / adjust / pending_probe` 选择生成只读结构探针。三个入口均零写入；`--document-only` 只改变 stdout 形状。命令模板、七项 checks、hash 解释与人工 runtime 门禁见 [复核 idle 行为并运行 body-sway 结构探针](docs/how-to-review-idle-behaviors.md)。关键实现入口为 [exact chain loader](src/autospine_workbench/p10_exact_chain.py)、[candidate compiler](src/autospine_workbench/idle_behavior_candidates.py)、[decision compiler](src/autospine_workbench/idle_behavior_decision.py) 和 [probe report compiler](src/autospine_workbench/body_sway_probe_report.py)。

P10.3a–P10.3c 先用 `compile-body-sway-preview` 把通过探针的决定编译为内存中的临时 Spine 4.2 preview，再在操作者提供且已确认授权的官方 `@esotericsoftware/spine-player@4.2.119` 中捕获固定 640×640 PNG，最后把 project、temporary preview、runtime capture bundle 与 artifact set 四项完整身份交给视觉复核。复核 candidate、历史和 decision 保持分离；prepare/GET 零写入，提交使用显式 `base_revision`/head SHA 做 CAS，并把 decision 追加到最多 64 项的 write-once 线性历史。CLI、API 和页面都不发现 `latest`，页面初始也不会自动选择 capture、历史 revision 或提交基线。完整操作、路由和并发恢复见 [复核 body-sway 官方 runtime 采样帧](docs/how-to-review-body-sway-runtime.md)。真实采集的官方 runtime 与许可前置条件见 [捕获并封存 body-sway 官方 runtime 证据](docs/how-to-capture-body-sway-runtime.md)。

P10.4a 用 `compile-body-sway-review-admission` 重放同一 P10/capture 链，并执行 `history A → exact decision → history B`。只有两次快照一致且指定 revision 是当前 `sampled_visual_approved` head 时才输出 path-free canonical admission；命令零写入，且 release gate 继续 blocked。完整参数、保存方式和 head 失效语义见 [准入已批准的 body-sway 视觉复核头](docs/how-to-admit-body-sway-review.md)。

P10.4b1 用 `compile-body-sway-amplitude-envelope` 在已复核四骨幅度向量的统一 gain 射线上检查 `0/8…8/8` 九个离散 key 状态。`8/8` 必须逐字节重放 P10.2 evidence 与临时 preview rotation keys，分析完成后还会再次执行 current-head 双快照；其余 gain 明确为未视觉复核的 candidate。该合同不推断点间区间、连续时间或安全范围，完整操作见 [编译 body-sway 幅度包络候选](docs/how-to-compile-body-sway-amplitude-envelope.md)。

P10.4b2 用 `compile-body-sway-continuous-proof` 重放 P10.4b1，并以向外舍入的有界区间细分覆盖 `λ∈[0,1]` 与每一对 sampled-linear preview key。任何预算耗尽、异常、非有限值或未闭合边界都只产生 `indeterminate`；全段通过也只证明 preview-model 的 FK、画布、mesh 和共享索引结构，不证明平台 libm/runtime 等价、视觉范围、接缝或发布权。完整操作见 [编译 body-sway 连续预览模型证明](docs/how-to-compile-body-sway-continuous-proof.md)。

P10.5a 用 `compile-seam-anchor-candidates` 从一个精确 Layer Manifest SHA 和一个精确 P3 双 SHA 地址只读编译六条静态接缝关系。generator 绑定完整 canonical algorithm profile；candidate 只含 2–4 对 Q4096 region/Q65535 mesh locator，gap、mesh-mesh 和不可表示状态不会产生 fallback。完整参数、真实样本 golden 与人工边界见 [编译 P10.5a 静态接缝锚点候选](docs/how-to-compile-seam-anchor-candidates.md)。

P10.5b 在独立页面、CLI 与精确 REST API 上比较 P10.5a option，并把固定六关系的 `accept/adjust/reject/unobservable` 选择追加为 candidate-bound write-once revision。prepare/GET 零写入；提交使用 base revision/head SHA 做严格 CAS；每个 option 的父子原始 PNG 由 option membership 与 P3 图片摘要共同寻址。完整流程见 [复核 P10.5b 静态接缝锚点](docs/how-to-review-seam-anchors.md)。

P10.5c 用 `compile-reviewed-seam-anchor-set` 按 `history A → exact decision/P3/candidate replay → pure compile → history B` 确认指定 ready revision 仍是当前 head，再发布固定三文件、双 SHA 寻址的 ReviewedSeamAnchorSet bundle；`verify-reviewed-seam-anchor-set` 只按显式地址重放历史 bundle，不把历史复验冒充 current-head authority。完整命令、错误码、bundle inventory 与真实 A/B test-only gate 边界见 [编译并复验 P10.5c 静态接缝锚点集](docs/how-to-compile-reviewed-seam-anchor-set.md)。

P10.5d 用 `compile-body-sway-dynamic-seam-probe` 读取完整 P10.4b2 proof 文件与一个精确 P10.5c 双 SHA bundle，在分析前后分别重查视觉和接缝 current head，并覆盖每一对相邻 tick、统一 `λ∈[0,1]` 和全部 reviewed anchor pairs。成功 stdout 已包含完整 path-free probe；命令零写入，退出 `0` 时 probe 仍可能为 `indeterminate`。`4 px² = 2 px` 只是一项 anchor-point 工程代理，不是 attachment 边界、raster/视觉或 runtime 结论。完整操作、双层快照、失败语义与真实 A/B blocked gate 见 [探测 P10.5d body-sway 动态接缝锚点](docs/how-to-probe-body-sway-dynamic-seams.md)。

P10.6a 用 `compile-body-sway-motion-consumer-admission` 读取一个完整 canonical P10.5d probe 文件及其显式 SHA，从 probe source closure 中按精确 P9 MotionInstance v2/bundle 地址复验 reviewed-motion bundle，并在 pure core 编译前后重查视觉与接缝 current head。输出内嵌完整 probe、unit-gain setup-local rotation timeline domain 和 MIv2 原有 root/marker/draw-order channels；命令零写入，head scope 仅为 `compile_time`，不发出 MotionInstance v3、Spine adapter 或发布 timeline。操作与边界见 [编译 P10.6a body-sway 动作消费准入](docs/how-to-compile-body-sway-motion-consumer-admission.md)。

P10.6b 用 `compile-body-sway-motion-instance-v3` 严格读取 P10.6a 的完整成功 stdout 与显式 admission SHA，按内嵌地址复验 P9，在纯编译前后重新观察 visual/seam current heads，然后原子发布 `admission + MotionInstance v3 + run` 三文件 bundle。`verify-body-sway-motion-instance-v3` 只按精确 v3/bundle 双 SHA 历史重放，不读取 current head。source `sampled-linear` 被明确编译为 target `linear`；MIv2 基础 channels 不变，rotation 只允许覆盖躯干四骨。完整命令、错误与权限边界见 [编译并复验 P10.6b MotionInstance v3](docs/how-to-compile-motion-instance-v3.md)。

P10.7a 用 `compile-body-sway-spine42-v3` 从精确 MIv3 双 SHA 完整重放 P9/P5/P3、RigIR 与源 PNG，并以独立 adapter profile 生成和原子发布 `skeleton.json/.atlas/.png/run/report` 五文件 bundle。`verify-body-sway-spine42-v3` 只按 skeleton/bundle 双 SHA 历史重放，不读取 current head。未知 timeline/attachment/constraint 会 fail loud；成功只声明 adapter emitted，不声明官方 Runtime、raster、永久 head、publishable timeline 或 release authority。操作见 [编译并复验 P10.7a Spine 4.2 v3](docs/how-to-compile-spine42-v3.md)。

P10.7b 已提供 `capture-body-sway-spine42-v3-runtime`、`verify-body-sway-spine42-v3-runtime`、`prepare-body-sway-spine42-v3-raster-review` 与 `submit-body-sway-spine42-v3-raster-review`。capture 需要操作者提供并明确确认有权使用的官方 `@esotericsoftware/spine-player@4.2.119` 与本机 Chrome；其余命令按精确 P10.7a/capture 地址复验 sampled evidence、准备候选或编译人工决定。基础设施已可用，但两份真实 See-through 样本的官方 Runtime 捕获和逐项人工验收仍待完成；任何成功结果都保持 continuous、persistent-head、publish 和 release claims 为 false/blocked。操作见 [捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](docs/how-to-capture-spine42-v3-runtime.md)。

P10.7b-readiness 用 `audit-body-sway-spine42-v3-readiness --manifest ... --state-root .\workspace [--document-only]` 对请求中显式声明的真实地址做零写入预检。readiness v1 的 Schema、哈希与八项 checkpoint 语义已经冻结，第八项仍固定报告 `p6_setup_golden_comparison_not_declared`；新增 P10.7c 不会反向改写它。当前 canonical 示例固定两份已审计 Manifest/P3 地址，后续五组地址与 raster decision 均为 `null`。因此两个 P9 checkpoint 只报告未声明 exact reviewed-motion 地址；A 的 seam checkpoint 报告 `reviewed_seam_anchor_set_address_not_declared`，这不表示审计读取过或证明不存在 current review head。B 则由精确 P3 seam candidate 的 pure replay 证明四条腿/脚关系不可观测。操作见 [审计两份真实样本的 Spine 4.2 v3 就绪状态](docs/how-to-audit-spine42-v3-readiness.md)。

P10.7c 已交付独立 `compare-body-sway-spine42-v3-setup-golden` 命令。它读取 strict canonical 请求、两份操作者选定的 P6 批准合同和精确 P10.7a/P10.7b 地址，只读重放证据后比较 capture 中唯一的 `setup + opaque_composite` 与对应 approved PNG；报告自哈希只是内容身份，不替代证据重放。命令不会启动官方 Runtime、扫描 mutable head、写入 state 或修改 golden，标准输出仍是临时、不可寻址结果。真实 A/B 当前仍缺真实 Kimodo/P9、seam、P10.7a/capture 等前置，因而尚未执行或通过这项真实样本对照。请求制作、命令和结果解释见 [对照 P10.7c Spine 4.2 v3 Setup Golden](docs/how-to-compare-spine42-v3-setup-golden.md)。

P6 使用 `compile-spine42` 把一个精确 P3 地址导出为 setup-only bundle，或与一对精确 P5 MotionInstance/bundle SHA 组合为单动画 bundle；`verify-spine42` 从导出双 SHA 重建完整上游链。五文件地址、官方 runtime 的本地安装边界与 capture 操作见 [导出、复验并运行 P6 Spine 4.2 资产](docs/how-to-export-spine42.md)。

对版本中立 RigIR 做语义检查：

```powershell
python -m autospine_workbench validate-rig .\path\to\rig.json
```

raw COCO17、canonical pose、几何证据、评估报告和候选分别写入 `pose-adapter-inputs/`、`pose-observations/`、`alpha-geometry-evidence/`、`pose-evaluations/` 和 `joint-candidates/`；manifest bundle 写入 `workspace/builds/<project-id>/layer-manifests/<manifest-sha256>/`，RigIR bundle 写入 `workspace/builds/<project-id>/rig-ir/<rig-sha256>/<bundle-sha256>/`。路径中的哈希来自 canonical 内容，相同输入不会产生相互覆盖的可变结果；编译 run、探针、setup renderer/encoder 或报告变化会产生新的 bundle 地址。`audit-bbox-heuristic`、`pose-alpha-limb-fusion` 和 `pose-alpha-geometry-limb` 都只输出 `heuristic_score`，不是经过标定的概率或模型置信度；pose provider 始终保留原始 pose，并把 alpha 作为有限幅度的软证据。评估报告固定为 `diagnostic`，不内置合格阈值或自动左右修复。

## HTTP API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务状态与项目数量 |
| `GET` | `/api/projects` | 项目摘要列表 |
| `GET` | `/api/projects/{id}` | 完整项目、图层、启发式骨架与当前 override |
| `GET` | `/api/projects/{id}/overrides` | 当前 revision 和 override |
| `PUT` | `/api/projects/{id}/overrides` | 校验并原子保存 canonical patch |
| `GET` | `/api/projects/{id}/composite` | 参考合成图 |
| `GET` | `/api/projects/{id}/embedded-composite` | PSD 内嵌合成图 |
| `GET` | `/api/projects/{id}/contact-sheet` | 图层 contact sheet |
| `GET` | `/api/projects/{id}/layers/{layer_id}/image` | 单图层图片 |
| `GET` | `/api/projects/{id}/validate` | 单项目结构验证 |
| `GET` | `/api/validate` | 所有项目结构验证 |
| `GET` | `/api/projects/{id}/candidate-artifacts` | 已验证候选 artifact 索引 |
| `GET` | `/api/projects/{id}/candidate-artifacts/{sha256}` | 按完整内容 SHA 读取候选文档 |
| `GET` | `/api/projects/{id}/geometry-evidence` | 已验证 alpha geometry artifact 索引 |
| `GET` | `/api/projects/{id}/geometry-evidence/{sha256}` | 按完整内容 SHA 读取几何证据文档 |
| `GET` | `/api/projects/{id}/split-previews` | 已验证 bilateral split 预览索引 |
| `GET` | `/api/projects/{id}/split-previews/{sha256}` | 按完整内容 SHA 读取切分审查文档 |
| `GET` | `/api/projects/{id}/split-previews/{sha256}/parts/{left\|right}/image` | 读取 manifest 绑定的左右子图 |
| `GET` | `/api/projects/{id}/mesh-bundles` | 发现 P3 不可变双 SHA 地址，不自动选择首项 |
| `GET` | `/api/projects/{id}/mesh-bundles/{rig_sha256}/{bundle_sha256}` | 严格重验并读取精确 P3 证据 |
| `GET` | `/api/projects/{id}/mesh-bundles/{rig_sha256}/{bundle_sha256}/images/{png_sha256}` | 读取经 bundle 绑定和哈希复核的证据图 |
| `GET` | `/api/projects/{id}/body-sway-runtime-captures/{preview}/{bundle}/{artifact}/visual-review/candidate` | 从精确四段地址只读编译 P10.3c candidate |
| `GET` | `.../visual-review/candidates/{candidate}/cases/{case}/image/{png}` | 读取 candidate 绑定且重新验真的 PNG |
| `GET` | `.../visual-review/candidates/{candidate}/history` | 读取连续 revision 和 head，不自动选择基线 |
| `GET` | `.../visual-review/candidates/{candidate}/history/{revision}/{decision}` | 读取精确 SHA 绑定的历史 decision |
| `PUT` | `.../visual-review/candidates/{candidate}/decisions` | 通过同源 intent 校验与 CAS 追加完整人工复核 revision |
| `GET` | `/api/projects/{id}/seam-anchor-reviews/{manifest}/{p3_rig}/{p3_bundle}/candidate` | 从精确三 SHA 静态链只读编译 P10.5b candidate |
| `GET` | `.../candidates/{candidate}/options/{option}/attachments/{attachment}/images/{png}` | 读取 option 绑定且重新验真的原始 attachment PNG |
| `GET` | `.../candidates/{candidate}/history` | 读取 seam review 连续 revision 和 head |
| `GET` | `.../candidates/{candidate}/history/{revision}/{decision}` | 读取精确 seam decision |
| `POST` | `.../candidates/{candidate}/decisions` | 通过同源 intent 校验与 CAS 追加六关系人工决定 |

API 响应带 `Cache-Control: no-store`。只接受 loopback Host；CORS 也只回显同 authority 的 loopback origin。分析工件端点会重新验证 strict JSON、内容地址和项目语义；损坏工件不会进入 UI。HTTP 写操作只有三类：`PUT overrides`、精确 body-sway visual-review decision CAS，以及精确 seam-anchor review decision CAS。后两者都要求各自的 `X-Autospine-Intent` 并拒绝跨 authority origin。`/docs/<文件名>.md` 只读映射只允许仓库 `docs/` 目录内的 Markdown，不是写接口；功能入口中心不会直接导航到 `.md`，而是让安全文档查看器 fetch 该路由并按纯文本显示，不解析 HTML。

## 运行测试

完整 schema 测试需要可选的 `jsonschema`：

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

P10.3c 独立视觉复核页面使用零依赖 Node test runner；修改 `web/body-sway-review.*` 或 `web/modules/body-sway-review-*.js` 后还应运行：

```powershell
npm test --prefix web
```

真实 runtime capture 另有两个 opt-in smoke：不含官方 runtime 的 Chrome smoke 只检查进程与 PNG 通路；只有在提供已授权 `@esotericsoftware/spine-player@4.2.119` 并显式确认许可时，licensed smoke 才检查实际 runtime。缺少这些外部前置条件会跳过相应测试，不能用 stub 结果冒充官方 runtime 证据。

如需 Pillow/NumPy 图像比较加速，可安装 `python -m pip install -e ".[analysis]"`；不安装时仍有标准库 PNG 解码路径。

未安装 `jsonschema` 时，标准库运行与大部分测试仍可执行，完整 Draft 2020-12 实例校验会标记为 skipped。若仓库中存在两份真实 See-through audit，测试还会固定表示层差异和真实可见差异的区分：透明 RGB 与扁平背景造成的巨大 raw RGBA MAE 不会直接判为视觉失败；背景匹配后的可见颜色差异仍会失败。第 5 channel、空且隐藏图层、左右语义歧义与缺失部位仍需人工复核。

Resolved Project v1 的 Python 语义测试不依赖 `jsonschema`；可选依赖只决定 Draft 2020-12 实例测试是否执行。合同字段、公开 validator、r5/r7 历史回归和版本升级规则见 [Resolved Project v1 参考](docs/resolved-snapshot-reference.md)。

## P1 门禁证据

P1 已交付 pose、alpha 中轴线和层接触候选，以及候选比较、四类人工决定和固定证据回看。可复现证据如下：

| 门禁 | 仓库证据 |
| --- | --- |
| 同一 stage 输入得到相同工件身份 | provider/CLI identity 测试；诊断发布重复运行得到相同 pose、geometry、candidate SHA |
| 候选只能引用已发布几何内容 | 跨文档 validator 检查 SHA、path、contact、layer/component fragment；错引用在首次发布前失败 |
| 可接受、调整、拒绝或标记不可观测 | candidate-aware override/binder 测试与候选审查 UI 状态测试 |
| 证据可回看且损坏时 fail closed | candidate/geometry 只读 API、SVG overlay/controller 测试及严格 repository 读取边界 |
| 两份样本可产出完整链 | `tools/publish_diagnostic_samples.py`；真实样本 geometry/candidate smoke 测试 |

诊断样本使用 resolved setup 关节作为零分、未知可见性的 prior，只证明工作流和内容地址可复现，不代表姿态模型精度。复核命令见 [生成并复核四肢候选](docs/how-to-run-pose-alpha.md)。

## 数据与恢复

- audit JSON、PSD 和 PNG 被视为不可变输入。
- 每次保存先写 `<state-root>/overrides/<project-id>/history/rNNNNNN.json`，再以原子替换更新 `latest.json`；历史快照不会被后续 revision 改写。
- `latest.json` 丢失时会从 history 恢复最新 revision；旧版 `<state-root>/overrides/<project-id>.json` 会被只读兼容，并在下一次保存时迁移，不会原地改写。
- 若要恢复旧 revision，先停止服务，备份整个项目 override 目录，再将目标历史快照作为新的、经过校验的 revision 提交；当前界面尚未提供历史浏览/回滚按钮。
- validation 的 `valid=true` 仅表示结构和本地资产检查没有硬错误，不等于美术、遮挡补全、pivot、mesh 或动画通过视觉验收。

## 已完成合同与阶段：P0、P2 region RigIR 至 P9 reviewed motion，以及 P10.0–P10.7c setup regression 基础设施

P0 合同加固、P1 四肢候选与 P2 region-only RigIR 已贯通：`stage-scoped analysis → immutable geometry/candidates → candidate-bound revision → deterministic resolved snapshot → reviewed Layer Manifest → RigIR/setup bundle`。P2 没有提前引入 mesh：

P0 的 Resolved Project v1 已有独立 Draft 2020-12 Schema 与严格语义 validator。validator 会重算 snapshot SHA、候选 inventory/run identity、current/stale split provenance、实体交叉引用和全部 QA 列表；两个真实历史 revision 的既有哈希由回归测试固定，不因补充公开合同而改写。v1 的字段与解释已冻结，未来任何改变 resolved 生成或 QA/provenance 语义的算法升级都必须发布 `autospine.resolved-project/v2`，不能沿用 v1 token 或让旧决定静默获得新含义。

1. 从已复核 Layer Manifest 与 resolved joints 编译 region-only RigIR，固定规范骨角色、pivot、父子关系、slot 和 draw order。
2. 用独立 FK setup probe 重建每个 region 的 world transform，并与 audit 合成基线比较。
3. 对未知语义、缺失 pivot、非法父子关系或 draw order 歧义 fail closed，不用 bbox fallback 冒充人工确认。
4. bilateral split v1.2 会优先整块分配可靠的双连通域，融合层才回退像素最近规则；算法升级使旧决定 stale，三个真实决定均已重新目视批准。
5. 两份真实样本均以严格模式重复编译为相同内容地址；setup 精确重建，pivot/父子关系/draw order 与固定 visual golden 全部通过。

P2 验收证据：A 为 27 层/25 region，B 为 22 层/20 region；两者各 17 根骨骼，setup differing pixels/channels 均为 0、MAE 为 0。固定批准合同位于 `tests/goldens/p2-setup/`。

P3 在该精确 P2 基线上增加可独立验证的 alpha mesh 与参数化两骨 LBS：

1. 仅把通过 eligibility 合同的 alpha attachment 转为 mesh；不满足条件的样本发布带原因和完整输入身份的 `reviewed-noop`，不伪造空 mesh。
2. 参数化权重绑定明确的 proximal/distal 骨，权重和、索引、三角形 winding、面积、setup 重建与有限数均有不变量测试。
3. 动作探针按方向搜索连续安全角，拒绝翻三角和明显裂缝，并发布 setup、最宽安全姿势和权重热图三类 PNG。
4. bundle 以 P3 rig SHA 与 bundle SHA 双重寻址；严格 reader 会重建全部上游/下游内容，并保证验证前后状态树完全不变。
5. 两份真实 See-through 样本均有固定批准合同：A 转换 2 个 hinge，共 739 顶点/1212 三角形；B 由于没有合格 hinge，稳定发布 reviewed no-op。

P3 的拓扑计数、安全角和每张 PNG 的 encoded-byte/RGBA SHA 固定在 `tests/goldens/p3-mesh/`。普通测试验证合同；设置 `AUTOSPINE_VERIFY_REAL_P3_GOLDENS=1` 后运行 `python -m unittest tests.test_p3_mesh_goldens`，会从精确 P2 地址重编译并只读复核真实 bundle。

P4 在精确 P3 来源上建立版本中立的离线 IK 边界：

1. 为左右臂和左右腿生成四个 canonical 两骨目标手柄，弯曲方向来自 setup 几何，不按角色左右硬编码。
2. analytic solver 对可达、过远、过近、镜像、目标重合和退化骨长输入均返回有限结果或明确失败，不产生 NaN。
3. 求解结果转换为 additive setup-local 旋转增量；setup 目标会精确重建肘/膝位置并产生零增量。
4. 固定探针覆盖 setup、可达中点、过远、过近和重合目标；运动学可达环与 P3 mesh 视觉安全范围保持两个独立合同。
5. profile/probes 以双 SHA 不可变发布，strict reader 从完整 9 项 P3 身份链重建并逐字节复验，不解析 `latest`。
6. 两份真实样本各稳定生成 4 个手柄、20 个有效探针案例且无 N/A；身份、弯曲方向和可达范围固定在 `tests/goldens/p4-ik/`，显式真实复验还证明整个 state tree 前后不变。

P5 在精确 P3/P4 来源上完成版本中立动画、BVH 编译和通用动作重定向：

1. `idle` 与 `wave.left` 以 setup-local rotation、归一化 root/IK 空间和接触 marker 表示；相同输入固定为相同 MotionIR/run/bundle SHA。
2. BVH 只接受人工确认的显式 map；四文件 bundle 原样保存 source BVH，并把 raw/map/compiler/MotionIR 全部交叉绑定，复验时从原始字节重编译。
3. retarget pipeline 只读取明确的 P3、P4 与 Motion 双 SHA，生成 target profile、MotionInstance、run、运动学报告和 mesh regression 五文档 bundle；任一报告失败都不会发布。
4. 同一内建 clip 已在三个不同 setup rig 上通过；两份真实 See-through 样本的四组 idle/wave 结果也固定在 `tests/goldens/p5-motion/`。
5. A 的两个 mesh attachment 在 41 个采样点均通过，B 稳定为 `reviewed-noop`；四组接触均为 2/2 保留，真实 opt-in 回归还证明只读重建不会改变 state tree。

P6 门禁已经完成：adapter profile 固定为 Spine JSON 4.2，`compile-spine42`/`verify-spine42` 发布并重建五文件内容寻址 bundle。A/B 两份真实样本的 setup、`idle`、`wave.left` 六个地址固定在 `tests/goldens/p6-spine42/real-exports.approved.json`；精确的 `@esotericsoftware/spine-player@4.2.119` 在 640×640、DPR 1 下加载六例，第二轮截图与批准 PNG 的 differing pixels、MAE 和最大通道差均为 0。runtime 合同与图片位于 `tests/goldens/p6-spine42/runtime.approved.json`，官方 runtime 仍由操作者在仓库外安装并确认许可。

P7a 已完成 Kimodo SOMA77 BVH 结构兼容 smoke：严格支持零包装 `Root` 下的 6DOF `Hips`，保留原始 BVH 内容地址，并通过三套 rig 的 P5/P6 bundle 门禁。测试输入是合成的 Kimodo-shaped fixture，不代表真实模型动作质量，也尚未进入官方 Spine Player 截图 golden。生成、映射、编译与限制见 [编译 Kimodo SOMA77 BVH](docs/how-to-compile-kimodo-bvh.md)。

正式 P7 合同与合成门禁已完成：严格的 Kimodo SOMA77 NPZ、独立 source sidecar 和显式 map 被编译为五文件内容寻址 MotionIR bundle；同一个合成 MotionIR 已通过三套不同 rig 的 P5 重定向和 P6 adapter/bundle reader。测试输入由标准库确定性生成，不是 Kimodo checkpoint 输出，也尚未进入该动作的官方 Spine Player 截图 golden。完整操作、失败边界和模板见 [编译 Kimodo SOMA77 NPZ](docs/how-to-compile-kimodo-npz.md)。

P8 相机感知投影与候选尺度门禁已完成：`CameraModel v1` 和 `ProjectedMotionIR v1` 保留逐段二维向量、L2/L3、深度余弦、root-relative depth、透视缩短比和 collapsed/observable 状态，并发布为精确重放 P7 的三文件不可变 bundle。legacy bridge 必须逐字节重建 P7 MotionIR；同一投影证据已经在三套不同目标 rig 上产生 setup-relative 长度候选，并再次通过 P5/P6，目标 profile 与 Spine 输出没有新增 scale timeline。P8 深度只作为证据，不决定前后遮挡；候选报告也不会自动成为动画。操作与边界见 [编译并复验 P8 投影证据](docs/how-to-compile-projected-motion.md)。

P9 reviewed motion 结构闭环已完成：foot-lock/depth-order evidence 与 candidate 不是决定；决定必须覆盖精确候选集，然后才能编译 reviewed policy、MotionInstance v2 与独立 Spine 4.2 v2 preview。六文件 reviewed bundle 固定 inventory，从 run manifest 重放精确 P3/P5 上游，无 `latest` 或扫描回退。MotionInstance v1/P8 哈希保持不变；heading/scale 仍是 evidence-only，attachment switch 尚未实现。loader-isomorphic audit 只是结构验证，不等于官方 runtime 或 raster truth；P9 动态官方 runtime screenshot 与真实 Kimodo reviewed asset 门禁仍未关闭。

P10.0/P10.1 已建立 candidate/decision 分离的 idle 行为合同；当前只有完整 canonical 躯干链可产生 `body_sway` candidate，眨眼、口型和头发仍明确保持不可观测或不支持。P10.2 会把人工给出的周期、四骨幅度和相位叠加到 exact MotionInstance v2，在固定离散 schedule 上检查 loop、FK、mesh、画布和共享索引，并把接缝与视觉质量保留为不可观测。报告只可能是 `structural_rejected` 或 `manual_visual_required`，release gate 始终 blocked；它不生成 MotionInstance v3 或 runtime timeline，也不证明连续时间、安全范围、接缝或视觉质量。

P10.3a/P10.3b 已完成 deterministic preview、固定 case 计划、官方 Spine 4.2.119 runtime runner 与内容寻址 capture 封存；真实采集必须由操作者提供已授权 runtime 并显式确认许可，test-only player stub 只用于进程 smoke。P10.3c 从 project/preview/bundle/artifact 精确四段地址确定性编译 sampled still candidate，并在独立页面、CLI 与 HTTP 上共享零写入 prepare、path-free evidence、不可变历史和严格 CAS。所有 case approve 时只得到 `sampled_visual_approved`；安全范围、连续时间、reviewed seam anchors 和 preview-only timeline 仍未关闭，因此 release gate 始终 blocked。

P10.4a 已增加 `BodySwayReviewAdmission v1`：从精确 P10/capture/visual 地址先后读取两次 authoritative history，并在中间重放精确 decision；旧 approved revision、reject/unobservable head、读取期间 head 漂移和任一跨链输入都会 fail closed。admission 只声明 sampled visual 已批准且 head 在编译时被观察，五项发布相关 claims 固定为 false；它不发布 MotionInstance v3，也不能在后续 revision 产生后继续冒充 current-head authority。

P10.4b1 已增加 `BodySwayAmplitudeEnvelopeCandidate v1`：只沿 reviewed amplitude vector 的统一 gain 射线生成九个 sampled structural probes，不构造四维独立幅度盒，也不假设单调性。reviewed gain 必须与 P10.2 stream/checks 和实际 sampled-linear preview keys 完全一致；命令在分析后再次按 `history → exact decision → history` 复核 head。所有范围、连续时间、视觉范围、seam、MotionInstance v3 与发布 claims 仍固定为 false。

P10.4b2 已增加 `BodySwayContinuousPreviewProof v1`：完整内嵌并重算 amplitude candidate、RigIR、target profile、MotionInstance v2、temporary preview manifest 与 preview projection，在统一 gain `λ∈[0,1]` 和全部相邻 preview tick 上执行有界区间证明。所有段通过时只开放两项 preview-model structural claims；预算耗尽、异常、非有限数或后端证明对象不一致均 fail closed 为 `indeterminate`。平台 libm/runtime 等价、raster 视觉范围、reviewed seam anchors、MotionInstance v3、可发布 timeline 与 release authority 仍固定为 false/blocked。

P10.5a 已增加 `SeamAnchorCandidates v1`：从精确 Layer Manifest/P3 静态链建立 torso-arm、pelvis-leg、leg-foot 左右六条关系，比较 setup alpha contact lobe，并生成可回看的 region/mesh attachment-local locator。候选与人工决定严格分离，generator `1.1.0` 的算法 profile SHA 会随实际行为常量变化；两份真实样本分别稳定得到 9 个/36 对与 2 个/8 对 candidate。human decision、reviewed anchor set、动态 seam、runtime/视觉质量和发布权仍固定为 false/blocked。

P10.5b 已增加 `SeamAnchorReviewDecision v1`：相同四段精确地址会重编 candidate，人工提交必须逐行绑定 relationship/option evidence SHA，并以 candidate SHA 隔离最多 64 项的不可变线性历史。相同并发提交收敛到一个 revision，不同提交只有一个 CAS winner；历史 slot、content-address 文件、candidate 或 P3 任一篡改都会 fail closed。六行全部 accept/adjust 只得到 `reviewed_anchor_set_ready_for_compile`，仍需 P10.5c 编译 reviewed set，release gate 始终 blocked。

P10.5c 已增加 `ReviewedSeamAnchorSet v1`：只有 current ready head 可被投影，set 固定六关系顺序、2–8 对 materialized anchors 和六项 source 身份，不重新选择 option 或生成 locator fallback。三文件 bundle 在写前重编并以 set/bundle 双 SHA 寻址；历史精确地址可复验但不拥有永久 current-head authority。真实 A/B opt-in gate 中 A 只使用明确标注的 test-only 内存决定验证合同可编译，B 的四条不可观测关系保持 blocked；该 gate 不构成真实人工批准或资产 golden。动态 seam、runtime/视觉质量和发布权仍固定为 false/blocked。

P10.5d 已增加 `BodySwayDynamicSeamProbe v1`：它完整重放 P10.4b2 与 P10.5c source closure，用 region 刚性投影或 mesh 重心/LBS 投影检查固定六关系的全部 reviewed anchor pairs，并以有界区间覆盖相邻 tick 与统一 gain。命令在 pure analysis 外再包一层 before/after current-head 检查，每次观察内部又执行视觉与接缝双快照；scope 只在 compile time 有效。只有上游结构证明和全部 seam segment 同时认证才开放 proximity 工程 claim；`dynamic_seam_safety`、边界连续、raster/视觉、runtime、timeline 与 release authority 始终为 false/blocked。

P10.6a 已增加 `BodySwayMotionConsumerAdmission v1`：只有认证的 P10.5d probe 可以进入，source 内嵌其完整 canonical 文档，并重新绑定/复验精确 P9 MotionInstance v2 六文件 bundle。pure core 选定 reviewed unit gain，把 sampled-linear rotation keys 与 MIv2 原有 root translation、markers、stepped draw order 组织为版本中立 setup-local motion domain；seal 在前后两次 current-head observation 完全一致后才开放 `setup_local_timeline_compilation_admitted`。所有 observation scope 仅为 `compile_time`；该 admission 本身不发出 MotionInstance v3、Spine adapter 或发布权。

P10.6b 已增加严格 `MotionInstance v3` Schema、pure compiler、三文件内容寻址 bundle、原子 store、exact reader，以及 compile/verify CLI。compile 不直接信任历史 admission 的 head 结论；公开命令和 store 自身都在待发布值构造前后重新观察 current heads，任何 identity/bytes 漂移均零发布，成功写入后还会按精确地址重新读取并逐字节验证。admission 上限固定为 64 MiB。run manifest 只授予 `motion_instance_v3_emitted`，其余 Spine adapter、完整 attachment 边界、raster/视觉、官方 runtime、永久 head authority、publishable Spine timeline 与 release authority 均为 false/blocked；历史 verify 也明确不观察 current heads。

P10.7a 已增加独立 Spine 4.2 adapter v3 capability、MIv3→P9→P5/P3 完整精确重放、五文件内容寻址 bundle、current-head 门禁、原子 store、exact reader 与 compile/verify CLI。旧 P6 profile、adapter 和 golden 哈希不变；未知 timeline、attachment、constraint 或 interpolation 会 fail loud。run 唯一授予 `spine_adapter_emitted`，官方 Runtime、完整 attachment raster、永久 current-head authority、publishable timeline 与 release authority 仍为 false/blocked。

P10.7b 已增加固定 runtime/capture profile、确定性 case plan、官方 Spine Player/浏览器精确身份封存、opaque/transparent composite 与完整 setup attachment isolate 捕获、sampled alpha/raster 指标、不可变 capture store/exact reader，以及 candidate/人工 decision 分离的四个 CLI。capture 是 `external_required`，不会下载 runtime 或代替操作者确认许可；prepare/submit 不扫描 `latest`，submit 也不发布 authoritative revision。基础设施交付不等于真实资产验收：两份真实 See-through 样本仍需各自具备 P10.7a 输入、运行官方 capture 并完成人工逐项决定；continuous runtime raster safety、永久 head、publishable timeline 与 release authority 始终 blocked。

P10.7b-readiness 已增加 strict canonical request 与 exact-address、zero-write 审计 CLI。它只重放请求明确声明的 Manifest/P3 和后续地址，并报告 P3 seam、P9、P10.5c、P10.6b、P10.7a、runtime capture、raster review 与 P6 setup comparison 八个 checkpoint。v1 已冻结且第八项仍固定为 missing；独立 P10.7c 命令不会改变其 Schema、哈希或报告含义。当前示例未声明两个项目的 P9 地址；A 也未声明 P10.5c 地址，B 的精确 P3 candidate 则证明左右 pelvis-leg/leg-foot 四关系不可观测。任何 readiness 结果都不授予 publish/release authority。

P10.7c 已增加 strict canonical setup-regression request/report、冻结 comparison profile、P6 批准合同精确字节绑定、P6/P10.7a 同 P3 与 atlas/texture 来源闭合、P10.7b setup capture 只读提取、RGBA 指标，以及由 exact evidence 在函数内部重新计算 sample 的 replay binding。该能力已交付不等于真实双样本通过：A/B 仍须先提供真实 Kimodo/P9、seam、P10.7a 与官方 capture 地址，之后才能运行对应真实请求；当前只能验证机制与既有 P6 基线，没有真实 P10.7c 通过结论。临时报告尚不是 readiness admission；readiness v2 前必须增加可寻址、不可变且可重放的 comparison bundle。

姿态 runner 与真实标注评估集仍是独立质量轨，不阻塞版本中立 P2 编译；诊断 setup prior 不能替代真实模型基线。

面部锚点、头发弹簧和实时追踪映射可以作为独立模块接到同一规范骨角色上；四肢扩展的关键不是增加更多屏幕坐标映射，而是建立 bind pose、父子骨、权重和重定向空间。

## 非目标与已知边界

当前版本不负责：

- 运行 See-through 推理、选择 seed、编辑 PSD 或自动清理图层；
- 下载或运行具体姿态模型；`import-pose` 只转换经过哈希固定且已还原到原画布的 COCO17 输出；
- 自动解决 `head-obj`、`objects`、合并肢体等歧义语义；
- 证明遮挡补全符合解剖或在大幅动作下不会露馅；
- 自动生成自由形变 deform 或运行时 IK constraint；动态 draw order 只来自 P9 人工批准的 slot-pair policy，不做 raster-truth 推断；
- 无人复核地把 Kimodo contact、heading、depth 或 scale 写入 runtime；P9 只消费人工批准的 foot correction 和 pairwise draw order，heading/scale 仍是 evidence-only，attachment switch 尚未实现；
- 把合成 P7 门禁当作真实 Kimodo checkpoint、真实动作质量或该 clip 的官方 Spine Player 截图验收；
- 把 loader-isomorphic audit 当作官方 runtime 或 raster truth；P9 动态官方 runtime screenshot 与真实 Kimodo reviewed asset 门禁仍需单独关闭；
- 把 P10 `completed_diagnostic`、离散结构采样通过、sampled still 全部批准、review 输入的 0–10 度语法包络或 P10.4b2 preview-model 区间证明当成 MotionInstance v3、runtime 等价、可发布 Spine timeline、接缝安全或人工视觉安全范围；
- 把 P10.5a 静态候选、contact overlap 或 locator evidence 当成人工决定、reviewed seam anchor set 或动态动作域接缝安全；
- 把 P10.5c 的静态 ReviewedSeamAnchorSet、历史 bundle 可复验或 compile-time current-head 观察当成永久审批权、动态 seam 证明、runtime/视觉质量或发布许可；
- 把 P10.5d 的 `4 px²` reviewed-anchor point 代理、`compiled` 命令状态或保存的 stdout 当成完整 attachment 边界连续、raster/视觉接缝通过、runtime 等价、永久 current-head authority 或发布许可；
- 把 P10.6a 的 setup-local timeline compilation admission 当成 MotionInstance v3/Spine adapter 已发出、完整边界或 raster 视觉通过、runtime 等价、永久 head authority、publishable timeline 或 release authority；
- 把 P10.6b 的 MotionInstance v3、历史 bundle 可重放或发布前 head 双观察当成 Spine adapter 已编译、官方 runtime/raster 通过、永久 head authority、publishable Spine timeline 或 release authority；
- 把 P10.7a adapter、P10.7b sampled capture/指标或一次人工 decision 当成连续时间 raster 安全、永久审批、可发布 timeline 或 release authority；
- 把冻结的 P10.7b-readiness v1 报告当成外部阶段执行记录、current review head 发现、人工决定、P10.7c setup golden 对照或发布授权；
- 把 P10.7c 单帧 setup RGBA 对照当成动画 case 人审、连续时间 raster 安全、真实双样本已验收或发布授权；
- 在未提供并确认授权的官方 Spine 4.2.119 runtime 时，用 test-only player stub、进程 smoke 或任意相邻截图冒充真实 capture；
- 生成眨眼/口型素材、实时追踪映射或运行时物理；
- 捆绑或再分发官方 Spine runtime、判断任意未知 Spine 版本、生成 Spine Editor 工程，或覆盖固定 P6 profile 之外的特性；
- 代替输入素材、训练数据或模型权重的许可证与商业使用审查；
- 多用户权限、远程协作或生产部署。

这些边界并非都应一次性并入当前阶段。下一顺序是先生成、复核并声明真实 Kimodo P7/P8/P9 exact 地址，完成或确认 A 的 seam 人审并声明 P10.5c 地址，以及完成 B 的上游语义/分层修复或独立 partial 合同；再完成两份真实样本的官方 Runtime capture、逐项人审，并使用已交付的 P10.7c 命令执行 P6 setup golden 对照；随后把 canonical request/report、批准合同和批准 PNG 封存为可寻址 comparison bundle，再接 readiness v2；之后进入 attachment switch → blink/mouth。输入模型 runner 继续作为独立质量轨；完整计划见[后续开发路线](docs/development-roadmap.md)。

项目中显示的骨架来自 bbox/语义启发式，`requires_review=true`。只有在语义、左右、pivot、层级、合成回归和动作探针均通过后，才能把人工确认结果交给后续 RigIR/导出阶段。

代码职责、依赖方向、文件长度预算和阶段完成门禁见 [docs/architecture.md](docs/architecture.md)。
