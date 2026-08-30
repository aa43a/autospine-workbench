# AutoSpine Workbench 简明操作手册

这份手册面向第一次使用工作台的人。目标是先从统一入口找到所需功能，再完成一次最小但完整的操作：打开 See-through 样本，复核图层和骨骼，处理关节候选，然后把结果保存为新的 revision。

P9 Kimodo 动作进入策略复核时，可从功能入口中心打开 `Motion Policy 自动工作流`。普通用户只需确认项目：存在推荐项时页面会自动选择并加载对应的 exact package，重算 SHA-256 和 candidate inventory。随后拖动时间轴或点击“一键采用全部安全建议”，只让系统覆盖 `state=candidate`、证据完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot candidates，再处理少量异常并做一次最终明确采纳。三份 JSON 与 SHA 手工输入只在“专业模式”中保留。Depth、`rejected_*`、缺证、非有限值和超阈值项不会自动批准；最终确认后，本机服务会编译、发布并精确复验 P9，review input 下载仅作备份。完整流程见 [复核并发布 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

P9 已采用后，从功能入口中心打开 `身体摆动设置`。页面会自动选择无歧义的项目/package，由服务端 exact replay P3/P5/P9 并准备 P10.0 候选；普通用户不用选 JSON、填写 SHA 或寻找目录。先看角色合成图和四骨示意，再播放、拖动时间轴并调整少量参数。页面上的推荐只是 `unvalidated_draft`，时间轴操作不会自行批准；保存、拒绝和无法判断三个按钮都会先显示项目、动作与后果，取消弹窗不会写入。只有在弹窗中点击“确认并提交”才形成 P10.1 revision。P10.2 会自动运行七项结构检查，并用 P10.2a `0/8…8/8` 统一 gain 诊断帮助区分“幅度可调”与“基础结构仍越界”；该诊断不会自行批准或保存参数。

P9 成功后可直接进入 `Seam Anchor 复核台`。页面会自动加载 package、绑定 current head、把明确的唯一候选和不可观测项填入可撤销草稿，并用图片叠加代替默认展示 SHA/JSON；普通操作者只需检查多候选和最后明确确认。若六条关系均可用，同一次确认会继续生成并精确读回 P10.5c 静态接缝集。完整流程见 [复核 P10.5b 静态接缝锚点](how-to-review-seam-anchors.md)。

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
- 搜索全部 66 个 CLI、六个任务页面和尚未实现的规划项；
- 直接打开绑定复核、P9 Motion Policy、身体摆动设置、P10.2 结构探针、Body-sway 视觉复核和 Seam Anchor 复核页面；
- 复制精确的 `python -B -m autospine_workbench <command> --help` 帮助命令；
- 通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开对应仓库文档。

浏览器不会执行 CLI，也不会选择不明确的 `latest`。P9 与身体摆动页面只会自动选择服务端列出的确定性 exact package，并由服务端补齐、重算上游身份；P9 成功回执可用 `package_id` 自动进入 Seam，Seam 的四段地址只在专业审计模式中手填。Body-sway Runtime 视觉复核目前仍需要精确地址；从 `package_id` 自动生成临时预览、经许可确认启动 capture 并带入 exact 地址属于下一阶段规划，尚未实现。首次使用 CLI 时，先在项目根目录的当前 PowerShell 执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

文档查看器只读获取 `/docs/<文件名>.md`，并把内容作为纯文本显示，不解析 Markdown 中的 HTML，也不会执行文档内容。

然后粘贴入口中心复制的帮助命令，根据 `--help` 自己补充必填参数。计划项只是开发路线入口，不能当作已经可用的功能。

完整入口清单见[功能与入口参考](capability-reference.md)。

### P9：用自动工作流完成一次动作复核

1. 打开 <http://127.0.0.1:8765/motion-policy-review.html>。
2. 查看“项目 / 动作”。页面有推荐项时会自动选择并立即加载；如果不是目标角色，再从同一列表切换。不要用下载目录里的同名文件覆盖来区分 A/B。
3. 等待状态显示 exact package、SHA 重算和预检均通过。普通流程无需选择文件或填写 SHA。
4. 拖动时间轴查看整段动作。保持“拖动时采用安全建议”开启时，一次拖动会采用经过范围内尚未决定的安全 Foot 建议；也可点击“一键采用全部安全建议”。两种操作都可以撤销。
5. 只处理“需要人工处理”的项目。Depth、`rejected_*`、缺证、非有限值、超 80% 阈值和需要 `adjust` 的项目不会自动批准。重点窗口只是帮你定位边界或极值，不会单独阻止满足安全规则的 Foot 建议。
6. 确认覆盖完整后，点击“确认并发布到本地”。这一次点击表示你把当前辅助结果采纳为 Motion Policy Decision v1 的 `human` review input；本机服务随后自动执行“校验 → 编译 → 发布 → 精确复验”。
7. 等待成功或“已复用”回执出现，然后点击“进入接缝复核”。无需下载文件、复制 SHA 或选择 JSON；该入口只完成精确证据交接，不会自动批准任何接缝关系。

自动选择项目、预检通过或覆盖率达到 100% 都不会自行发布；必须有最后一次明确人工确认。若要载入外部副本、独立运行 CLI 或排查身份问题，再展开“专业模式：手动导入 JSON 与 SHA”。

### P10.0–P10.1：设置身体摆动

1. 打开 <http://127.0.0.1:8765/idle-behavior-review.html>。
2. 查看页面自动选择的“项目 / 动作”。如果只有一个推荐项，页面会直接加载；如果存在多个同项目/clip 的有效 adoption，系统不会猜测，需从列表明确选择。
3. 等待服务端 exact replay 完成。服务冷启动会完整 replay；同一服务进程可以复用经过全字节 seal 重验的非权威 chain 缓存。普通流程不选择文件、不填写 SHA；原始身份、revision 和历史只在“技术详情”中显示。缓存不会保存 history、current head 或 CAS。
4. 查看角色合成图和 `pelvis-spine`、`spine-chest`、`chest-neck`、`neck-head` 四骨示意。播放或拖动时间轴，检查摆动方向、幅度和循环是否符合角色。
5. 用页面提供的少量通俗参数调整幅度与节奏。推荐值、播放结果和时间轴停留位置都只是 `unvalidated_draft`，不会在后台批准。
6. 满意后先勾选人工确认，再点击“保存 P10.1，下一步运行结构探针”。如需停止使用候选，可选择“不使用身体摆动”或“当前无法判断”。三个按钮都会打开二次确认弹窗，显示当前项目、动作、决定类型和后果；按 Esc、点击遮罩或点击“取消”均不发送请求。只有点击“确认并提交”才会以实时 current-head CAS 写入 candidate-bound P10.1 revision；若另一窗口先保存，刷新历史并重新确认，不要沿用旧基线。
7. 若保存的是参数，成功回执应显示 `pending_probe`，此时点击“打开 P10.2 自动结构探针”；“不使用”或“当前无法判断”会得到 `not_applicable`，不进入 P10.2。不要把任何 P10.1 决定当成 Runtime、视觉、动态接缝或发布批准。

### P10.2：自动运行结构探针

1. 打开 <http://127.0.0.1:8765/body-sway-probe.html>，或从 P10.1 成功回执进入。页面会优先选择 URL 指定的 package；没有指定时，只自动选择唯一 `adjust/pending_probe` current head。
2. 等待自动重放和结构编译完成。首次冷加载或首次项目发现可能较慢；同一服务进程会对完整 package、candidate、current revision/decision 与算法 profile 都相同的结果使用有界缓存，但每次仍会在前后重放 exact 链并检查 current head。缓存不落盘、不跨服务重启，也不代表批准。页面不要求选择文件、填写 SHA 或逐项点击批准；切换项目或重读也不会写 revision。
3. 查看顶部结论、角色图和四骨时间轴。拖动时间轴只切换有界采样见证；它不会批准 tick，也不代表穷尽全部采样。
4. 查看五项自动结构卡：loop、FK、mesh、画布和共享索引。接缝与 Runtime 视觉两卡固定列为后续门禁，不能因为前五项通过而当作已发布。
5. 若显示“结构拒绝”，查看 P10.2a 的 `0/8…8/8` 统一 gain 诊断。`0/8` 只是“移除 body-sway 后是否仍越界”的测试，不能保存为动作。只有非零 gain 的 sampled canvas 和 geometry 都通过时，系统才会给出 `unvalidated_draft`；把它带回 P10.1 后，仍须在确认弹窗中保存一个新 revision，再回本页重跑 P10.2。
6. 若所有非零候选都失败，特别是 `0/8` 也失败，不要继续盲目调小幅度；应修复画布余量、attachment/骨绑定或上游动作。若显示“需要 Runtime 视觉复核”，才可开始准备 P10.3 capture，但 release 仍保持 blocked。
7. 专家详情中的 canonical report 与唯一文件名下载只用于备份/排障；普通流程无需下载后重新选文件。

当前真实数据中，`seethrough_output` 的 P10.1 r1 是不可观测、不进入探针；`seethrough_output_5` 的 r2 是唯一 ready 项，但 reviewed gain `8/8` 有 `334/334` 个画布失败 tick，`0/8` 仍有 `333/334` 个，主要涉及 `layer-006-objects`、`layer-000-back-hair` 与 `layer-008-hand-r`。这证明纯参数无法修复；先处理结构输入，不要绕到 P10.3。

### P10.5：用图片完成接缝复核

1. 从 P9 成功或“已复用”回执点击“进入接缝复核”。页面只接收该回执的 `package_id`，自动加载对应项目、候选、图片证据和 current head；不要复制 SHA 或选择 JSON。
2. 先看每处接缝的叠加图：青色是 parent，紫色是 child，虚线框是 contact 范围，同编号圆点与连线是一对锚点。SHA、contact 数字、locator 表和单层原图默认收在“技术详情”中，普通复核无需展开。
3. 系统会把唯一完整候选填成 `accept` 草稿，把源图不可观测项填成带原因的 `unobservable` 草稿。所有自动结果都可以撤销，且最后确认前不会写入 revision。
4. 若一处有多个候选，逐张比较叠加图。系统可能标记“建议重点查看”，但这不等于批准；点击你认可的候选后，页面才会形成该项的 `accept` 草稿。需要时可改为“手动调整”“候选不正确”或“源图不可见”。
5. 确认页面显示六项已检查后，点击“确认复核并生成静态接缝集”。这是唯一会提交人工决定的最终操作；自动加载、自动草稿和 6/6 进度都不会代替这次点击。
6. 若六条关系全部 `accept/adjust` 且页面来自 P9 package，本机随后自动执行 P10.5c 编译、内容寻址发布和 exact readback。成功后可下载 path-free 精确复验回执；只有精确 P10.4b2 动作域也已闭合时，才能进入“动态接缝验证”。
7. 若页面提示“P10.5b 已保存；P10.5c 未完成”，只点击“仅重试生成静态接缝集”。不要再次提交六项人工决定；页面会保留已经写入的 revision。若结果包含 `reject/unobservable`，页面只保存阻塞结论，不会生成不可信的 P10.5c。

当前真实状态要单独理解：样本 A 的 P10.5b revision 2 已以 `6/6 accept`、`24` 个 anchor pairs 取代 revision 1；对应 P10.5c 静态接缝集也已发布并通过 exact replay，无需重复提交六项决定。该结果不表示动态接缝、Runtime 等价或视觉接缝质量已经通过；这些门仍为 blocked。A 的 current P10.1 也仍不适用，须回设置页形成可探针 revision。样本 B 在 `8/8` 和 `0/8` 都被画布越界拒绝，且左右髋/脚踝共四条静态关系不可观测；参数、画布结构与静态 seam 是不同 blocker，自动流程不会把它们改成通过。

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
- 从已采用的 P9 链自动选择项目和 exact package，在“身体摆动设置”中用角色合成图、四骨示意、播放/时间轴和少量参数准备 P10.0 草稿；同进程 exact-chain 缓存命中仍全字节重验，三个决定按钮均经项目/动作/后果二次确认，取消零写入；
- 从 current P10.1 head 自动推荐唯一可探针项目，在 P10.2 页面只读编译七项结构报告和 P10.2a `0/8…8/8` 零权威诊断，并以通俗卡片、角色图和四骨采样见证显示结果；有界 derived cache 只复用完整 root/address/candidate/head/profile 身份相同的可重建结果，仍执行前后 exact replay/head 检查；
- 从独立页面完成人工 Body-sway still；从 P9 package 自动进入 Seam Anchor 页面，以叠加图、确定性建议草稿和一次最终确认完成 P10.5b，并在 ready 时继续 P10.5c exact publication/readback；
- 在 P9 页面完成一次明确 human adoption 后，由本机编译 decision/reviewed policy、原子发布 MotionInstance v2 六文件 bundle，并立即 exact verify；CLI 仍可独立复验，review input 下载仅作备份；
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

**P9-real-kimodo-policy-adoption** 对当前 `wave-left-v1` 的 A/B 已关闭，P10.2/P10.2a 自动诊断入口也已交付。项目 A 的 P10.5c 静态集已闭合，但 current P10.1 r1 为不可观测；项目 B current r2 可探针，却在 `8/8` 和 `0/8` 均有大面积画布越界，同时四条下肢 seam 仍不可观测。当前应让 A 回 P10.1 形成可探针 revision，让 B 修复画布、attachment/骨绑定或上游动作后重跑 P10.2；不能再把单纯调小 gain 当成充分修复。只有非拒绝结果才进入 P10.3a–P10.3c → P10.4a → P10.4b1 → P10.4b2 → P10.5d。P10.3 package-centric 自动 capture 仍是未实现规划。对新的 Kimodo 输入，仍应先运行零写入准入审计：

```powershell
python -B -m autospine_workbench audit-kimodo-pilot-intake `
  <raw.npz> <sidecar.json> <map.json> <camera.json> `
  --checkpoint-manifest <checkpoint.manifest> `
  --generation-request <generation-request>
```

该命令要求 `producer.status=recorded`，闭合两份 provenance 原件 SHA，在内存重跑 P7 结构编译并检查 camera/map；它不写 state、不认证 checkpoint、不批准动作质量，也不生成 P7/P8/P9 bundle。完整准备步骤见[审计真实 Kimodo Pilot 输入](how-to-audit-real-kimodo-pilot-intake.md)。

继续当前 `wave-left-v1` 时，不要重复 P9 adoption 或扫描 P5 地址；除非输入、算法或人工决定发生版本化变化，否则沿用 handoff 中已复验的 P9 双 SHA。[Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html)仍用于新的项目或新 review revision；CLI 只用于独立专业复验或无浏览器 exact 链。下列命令用于复验或排障：

如果新绑定或语义修正已经改变 P3/P4/P5，不要把旧 P9 policy、candidate 或 human decision 复制到新链。维护者应运行 `prepare-motion-policy-review-draft`，使用一个从未存在的新 namespace；它会自动重生 Kimodo evidence、standalone Foot candidates 和 pending Depth proposal。命令完成不表示已批准：还需先复核 proposal、显式形成正式 Depth policy，再生成 Depth candidates 并进入 Motion Policy 页面的最终人工确认。CLI 回执只显示 namespace、project、幂等复用状态和内容 SHA，不显示本机目录。详细参数和输出文件见[准备新的 Motion Policy 复核草案](how-to-prepare-motion-policy-review-draft.md)。

```powershell
python -B -m autospine_workbench compile-motion-retarget --help
python -B -m autospine_workbench verify-motion-retarget --help
python -B -m autospine_workbench compile-kimodo-policy-evidence --help
python -B -m autospine_workbench prepare-motion-policy-review-draft --help
python -B -m autospine_workbench probe-foot-lock --help
python -B -m autospine_workbench probe-depth-order --help
```

intake report SHA、P7/P8 SHA 和 builtin `wave.left` 地址都不能作为 P9 reviewed-motion 地址填入 readiness 请求；当前 A/B 的正确双 SHA 只从 pilot handoff 读取。

随后仍可运行冻结的 readiness v1 只读预检，查看两份目标项目尚缺哪些 exact 地址：

```powershell
python -B -m autospine_workbench audit-body-sway-spine42-v3-readiness `
  --manifest .\examples\p10-spine42-v3-readiness\real-see-through.request.json `
  --state-root .\workspace `
  --document-only
```

readiness v1 的 Schema、哈希和 checkpoint 语义已经冻结；即使 P10.7c 已交付，第八项仍固定为 `p6_setup_golden_comparison_not_declared`。仓库 baseline 仍把 P9 与下游地址设为 `null`，所以直接运行会继续报告未声明；这不推翻当前真实 P9/P10 状态。A 缺新的可探针 P10.1 与后续动作域；B 缺 P10.2 结构修复，并另受四条下肢 seam blocker 约束。Runtime 基础设施不能绕过这些更早门禁。

P10.7c 的独立入口已经可从功能中心复制，也可直接查看帮助：

```powershell
python -B -m autospine_workbench compare-body-sway-spine42-v3-setup-golden --help
```

该命令需要每个项目真实的 P10.7a 与 P10.7b capture 精确地址，并同时锁定既有 P6 export/runtime golden 合同。当前 A/B 的 P9 已通过，A 也已有静态 P10.5c，但 A 的动作域、B 的完整静态 seam 和两项目官方 capture 都尚未关闭；不要用全零请求模板、P7/P8/P5 地址或 fixture 声称真实比较通过。准备 canonical 请求和读取报告见[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。

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
- 身体摆动页的自动项目、推荐参数和时间轴预览已由人看图确认，并且只通过最终确认提交一次 P10.1；
- P10.2a 的离散 gain 结果只当作诊断；若采用非零 draft，已经回 P10.1 显式保存新 revision 并重新运行 P10.2；
- 接缝页面的建议高亮和自动草稿已由人看图确认，并且只执行了一次最终提交；若 P10.5c 失败，只重试 publication；
- 前端与相关 Python 测试通过；
- 没有把结构证明写成视觉、官方 Runtime 或发布通过。
