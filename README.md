# AutoSpine Workbench

AutoSpine Workbench 是一个本地人工复核界面，用于查看 See-through PSD 审计结果、校正图层语义和 setup 可见性、调整启发式关节，并保存带 revision 的 override。它不会修改 PSD、审计 JSON 或 PNG；默认只向 `autospine-workbench/workspace/overrides` 写入状态。

当前阶段的目标是把“模型输出”变成可追溯、可复核的 authoring 输入，而不是直接宣称生成了可发布的 Spine 资产。

## 能做什么

- 从 `<workspace>/tmp/psd_audit/results/*/audit.json` 发现项目。
- 在统一画布坐标中查看参考合成图、独立图层与骨架覆盖。
- 检查空图层、未分类语义、低置信度关节和合成差异等 QA 信息。
- 覆盖图层语义、角色左右、setup 可见性、pivot 与 region 目标骨，并逐字段确认人工复核。
- 拖动或精确输入关节坐标，并恢复自动推断位置。
- 使用 optimistic concurrency 保存 override；过期 revision 不会覆盖新结果。
- 每次成功保存都写入 append-only revision 历史，并生成应用人工决定后的 resolved snapshot。
- 在界面加载内容寻址候选，比较画布标记、alpha 中轴线/接触证据，并记录 accept/adjust/reject/unobservable 决定。
- 候选决定绑定完整内容 SHA；算法输出变化不会把旧决定静默套用到新工件。
- 通过只读验证 API 检查画布、图层 ID、资产路径和骨架结构。
- 离线发布带 provenance 的关节候选、region-first Layer Manifest 与 region-only RigIR bundle。
- 把固定的 COCO17 检测转换为显式左右/镜像 provenance 的 canonical pose，并用人工复核四肢点生成诊断误差报告。
- 对 RigIR 执行跨引用、拓扑、权重、三角形及 timeline 语义验证；不支持特性会明确失败。
- 从精确 P3 bundle 编译四个 canonical 两骨 IK 手柄，固定弯曲方向、可达环和 setup-local 数值探针。
- 编译可复用的 setup-local MotionIR（内建 idle/wave 或显式映射 BVH），并从精确 P3/P4/Motion 地址生成带接触、运动学与 mesh 回归证据的不可变 MotionInstance bundle。
- 以 compiler 1.1.0 严格读取 Kimodo 双根 SOMA77 BVH，并让同一 MotionIR 穿过三 rig 与 Spine 4.2 bundle 兼容性门禁。
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

启动后打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。默认配置为：

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

`joint_overrides` 是与候选算法无关的绝对人工坐标；`joint_decisions` 表示 accept、adjust、reject 或 unobservable，同一关节不能同时出现在两者中。accept 坐标由服务端从内容寻址候选工件派生，客户端不能提交。`side` 使用 `left`、`right`、`center`、`bilateral` 或 `unknown`，始终表示角色自身左右。`visible` 只定义 setup/复核预览可见性，不会改写 PNG。关节与 pivot 必须是有限数，并位于画布内。完整语义见 [候选关节决定参考](docs/candidate-decisions-reference.md)。

JSON Schema 位于：

- `schemas/override-patch-v2.schema.json`：当前在线 API 的 candidate-aware canonical patch；v1 仅用于历史兼容；
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

P5 将动作与目标 rig 分开内容寻址。内建 `idle`/`wave.left`、显式 BVH map、目标重定向及只读复验分别使用 `compile-builtin-motion`、`compile-bvh-motion`、`compile-motion-retarget` 与对应 verify 命令。所有命令只接受精确 SHA，不解析 `latest`；完整合同、固定地址、A/B 示例和排障步骤见 [编译、重定向并复验 P5 动画](docs/how-to-compile-motion.md)。

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

API 响应带 `Cache-Control: no-store`。只接受 loopback Host；CORS 也只回显 loopback origin。分析工件端点会重新验证 strict JSON、内容地址和项目语义；损坏工件不会进入 UI。除 `PUT overrides` 外，API 不提供写操作。

## 运行测试

完整 schema 测试需要可选的 `jsonschema`：

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

如需 Pillow/NumPy 图像比较加速，可安装 `python -m pip install -e ".[analysis]"`；不安装时仍有标准库 PNG 解码路径。

未安装 `jsonschema` 时，标准库运行与大部分测试仍可执行，完整 Draft 2020-12 实例校验会标记为 skipped。若仓库中存在两份真实 See-through audit，测试还会固定表示层差异和真实可见差异的区分：透明 RGB 与扁平背景造成的巨大 raw RGBA MAE 不会直接判为视觉失败；背景匹配后的可见颜色差异仍会失败。第 5 channel、空且隐藏图层、左右语义歧义与缺失部位仍需人工复核。

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

## 已完成阶段：P2 region-only RigIR、P3 两骨 LBS、P4 离线 IK 与 P5 MotionIR

P0 合同加固、P1 四肢候选与 P2 region-only RigIR 已贯通：`stage-scoped analysis → immutable geometry/candidates → candidate-bound revision → deterministic resolved snapshot → reviewed Layer Manifest → RigIR/setup bundle`。P2 没有提前引入 mesh：

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

P7a 已完成 Kimodo SOMA77 BVH 结构兼容 smoke：严格支持零包装 `Root` 下的 6DOF `Hips`，保留原始 BVH 内容地址，并通过三套 rig 的 P5/P6 bundle 门禁。测试输入是合成的 Kimodo-shaped fixture，不代表真实模型动作质量，也尚未进入官方 Spine Player 截图 golden。生成、映射、编译与限制见 [编译 Kimodo SOMA77 BVH](docs/how-to-compile-kimodo-bvh.md)；下一步是正式 P7 NPZ adapter。

姿态 runner 与真实标注评估集仍是独立质量轨，不阻塞版本中立 P2 编译；诊断 setup prior 不能替代真实模型基线。

面部锚点、头发弹簧和实时追踪映射可以作为独立模块接到同一规范骨角色上；四肢扩展的关键不是增加更多屏幕坐标映射，而是建立 bind pose、父子骨、权重和重定向空间。

## 非目标与已知边界

当前版本不负责：

- 运行 See-through 推理、选择 seed、编辑 PSD 或自动清理图层；
- 下载或运行具体姿态模型；`import-pose` 只转换经过哈希固定且已还原到原画布的 COCO17 输出；
- 自动解决 `head-obj`、`objects`、合并肢体等歧义语义；
- 证明遮挡补全符合解剖或在大幅动作下不会露馅；
- 自动生成自由形变 deform、运行时 IK constraint 或动态 draw order；P3 只覆盖通过门禁的 alpha mesh 与参数化两骨 LBS，P4 只提供离线两骨目标求解；
- 生成眨眼/口型素材、实时追踪映射或运行时物理；
- 捆绑或再分发官方 Spine runtime、判断任意未知 Spine 版本、生成 Spine Editor 工程，或覆盖固定 P6 profile 之外的特性；
- 代替输入素材、训练数据或模型权重的许可证与商业使用审查；
- 多用户权限、远程协作或生产部署。

项目中显示的骨架来自 bbox/语义启发式，`requires_review=true`。只有在语义、左右、pivot、层级、合成回归和动作探针均通过后，才能把人工确认结果交给后续 RigIR/导出阶段。

代码职责、依赖方向、文件长度预算和阶段完成门禁见 [docs/architecture.md](docs/architecture.md)。
