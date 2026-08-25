# AutoSpine Workbench

AutoSpine Workbench 是一个本地人工复核界面，用于查看 See-through PSD 审计结果、校正图层语义和 setup 可见性、调整启发式关节，并保存带 revision 的 override。它不会修改 PSD、审计 JSON 或 PNG；默认只向 `autospine-workbench/workspace/overrides` 写入状态。

当前阶段的目标是把“模型输出”变成可追溯、可复核的 authoring 输入，而不是直接宣称生成了可发布的 Spine 资产。

## 能做什么

- 从 `<workspace>/tmp/psd_audit/results/*/audit.json` 发现项目。
- 在统一画布坐标中查看参考合成图、独立图层与骨架覆盖。
- 检查空图层、未分类语义、低置信度关节和合成差异等 QA 信息。
- 覆盖图层语义、角色左右、setup 可见性与 pivot 提示。
- 拖动或精确输入关节坐标，并恢复自动推断位置。
- 使用 optimistic concurrency 保存 override；过期 revision 不会覆盖新结果。
- 每次成功保存都写入 append-only revision 历史，并生成应用人工决定后的 resolved snapshot。
- 候选 accept/adjust/reject/unobservable 决定绑定完整内容 SHA；算法输出变化不会把旧决定静默套用到新工件。
- 通过只读验证 API 检查画布、图层 ID、资产路径和骨架结构。
- 离线发布带 provenance 的关节候选工件和 region-first Layer Manifest bundle。
- 把固定的 COCO17 检测转换为显式左右/镜像 provenance 的 canonical pose，并用人工复核四肢点生成诊断误差报告。
- 对 RigIR 执行跨引用、拓扑、权重、三角形及 timeline 语义验证；不支持特性会明确失败。

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
2. 在“图层”模式搜索、选择、显示或隐藏图层；右侧可检查语义、角色左右、bbox、置信度和 QA。
3. 在“关节”模式拖动关节，或在右侧输入 X/Y。坐标使用源画布像素，原点在左上，Y 向下。
4. 使用参考图、骨骼、预览透明度和缩放控件比较 setup 状态。
5. 填写校正备注后点击“保存校正”，或按 `Ctrl+S`。

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
- `schemas/layer-manifest-v1.schema.json`：规范化 RGBA 图层与语义、offset、QA 的 authoring 合同；
- `schemas/rig-ir-v1.schema.json`：版本中立的骨骼、slot、attachment 与有限动画合同。

Layer manifest 与 RigIR 是下游流水线合同；当前 UI 不会自动生成完整 RigIR，也不会把它冒充为某一 Spine 版本。RigIR 对不支持特性的策略固定为 `fail`，防止 constraint、mesh 或 timeline 被静默丢弃。

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

用当前人工复核关节生成诊断误差报告：

```powershell
python -m autospine_workbench evaluate-pose seethrough_output `
  .\workspace\analysis\seethrough_output\pose-observations\<sha256>.json `
  --workspace .. `
  --state-root .\workspace
```

COCO17 准备、导入、融合和评估步骤见 [导入并评估 COCO17 四肢姿态](docs/how-to-import-and-evaluate-pose.md)；已有 canonical 输入见 [使用 pose-alpha 生成四肢候选](docs/how-to-run-pose-alpha.md)；机器合同见 [姿态 adapter 与评估参考](docs/pose-adapter-reference.md) 和 [Pose observations v1/v2 参考](docs/pose-observations-reference.md)。

从当前已复核 revision 发布不可变的 region attachment bundle：

```powershell
python -m autospine_workbench materialize-manifest seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

对版本中立 RigIR 做语义检查：

```powershell
python -m autospine_workbench validate-rig .\path\to\rig.json
```

raw COCO17、canonical pose、评估报告和候选分别写入 `pose-adapter-inputs/`、`pose-observations/`、`pose-evaluations/` 和 `joint-candidates/`；manifest bundle 写入 `workspace/builds/layer-manifest/<project-id>/<sha256>/`。路径中的哈希来自 canonical 内容，相同输入不会产生相互覆盖的可变结果。`audit-bbox-heuristic` 和 `pose-alpha-limb-fusion` 都只输出 `heuristic_score`，不是经过标定的概率或模型置信度；后者始终保留原始 pose，并把 alpha 作为有限幅度的软证据。评估报告固定为 `diagnostic`，不内置合格阈值或自动左右修复。

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

API 响应带 `Cache-Control: no-store`。只接受 loopback Host；CORS 也只回显 loopback origin。除 `PUT overrides` 外，API 不提供写操作。

## 运行测试

完整 schema 测试需要可选的 `jsonschema`：

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

如需 Pillow/NumPy 图像比较加速，可安装 `python -m pip install -e ".[analysis]"`；不安装时仍有标准库 PNG 解码路径。

未安装 `jsonschema` 时，标准库运行与大部分测试仍可执行，完整 Draft 2020-12 实例校验会标记为 skipped。若仓库中存在两份真实 See-through audit，测试还会固定表示层差异和真实可见差异的区分：透明 RGB 与扁平背景造成的巨大 raw RGBA MAE 不会直接判为视觉失败；背景匹配后的可见颜色差异仍会失败。第 5 channel、空且隐藏图层、左右语义歧义与缺失部位仍需人工复核。

## 数据与恢复

- audit JSON、PSD 和 PNG 被视为不可变输入。
- 每次保存先写 `<state-root>/overrides/<project-id>/history/rNNNNNN.json`，再以原子替换更新 `latest.json`；历史快照不会被后续 revision 改写。
- `latest.json` 丢失时会从 history 恢复最新 revision；旧版 `<state-root>/overrides/<project-id>.json` 会被只读兼容，并在下一次保存时迁移，不会原地改写。
- 若要恢复旧 revision，先停止服务，备份整个项目 override 目录，再将目标历史快照作为新的、经过校验的 revision 提交；当前界面尚未提供历史浏览/回滚按钮。
- validation 的 `valid=true` 仅表示结构和本地资产检查没有硬错误，不等于美术、遮挡补全、pivot、mesh 或动画通过视觉验收。

## 下一阶段开发顺序

P0 合同加固已经贯通：`stage-scoped analysis → immutable candidate → candidate-bound revision → deterministic resolved snapshot`。外部 pose、alpha 四肢候选和 manifest 工件也已具备版本中立合同。后续按以下顺序推进：

1. **姿态 runner 与真实评估集**：COCO17 固定输入、显式 view/mirror/character-side adapter 和人工误差报告已经完成；下一步为选定的 Anime/ONNX/MMPose runner 产出该合同，冻结真实模型 revision，并在两份样本与新增标注集上记录基线，不把参考点回灌 smoke 当作模型精度。
2. **接触几何候选与比较 UI**：在现有连通域基础上增加 torso/arm、pelvis/leg、leg/foot 接触簇，并让用户接受、调整、拒绝或标记不可观测；宽袖、长裙、融合双腿和遮挡关节继续保留多解与证据回看。
3. **region-first RigIR 编译**：把已发布 Layer Manifest 和确认关节编译为规范骨角色、slot、draw order 与 region attachment；先做 setup 合成回归，不在这一阶段引入 mesh。
4. **绑定与动作探针**：只对 region 无法连续弯曲的上臂、前臂、大腿、小腿生成轮廓网格、两骨权重和 LBS 预览，并用抬臂、屈肘、抬腿、屈膝四个极值探针暴露遮挡补全、翻三角与接缝问题。
5. **通用动画重定向与版本适配**：动画库只引用 `humanoid-v1`；目标 Spine 版本仅进入 adapter，不支持的 mesh、deform、constraint 或 draw order 必须失败并报告。

面部锚点、头发弹簧和实时追踪映射可以作为独立模块接到同一规范骨角色上；四肢扩展的关键不是增加更多屏幕坐标映射，而是建立 bind pose、父子骨、权重和重定向空间。

## 非目标与已知边界

当前版本不负责：

- 运行 See-through 推理、选择 seed、编辑 PSD 或自动清理图层；
- 下载或运行具体姿态模型；`import-pose` 只转换经过哈希固定且已还原到原画布的 COCO17 输出，当前 UI 也尚未加载离线候选工件；
- 自动解决 `head-obj`、`objects`、合并肢体等歧义语义；
- 证明遮挡补全符合解剖或在大幅动作下不会露馅；
- 自动生成 mesh、权重、deform、IK、约束或动态 draw order；
- 生成眨眼/口型素材、简单动画或通用动画重定向；
- 导出 Spine JSON/atlas/PNG、判断真实 Spine 版本或集成官方 Spine runtime；
- 代替输入素材、训练数据或模型权重的许可证与商业使用审查；
- 多用户权限、远程协作或生产部署。

项目中显示的骨架来自 bbox/语义启发式，`requires_review=true`。只有在语义、左右、pivot、层级、合成回归和动作探针均通过后，才能把人工确认结果交给后续 RigIR/导出阶段。

代码职责、依赖方向、文件长度预算和阶段完成门禁见 [docs/architecture.md](docs/architecture.md)。
