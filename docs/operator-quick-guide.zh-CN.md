# AutoSpine Workbench 简明操作手册

这份手册面向第一次使用工作台的人。目标是先从统一入口找到所需功能，再完成一次最小但完整的操作：打开 See-through 样本，复核图层和骨骼，处理关节候选，然后把结果保存为新的 revision。

> 工作台是本地人工复核工具，不是“一键生成可发布 Spine 动画”的工具。看到结构检查通过、探针 `compiled` 或锚点距离合格，都不能据此认定视觉效果、官方 Spine Runtime 或发布许可已经通过。

## 1. 启动工作台

要求：Windows PowerShell、Python 3.11 或更高版本。

打开 PowerShell，执行：

```powershell
cd E:\proj\unusual\localset\autospine-workbench
.\run.ps1
```

保持这个 PowerShell 窗口开启。看到服务已启动后，用浏览器打开：

<http://127.0.0.1:8765/>

当前工作区正常时，项目下拉框中应出现两个示例：

- `seethrough_output`
- `seethrough_output_5`

停止服务时，回到 PowerShell 窗口按 `Ctrl+C`。

### 端口被占用时

换一个本机端口启动：

```powershell
.\run.ps1 -Port 8766
```

然后打开 <http://127.0.0.1:8766/>。

不要把服务绑定或转发到局域网、公网。工作台没有用户认证，只供本机使用。

## 2. 从功能入口中心选择功能

启动后优先打开：

<http://127.0.0.1:8765/workflow-hub.html>

“功能入口中心”提供：

- 按 P0–P10 阶段、入口类型和状态筛选；
- 搜索全部 63 个 CLI、三个任务页面和尚未实现的规划项；
- 直接打开绑定复核、Body-sway 视觉复核和 Seam Anchor 复核页面；
- 复制精确的 `python -B -m autospine_workbench <command> --help` 帮助命令；
- 通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开对应仓库文档。

浏览器不会执行 CLI，也不会替你选择 `latest`、填写项目或补齐 SHA。首次使用 CLI 时，先在项目根目录的当前 PowerShell 执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

文档查看器只读获取 `/docs/<文件名>.md`，并把内容作为纯文本显示，不解析 Markdown 中的 HTML，也不会执行文档内容。

然后粘贴入口中心复制的帮助命令，根据 `--help` 自己补充必填参数。计划项只是开发路线入口，不能当作已经可用的功能。

完整入口清单见[功能与入口参考](capability-reference.md)。

## 3. 打开一个样本

1. 在页面顶部的“项目”下拉框选择 `seethrough_output` 或 `seethrough_output_5`。
2. 等待合成图、图层列表和骨骼覆盖显示出来。
3. 先看右侧“QA 警告”。警告是复核线索，不等于自动判定结果。
4. 如果画布大小不合适，按 `0` 适配画布，或使用 `+`、`-` 缩放。

切换项目前先保存。若当前有未保存修改，页面会要求确认；继续切换会放弃这些未保存修改。

## 4. 复核图层

先保持画布上方的“图层”模式处于选中状态。

1. 在左侧搜索框按名称、语义或 QA 查找图层。
2. 单击列表中的图层；也可以在画布上单击图层。
3. 用眼睛图标显示或隐藏图层，检查遮挡和归属。
4. 在右侧检查并按需修改：
   - “语义角色”：例如头、躯干、手臂或腿对应的语义 token；
   - “角色左右”：这里始终指角色自身的左、右，不是观看者左右；
   - “处理决策”：保留、排除、拆分或待复核；
   - `Pivot X/Y`：旋转中心，必须位于画布内；
   - “目标骨”：该图层准备绑定到的骨。
5. 信息确认后，点击“确认语义、Pivot 与目标骨”。

“画布可见”只控制 setup/复核状态并写入 override，不会修改原始 PNG 或 PSD。遇到空图层、合并肢体、遮挡补全不完整或左右不确定时，不要为了消除警告而猜测；保留“待复核”或记录备注更安全。

### 双侧图层的切分复核

当图层标记为“双侧 / 待拆分”且处理决策为“拆分”时，右侧可能出现“切分预览审查”。比较预览的两部分、面积和目标骨后，选择：

- “接受当前切分”：确认这个具体算法预览；
- “拒绝当前切分”：填写原因后拒绝。

切分算法或输入内容发生变化后，旧决定可能失效，需要重新复核。这是预期的安全行为。

## 5. 复核骨骼和关节

1. 点击画布上方的“关节”模式。
2. 单击骨骼上的关节点，右侧会显示关节名称、坐标和置信度。
3. 拖动关节点，或直接输入 `X/Y` 坐标进行校正。
4. 精细调整可使用：
   - 方向键：移动 1 px；
   - `Shift` + 方向键：移动 10 px；
   - `Alt` + 方向键：移动 0.1 px。
5. 若要撤销该关节的人工坐标，点击“恢复自动推断位置”。

调整时同时观察参考合成图、图层轮廓和整条骨链。当前自动位置来自姿态、alpha 几何或 bbox/语义启发式，仍需要人工判断。

## 6. 处理关节候选

选择关节后，右侧“候选审查”会显示当前候选 artifact、候选方法、可观测性和固定几何证据。先选候选，再选择一种处理方式：

- “接受候选”：采用所选候选的精确坐标；
- “按当前位置调整”：先拖动关节或输入坐标，再提交当前位置；
- “拒绝候选”：拒绝所选候选，必须填写理由；
- “标记不可观测”：当遮挡或图层不足以可靠定位时使用，必须填写理由，不要求存在候选点。

注意：

- 点击上述按钮只是把决定写入当前页面草稿；还要点击“保存校正”才会产生新 revision。
- 候选决定绑定候选内容 SHA。算法重新生成不同内容后，旧决定不会静默套用。
- “启发式分数”不是经过标定的概率，分数高也不等于美术结果正确。
- 若“固定几何证据”加载失败，不要盲目接受候选；先重试或排查工件。

### 页面显示“此项目还没有候选 artifact”

在新的 PowerShell 窗口进入项目目录，先发布基础审计候选：

```powershell
cd E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m autospine_workbench analyze-joints seethrough_output `
  --workspace .. `
  --state-root .\workspace
```

另一个样本把项目名改为 `seethrough_output_5`。命令完成后，回到页面刷新项目并重新选择样本。

需要导入 COCO17、结合 alpha 中轴线与接触证据时，请按照[生成并复核四肢候选](how-to-run-pose-alpha.md)操作；工作台本身不会下载或运行姿态模型。

## 7. 保存与 revision

1. 在右侧“校正备注”中记录仍需处理的问题。
2. 点击顶部“保存校正”，或按 `Ctrl+S`。
3. 等待状态变为“已保存”。
4. 检查顶部 revision 徽标，例如从 `r3` 变为 `r4`。
5. 刷新页面或重新选择项目，确认刚才的修改能够读回。

每次成功保存都会追加一个历史 revision，并更新当前状态：

```text
workspace/overrides/<project-id>/
├── latest.json
└── history/
    └── rNNNNNN.json
```

当前在线保存合同是 `autospine-workbench.override/v3`，会同时保留绝对关节、候选关节决定、bilateral split 决定和图层 authoring。不要使用旧 v2 示例删除 `split_decisions`。

保存后的 resolved authoring 状态使用冻结的 `autospine.resolved-project/v1`。它已有独立 JSON Schema 与严格 Python 语义 validator，会重算内容哈希、候选/拆分 provenance、实体交叉引用和派生 QA。普通操作者不需要额外运行一个 CLI；需要在 API 或编译器边界校验文档的开发者请查阅 [Resolved Project v1 参考](resolved-snapshot-reference.md)。未来 resolved 算法语义变化必须升级到 v2，不能让旧 revision 在 v1 标识下改变含义。

不要在服务运行时手工改写这些文件。原始 audit、PSD 和 PNG 也应保持不变。

### 出现 `409 revision_conflict`

这表示另一个页面或会话已经保存了更新版本。工作台不会用后保存的内容静默覆盖先保存的内容。

1. 点击“导出本地 patch”保留当前草稿。
2. 点击“加载最新并重放”。
3. 重新检查有冲突的字段。
4. 再次保存。

## 8. 常见问题

### `Uncaught ReferenceError: SVG_NS is not defined`

这通常说明浏览器执行的前端文件彼此不一致，缓存是需要先排除的原因之一。更新代码或修复完成后按顺序尝试：

1. 停止服务并重新运行 `.\run.ps1`。
2. 在工作台页面按 `Ctrl+F5` 强制刷新。
3. 若仍出现，打开浏览器开发者工具，在 Network 面板勾选“Disable cache”，再刷新一次；也可清除此站点 `127.0.0.1` 的缓存。
4. 确认地址仍是当前启动端口，而不是旧标签页或旧服务。
5. 若问题仍在，保留控制台的完整报错、`app.js` 行号和当前 Git commit，交给开发者定位。

这些步骤只排除旧资源或混合缓存，不能替代代码修复；不要仅因报错暂时消失就认定相关交互已验证。

### 页面打不开

- 确认运行 `run.ps1` 的 PowerShell 窗口仍然开启且没有报错。
- 确认 URL、端口与启动参数一致。
- 若提示找不到 Python，安装 Python 3.11+，或使用：

```powershell
.\run.ps1 -PythonExe "C:\path\to\python.exe"
```

### 项目列表为空

确认样本 audit 位于：

```text
E:\proj\unusual\localset\tmp\psd_audit\results\<project-id>\audit.json
```

同一目录还应包含合成图、contact sheet 和 `layers/` 下的图层 PNG。然后点击项目下拉框旁的刷新按钮。

### 保存失败或字段被标红

- Pivot 和关节坐标必须是有限数，并位于画布内。
- 语义角色只能使用界面允许的 token 字符。
- `adjust`、`reject` 和 `unobservable` 必须填写理由。
- 先查看页面顶部错误提示和右侧 QA，再修正具体字段。

## 9. 当前能做与不能做

当前可以：

- 自动发现已有 See-through audit 样本；
- 复核图层语义、角色左右、可见性、处理决策、Pivot 和目标骨；
- 查看并调整基础骨架，处理 pose/alpha/接触候选；
- 以内容地址保存候选证据，以 revision 保存人工决定；
- 生成并严格验证版本化的 Resolved Project v1 snapshot，同时保持历史 r5/r7 内容地址不变；
- 从独立页面完成人工 Body-sway still 与 Seam Anchor revision；
- 通过离线命令生成和验证版本中立的 Layer Manifest、RigIR、mesh、IK、MotionIR、P10.6a admission、MotionInstance v3 及 P10.7a Spine 4.2 v3 五文件 adapter 工件。
- 在操作者提供并确认有权使用官方 Spine Player 4.2.119 时，捕获 P10.7a 的固定 sampled raster 证据，复验不可变 capture，并编译逐 case、逐 setup attachment 的人工决定。
- 从 strict canonical 示例 Manifest 只读审计两份真实样本的 P3→P10.7b 前置；审计不会自动执行阶段、代替人审或授予发布权。
- 使用独立 P10.7c 命令，把精确 capture 中唯一的 opaque setup 帧与既有 P6 approved golden 做零写入 RGBA 对照；该入口已交付，但真实样本仍需先补齐外部前置。

当前不能据此自动完成：

- 运行 See-through、挑选 seed、修补 PSD 或清理图层；
- 无人复核地生成可靠绑定、权重和通用动画；
- 自动生成眨眼、口型、头发物理、实时追踪或自由形变；
- 保证大幅动作下没有露底、裂缝、错误遮挡或翻三角；
- 把结构探针、离散截图、sampled raster 指标、锚点点距或一次人工决定当作连续时间或完整发布验收；
- 在未提供并确认授权的官方 Spine Runtime 时声称 runtime 等价；
- 自动授予商业使用、发布许可或生成 Spine Editor 工程。

固定 Spine 4.2 profile 的 adapter 和验证链已经存在，但每个新 rig/clip 仍需分别完成 attachment 边界视觉回归、官方 Runtime 证据和许可审查。

### P3 Mesh 入口

在功能入口中心选择阶段 `P3`，可复制这两个帮助命令：

```powershell
python -B -m autospine_workbench compile-mesh-rig --help
python -B -m autospine_workbench verify-mesh-bundle --help
```

编译后回到主工作台底部的“P3 Mesh 证据”，显式选择 rig SHA 与 bundle SHA，再点击读取。这里显示的是 setup、权重热图、极值姿势和严格复验结果；它不是 mesh/weight 编辑器，也不会自动选中最新 bundle。

## 10. 当前阶段与下一开发入口

当前阶段是 **P10.7c-setup-regression**。先在项目根目录运行冻结的 readiness v1 只读预检：

```powershell
python -B -m autospine_workbench audit-body-sway-spine42-v3-readiness `
  --manifest .\examples\p10-spine42-v3-readiness\real-see-through.request.json `
  --state-root .\workspace `
  --document-only
```

readiness v1 的 Schema、哈希和 checkpoint 语义已经冻结；即使 P10.7c 已交付，第八项仍固定为 `p6_setup_golden_comparison_not_declared`，不能把 readiness 报告当作 setup 对照结果。当前结果是：A/B 都未声明真实 Kimodo P7/P8/P9 的 reviewed-motion 地址；A 还未声明 P10.5c 双 SHA，审计不读取 current review head，因此不能据此断言人审是否已经发生；B 的 P3 candidate 则证明有四条不可观测腿/脚 seam，必须修复上游语义/分层或另立 partial 合同。Runtime 已存在，但不是最早 blocker。请求格式、报告读取方式和权限边界见[审计两份真实样本的 Spine 4.2 v3 就绪状态](how-to-audit-spine42-v3-readiness.md)。

P10.7c 的独立入口已经可从功能中心复制，也可直接查看帮助：

```powershell
python -B -m autospine_workbench compare-body-sway-spine42-v3-setup-golden --help
```

该命令需要每个项目真实的 P10.7a 与 P10.7b capture 精确地址，并同时锁定既有 P6 export/runtime golden 合同。当前 A/B 尚受 Kimodo/P9、seam 和官方 capture 外部 blocker，因此不要用全零请求模板或 fixture 声称真实比较通过。准备 canonical 请求和读取报告见[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。

P0 Resolved Project v1、P10.6b MotionInstance v3 与 P10.7a Spine adapter bundle 均已完成。普通图层/关节复核不需要运行这些命令；开发 body-sway 动画编译链时，先按
[编译 P10.6a body-sway 动作消费准入](how-to-compile-body-sway-motion-consumer-admission.md)
把认证的 P10.5d probe 与精确 P9 MotionInstance v2 bundle 重新闭合。对应命令是：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-consumer-admission --help
```

随后按[编译并复验 P10.6b MotionInstance v3](how-to-compile-motion-instance-v3.md)保存完整
P10.6a 成功输出，编译并复验精确三文件 bundle：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-instance-v3 --help
python -B -m autospine_workbench verify-body-sway-motion-instance-v3 --help
```

然后按[编译并复验 P10.7a Spine 4.2 v3](how-to-compile-spine42-v3.md)生成并复验五文件
adapter bundle：

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3 --help
python -B -m autospine_workbench verify-body-sway-spine42-v3 --help
```

P10.7a 的发布前 head observation 仍不是永久审批权，成功结果也只声明 adapter 已发出。

P10.7b 的捕获、精确复验、raster 候选与人工 decision 基础设施已经可用。capture 需要外部
官方 Runtime 与显式许可确认；另外三个入口可从功能入口中心直接复制帮助命令：

```powershell
python -B -m autospine_workbench capture-body-sway-spine42-v3-runtime --help
python -B -m autospine_workbench verify-body-sway-spine42-v3-runtime --help
python -B -m autospine_workbench prepare-body-sway-spine42-v3-raster-review --help
python -B -m autospine_workbench submit-body-sway-spine42-v3-raster-review --help
```

完整流程见[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)。
目前仍需对两份真实 See-through 样本分别生成 P10.7a 输入、运行官方 Runtime capture，并逐
case、逐 attachment 完成人工决定。fixture 或单个样本不能替代这项验收；通过 sampled
decision 也不会证明连续时间安全，不会授予永久 head、可发布 timeline 或 release authority。
具备精确 capture 后，再按[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)
运行独立 setup 回归；该单帧对照同样不替代完整人工决定或发布门禁。
后续依赖、交付与风险见[后续开发路线](development-roadmap.md)。

## 11. 常用验证命令

以下命令都在项目根目录执行。

确认 CLI 可以加载：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m autospine_workbench --help
```

确认服务可以列出项目：

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/projects
```

运行与服务、候选和 override 相关的快速 Python 测试：

```powershell
python -m unittest `
  tests.test_server `
  tests.test_candidate_artifact_api `
  tests.test_override_candidate_integration `
  -v
```

运行前端测试：

```powershell
npm test --prefix web
```

运行完整 Python 测试（耗时较长）：

```powershell
python -m unittest discover -s tests -v
```

提交前检查补丁格式：

```powershell
git diff --check
```

缺少可选 `jsonschema` 时，部分完整 schema 实例测试会显示 `skipped`。这不等于失败，但也不能宣称完整 schema 验证已经执行。需要完整测试依赖时运行：

```powershell
python -m pip install -e ".[test]"
```

只验证 Resolved Project v1 时可运行：

```powershell
python -m unittest tests.test_resolved_snapshot_validation tests.test_resolved_snapshot_schema -v
```

其中语义 validator 测试不依赖 `jsonschema`；若该可选依赖未安装，命令会明确跳过 Schema 实例用例。只有输出显示实例用例实际执行并通过时，才能声明完成 Draft 2020-12 实例验证。

## 12. 建议的最小验收清单

一次操作完成前，至少确认：

- 已选对项目和角色自身左右；
- 所有关键图层都有明确处理决策；
- 关键关节已接受、调整、拒绝或标记不可观测；
- QA 警告已处理，或在备注中说明为什么暂不处理；
- 保存后 revision 增加；
- 刷新页面后修改可以读回；
- 前端与相关 Python 测试通过；
- 没有把结构证明写成视觉、官方 Runtime 或发布通过。
