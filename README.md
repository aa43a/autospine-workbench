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
- 通过只读验证 API 检查画布、图层 ID、资产路径和骨架结构。

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

`side` 使用 `left`、`right`、`center`、`bilateral` 或 `unknown`，始终表示角色自身左右。`visible` 只定义 setup/复核预览可见性，不会改写 PNG。关节与 pivot 必须是有限数，并位于画布内。

JSON Schema 位于：

- `schemas/override-patch-v1.schema.json`：在线 API 的 canonical patch；
- `schemas/layer-manifest-v1.schema.json`：规范化 RGBA 图层与语义、offset、QA 的 authoring 合同；
- `schemas/rig-ir-v1.schema.json`：版本中立的骨骼、slot、attachment 与有限动画合同。

Layer manifest 与 RigIR 是下游流水线合同；当前 UI 不会自动生成完整 RigIR，也不会把它冒充为某一 Spine 版本。RigIR 对不支持特性的策略固定为 `fail`，防止 constraint、mesh 或 timeline 被静默丢弃。

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

未安装 `jsonschema` 时，标准库运行与大部分测试仍可执行，完整 Draft 2020-12 实例校验会标记为 skipped。若仓库中存在两份真实 See-through audit，测试还会固定以下发现：

- 1024×1024 样本的严重 composite mismatch 不能被误判为通过；
- 1200×1800 样本的第 5 channel、空且隐藏的 `handwear`、`hand-r/l`、`head-obj`、缺失 `legwear` 与未拆分双侧五官仍需人工复核。

## 数据与恢复

- audit JSON、PSD 和 PNG 被视为不可变输入。
- 保存采用临时文件、flush/fsync 和原子替换。
- state 文件位于 `<state-root>/overrides/<project-id>.json`。
- 删除某个 override 文件会使该项目回到 revision 0；操作前应自行备份，因为工作台没有版本历史界面。
- validation 的 `valid=true` 仅表示结构和本地资产检查没有硬错误，不等于美术、遮挡补全、pivot、mesh 或动画通过视觉验收。

## 下一阶段开发顺序

当前工作台是第一条可运行纵向链路：`See-through audit → 人工复核 → revision override`。建议在这个合同上继续推进，而不是直接把启发式坐标写成某个 Spine 版本：

1. **规范化 Layer Manifest**：把已确认的语义、角色自身左右、offset、pivot、排除/拆分决策固化为 `autospine-layer-manifest/v1`，保持源 PSD 和审计结果不可变。
2. **四肢锚点估计**：引入人体姿态关键点作为候选，再以图层 alpha 轮廓、连通域和 torso/hand/foot 接触关系校正 shoulder、elbow、wrist、hip、knee、ankle；所有候选都输出 confidence 和来源，低置信度回到本界面复核。
3. **绑定与动作探针**：首轮采用 region attachment 与刚性父子骨验证层级、pivot 和 draw order；随后只对需要弯曲的上臂、前臂、大腿、小腿生成轮廓网格、两骨权重和 LBS 预览，并用抬臂、屈肘、抬腿、屈膝四个探针暴露遮挡补全问题。
4. **通用动画重定向**：动画库只引用 `humanoid-v1` 的规范骨角色；按 bind-pose 骨长、局部旋转和角色自身左右重定向，位移按骨长比例缩放，接触动作再用 IK/脚底约束修正。
5. **版本适配导出**：先生成版本中立 RigIR，并对 mesh、deform、constraint、draw order 建立显式能力矩阵；只有目标 Spine 版本确定后才进入对应 adapter，遇到不支持特性必须失败并报告，不能静默丢失。

面部锚点、头发弹簧和实时追踪映射可以作为独立模块接到同一规范骨角色上；四肢扩展的关键不是增加更多屏幕坐标映射，而是建立 bind pose、父子骨、权重和重定向空间。

## 非目标与已知边界

当前版本不负责：

- 运行 See-through 推理、选择 seed、编辑 PSD 或自动清理图层；
- 自动解决 `head-obj`、`objects`、合并肢体等歧义语义；
- 证明遮挡补全符合解剖或在大幅动作下不会露馅；
- 自动生成 mesh、权重、deform、IK、约束或动态 draw order；
- 生成眨眼/口型素材、简单动画或通用动画重定向；
- 导出 Spine JSON/atlas/PNG、判断真实 Spine 版本或集成官方 Spine runtime；
- 代替输入素材、训练数据或模型权重的许可证与商业使用审查；
- 多用户权限、远程协作或生产部署。

项目中显示的骨架来自 bbox/语义启发式，`requires_review=true`。只有在语义、左右、pivot、层级、合成回归和动作探针均通过后，才能把人工确认结果交给后续 RigIR/导出阶段。
