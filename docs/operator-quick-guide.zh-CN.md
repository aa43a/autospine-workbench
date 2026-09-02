# AutoSpine Workbench 简明操作手册

这份手册面向第一次使用工作台的人。目标是先从统一入口找到所需功能，再完成一次最小但完整的操作：打开 See-through 样本，复核图层和骨骼，处理关节候选，然后把结果保存为新的 revision。

P9 Kimodo 动作进入策略复核时，可从功能入口中心打开 `Motion Policy 自动工作流`。普通用户只需确认项目：存在推荐项时页面会自动选择并加载对应的 exact package，重算 SHA-256 和 candidate inventory。随后拖动时间轴或点击“一键采用全部安全建议”，只让系统覆盖 `state=candidate`、证据完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot candidates，再处理少量异常并做一次最终明确采纳。三份 JSON 与 SHA 手工输入只在“专业模式”中保留。Depth、`rejected_*`、缺证、非有限值和超阈值项不会自动批准；最终确认后，本机服务会编译、发布并精确复验 P9，review input 下载仅作备份。完整流程见 [复核并发布 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

P9 已采用后，从功能入口中心打开 `身体摆动设置`。页面会自动选择无歧义的项目/package，由服务端 exact replay P3/P5/P9 并准备 P10.0 候选；普通用户不用选 JSON、填写 SHA 或寻找目录。先看角色合成图和四骨示意，再播放、拖动时间轴并调整少量参数。页面上的推荐只是 `unvalidated_draft`，时间轴操作不会自行批准；保存、拒绝和无法判断三个按钮都会先显示项目、动作与后果，取消弹窗不会写入。只有在弹窗中点击“确认并提交”才形成 P10.1 revision。P10.2 会自动运行七项结构检查，并用 P10.2a `0/8…8/8` 统一 gain 诊断帮助区分“幅度可调”与“基础结构仍越界”；当唯一问题只是旧素材框 containment 时，P10.2b 会进一步生成覆盖 setup、base 与 combined 动作包络的自动取景候选，仍须一次明确确认才形成取景 revision。

P9 成功后可直接进入 `Seam Anchor 复核台`。页面会自动加载 package、绑定 current head、把明确的唯一候选和不可观测项填入可撤销草稿，并用图片叠加代替默认展示 SHA/JSON；普通操作者只需检查多候选和最后明确确认。若六条关系均可用，同一次确认会继续生成并精确读回 P10.5c 静态接缝集。完整流程见 [复核 P10.5b 静态接缝锚点](how-to-review-seam-anchors.md)。

> 工作台是本地人工复核工具，不是“一键生成可发布 Spine 动画”的工具。看到结构检查通过、探针 `compiled` 或锚点距离合格，都不能据此认定视觉效果、官方 Spine Runtime 或发布许可已经通过。

## 1. 启动工作台

要求：Windows PowerShell、Python 3.11 或更高版本。

打开 PowerShell，执行：

```powershell
cd <autospine-workbench>
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
- 搜索全部 CLI、任务页面和尚未实现的规划项；
- 直接打开绑定复核、P9 Motion Policy、身体摆动设置、P10.2 结构探针、P10.3 官方 Runtime 自动采集、P10.3c 视觉复核、P10.4a v2 自动准入、P10.4b v2 自动安全分析和 Seam Anchor 复核页面；
- 复制精确的 `python -B -m autospine_workbench <command> --help` 帮助命令；
- 通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开对应仓库文档。

浏览器不会选择不明确的 `latest`。P9 与身体摆动页面只会自动选择服务端列出的确定性 exact package，并由服务端补齐、重算上游身份；P9 成功回执可用 `package_id` 自动进入 Seam。P10.3 页面也按 package 自动闭合 Preview v2、当前 P10.1/CaptureFraming 和 Runtime 环境；完成的异步 job 自动把 exact execution 地址带入 P10.3c，复核通过后又以同一 `job_id` 依次进入 P10.4a v2 准入页和 P10.4b v2 安全分析页。普通用户不手填文件或 SHA。首次使用专业 CLI 时，先在项目根目录的当前 PowerShell 执行：

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
3. 等待服务端 exact replay 完成。页面会把 `project_id` 传给 list/detail 以只发现当前项目；P9 replay 对相同 key 使用 single-flight，同一进程还会复用经过全字节 seal 重验的非权威 chain/split 缓存。全项目 warm 实测约 `0.61 s`，单独 A 项目约 `0.28 s`；服务冷启动仍需约 `18 s` 完整 replay A 的 P9 链。普通流程不选择文件、不填写 SHA；缓存不会保存 history、current head 或 CAS，也不会省略双快照。
4. 查看角色合成图和 `pelvis-spine`、`spine-chest`、`chest-neck`、`neck-head` 四骨示意。播放或拖动时间轴，检查摆动方向、幅度和循环是否符合角色。
5. 用页面提供的少量通俗参数调整幅度与节奏。推荐值、播放结果和时间轴停留位置都只是 `unvalidated_draft`，不会在后台批准。
6. 满意后先勾选人工确认，再点击“保存 P10.1，下一步运行结构探针”。如需停止使用候选，可选择“不使用身体摆动”或“当前无法判断”。三个按钮都会打开二次确认弹窗，显示当前项目、动作、决定类型和后果；按 Esc、点击遮罩或点击“取消”均不发送请求。只有点击“确认并提交”才会以实时 current-head CAS 写入 candidate-bound P10.1 revision；若另一窗口先保存，刷新历史并重新确认，不要沿用旧基线。
7. 若保存的是参数，成功回执应显示 `pending_probe`，此时点击“打开 P10.2 自动结构探针”；“不使用”或“当前无法判断”会得到 `not_applicable`，不进入 P10.2。不要把任何 P10.1 决定当成 Runtime、视觉、动态接缝或发布批准。

### P10.2：自动运行结构探针

1. 打开 <http://127.0.0.1:8765/body-sway-probe.html>，或从 P10.1 成功回执进入。页面会优先选择 URL 指定的 package；没有指定时，只自动选择唯一 `adjust/pending_probe` current head。
2. 等待自动重放和结构编译完成。首次冷加载会完整 replay；同一服务进程会对完整 package、candidate、current revision/decision 与算法 profile 都相同的结果使用有界缓存，stored split 缓存还绑定 source/preview/manifest 全字节内容、Resolved/decision 与 runtime。每次仍会在前后重放 exact 链并检查 current head；缓存不落盘、不跨服务重启、不代表批准。页面不要求选择文件、填写 SHA 或逐项点击批准。
3. 查看顶部结论、角色图和四骨时间轴。`1024×1024` 等数字只是 See-through 素材/setup 坐标，不是 Rig 或 Runtime 相机边界。可滚轮或按钮缩放、在画布上拖拽平移，点击“适配全部动作”查看完整采样包络；这些操作只改变本地视图。拖动时间轴只切换有界采样见证，不会批准 tick，也不代表穷尽全部采样。
4. 查看五项自动结构卡：loop、FK、mesh、画布和共享索引。接缝与 Runtime 视觉两卡固定列为后续门禁，不能因为前五项通过而当作已发布。
5. 若显示“结构拒绝”，查看 P10.2a 的 `0/8…8/8` 统一 gain 诊断。`0/8` 只是“移除 body-sway 后是否仍越界”的测试，不能保存为动作。只有非零 gain 的 sampled canvas 和 geometry 都通过时，系统才会给出 `unvalidated_draft`；把它带回 P10.1 后，仍须在确认弹窗中保存一个新 revision，再回本页重跑 P10.2。
6. 若旧报告只因素材框 containment 被拒绝、而动态视口能够覆盖完整动作，页面会显示“动态视口已适配”；旧 v1 报告仍作为审计证据保留，但不再把素材框越界解释成 Rig 结构失败。继续向下查看“自动取景确认”：系统会自动显示 setup、base、combined 三张覆盖卡和最多四个责任点，不要求坐标、SHA 或文件。图像完整且留白合理时点击“采用自动取景”；不合适时点“不采用”，素材不足时点“当前无法判断”。三个按钮都会先弹出项目、动作、决定与后果，只有“确认并提交”才追加 P10.2b revision。
7. 只有 current `accept/adjust` 取景决定才能成为 Temporary Preview v2 的输入；自动候选、拖动画布、滚动时间轴或动态视口适配本身都不会批准。取景保存后，下一步从 P10.3 页面显式启动官方 Runtime 采集。
8. 若同时出现 region 换绑建议，点击入口会打开绑定工作台、选择责任图层，并在独立建议卡预览目标骨；建议不会填入上方共享 Rig 表单，普通保存也不能绕过专用入口。确认保存后会产生新 override revision，旧下游链随即变成历史。若还存在 FK、mesh、拓扑等拒绝，不要继续盲目调小幅度，应修复 attachment、骨绑定或上游动作。
9. 专家详情中的 canonical report 与唯一文件名下载只用于备份/排障；普通流程无需下载后重新选文件。

当前真实数据中，`seethrough_output` 已把 `layer-007-handwear-l` 改绑到 `upper-arm.left` 并保存 override revision 6；Manifest/P2–P5、P9、P10.1/P10.2、CaptureFraming 以及 P10.5b/P10.5c 静态接缝均已按新身份闭合。current 静态 set/bundle 为 `00de666e…`/`e23e3792…`，不可与旧链地址互换。六次旧官方 Runtime job 作为不可变失败历史保留且没有部分证据；runner 1.1.0 的 job `d7150fa1…` 已完成 43/43，P10.3c v2 revision 1 全部通过，P10.4a v2 可自动复验。P10.4b v2 分析入口已交付，真实 run 完成后写入项目交接记录。样本 B revision 16 必须沿自己的 current chain 重建，不能继承 A 或任一旧链的数字。

### P10.3–P10.3c：采集并人工复核官方 Runtime 画面

1. 打开 <http://127.0.0.1:8765/body-sway-runtime-capture.html>。页面会列出已具备 current P10.1 和 CaptureFraming 的项目/动作包，并尽量自动选择唯一可用项。
2. 等待 Preview v2 与环境卡完成。固定 profile 必须验证本地 Spine Player 4.2.119、Chrome、Runtime JS/CSS/package/LICENSE、采样计划和完整 cases；普通用户不选择 JSON、不复制 SHA。
3. 阅读许可提示并勾选授权确认，点击运行后再在二次确认弹窗核对项目、动作和 current revision。取消弹窗不会创建 job；每次真实运行都必须重新确认。
4. 查看异步进度。刷新页面可以继续查询同一 job；失败卡会从不可变事件链显示停止阶段、path-free 精确 `failure_code`、已完成数量和下一个未完成样本序号，不显示本地路径或原始异常。该序号是续跑边界，不等于证明该样本有错。失败或服务关闭造成的中断不会自动重试；当前没有主动取消运行中 job 的按钮，修复原因后重新确认并创建新 job，不要把未封存截图当作证据。
5. job 完成后点击“进入视觉复核”。链接只携带完整 `job_id`，服务端自动解析 project、Preview v2、execution bundle 和 artifact set；不要求手工填地址。
6. 在 P10.3c v2 页面从 Setup 逐点拖动时间轴到末端；21 个动作时间点会并排显示基础动作和身体摆动。图片实际加载后才计入“已查看”，快速跳过不计数；同一帧在当前页面内只请求一次并有限预取下一组。43 个 case 默认填为本地通过草稿，只需把异常图片改为“剔除”或“无法判断”并填写原因；默认草稿不会自动提交或批准。
7. 确认“已查看 22 / 22”，核对 current history head，在最终弹窗勾选复核声明后提交。发生 revision conflict 时刷新历史、重新核对后再提交；旧决定不会被覆盖。
8. 提交成功后点击“继续 P10.4a v2 准入”。新页只携带同一 `job_id`，会自动复验 current approved revision；不要下载文件或填写 SHA。
9. 页面显示“可进入后续安全分析”时，点击“继续 P10.4b v2 安全分析”。新页仍只携带同一 `job_id`，会自动创建或恢复分析任务并显示进度，不要求再次选择项目。CPU 证明运行在独立低优先级子进程；出现“区间盒证明心跳”表示长计算仍在推进，此时页面和其它 API 仍可使用。
10. 若任务失败，先读取 failure receipt。点击创建新尝试会出现二次确认；只有确认后才重新读取 current admission 并创建新 attempt。旧 receipt 不会被覆盖，失败尝试的部分工件不会被新尝试复用。
11. 完成后依次读取四条轨道：九个离散结构点、相邻连续区间、仅覆盖 100% 幅度的视觉复核，以及明确“不可用”的可发布安全范围。`indeterminate` 表示证明预算内无法闭合，不是页面或任务失败；不要据此手工扩大安全范围。详细步骤见[运行 P10.3 官方 Runtime 自动采集](how-to-capture-body-sway-runtime.md)、[复核 P10.3c 官方 Runtime 采样帧](how-to-review-body-sway-runtime.md)、[进入 P10.4a v2 安全分析准入](how-to-admit-body-sway-review-v2.md)和[运行 P10.4b v2 自动安全分析](how-to-analyze-body-sway-safety-v2.md)。

当前 P10.3 v2 runner 版本为 `1.1.0`。它以 collector 的 exact 截图提交作为页面终态，移除了旧
`--dump-dom`/`--virtual-time-budget` 组合；只会容忍“截图已经提交且主动 teardown”导致的 stdout
reader 关闭异常。提交前读取失败、输出超限或截图未提交仍会失败。冻结 v1 不受影响。runner 已更新
不等于真实采集已通过；下一次运行仍须执行第 3 步的两次明确确认。

### P10.5：用图片完成接缝复核

1. 从 P9 成功或“已复用”回执点击“进入接缝复核”。页面只接收该回执的 `package_id`，自动加载对应项目、候选、图片证据和 current head；不要复制 SHA 或选择 JSON。
2. 先看每处接缝的叠加图：青色是 parent，紫色是 child，虚线框是 contact 范围，同编号圆点与连线是一对锚点。SHA、contact 数字、locator 表和单层原图默认收在“技术详情”中，普通复核无需展开。
3. 系统会把唯一完整候选填成 `accept` 草稿，把源图不可观测项填成带原因的 `unobservable` 草稿。所有自动结果都可以撤销，且最后确认前不会写入 revision。
4. 若一处有多个候选，逐张比较叠加图。系统可能标记“建议重点查看”，但这不等于批准；点击你认可的候选后，页面才会形成该项的 `accept` 草稿。需要时可改为“手动调整”“候选不正确”或“源图不可见”。
5. 确认页面显示六项已检查后，点击“确认复核并生成静态接缝集”。这是唯一会提交人工决定的最终操作；自动加载、自动草稿和 6/6 进度都不会代替这次点击。
6. 若六条关系全部 `accept/adjust` 且页面来自 P9 package，本机随后自动执行 P10.5c 编译、内容寻址发布和 exact readback。成功后可下载 path-free 精确复验回执；只有精确 P10.4b2 动作域也已闭合时，才能进入“动态接缝验证”。
7. 若页面提示“P10.5b 已保存；P10.5c 未完成”，只点击“仅重试生成静态接缝集”。不要再次提交六项人工决定；页面会保留已经写入的 revision。若结果包含 `reject/unobservable`，页面只保存阻塞结论，不会生成不可信的 P10.5c。

当前真实状态要单独理解：样本 A 的 current P10.5c 已 exact verify，不应再次提交六项静态决定。P10.5d v2 自动入口已交付；当前 P10.4b run 完成并重启服务后，从完成页点击“开始 P10.5d v2 动态接缝分析”。页面自动选择 current P10.5c，不填 SHA；失败时保留旧回执，新 attempt 必须二次确认。真实 A 尚未执行，静态接缝也不表示动态接缝、Runtime、Raster、Overlap 或视觉质量通过。专业 CLI 见 [P10.5d v2 操作说明](how-to-compile-body-sway-dynamic-seam-v2.md)。

## 3. 打开一个样本

1. 在页面顶部的“项目”下拉框选择 `seethrough_output` 或 `seethrough_output_5`。
2. 等待合成图、图层列表和骨骼覆盖显示出来。
3. 先看右侧“QA 警告”。警告是复核线索，不等于自动判定结果。
4. 如果画布大小不合适，按 `0` 适配画布，使用 `+`、`-` 缩放；在空白处左键拖拽，或在任意位置中键拖拽，可自由平移。

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
cd <autospine-workbench>
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
.\run.ps1 -PythonExe "<python.exe>"
```

### 项目列表为空

确认样本 audit 位于：

```text
<workspace-root>\tmp\psd_audit\results\<project-id>\audit.json
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
- 从已采用的 P9 链按 `project_id` 自动选择 exact package，在“身体摆动设置”中用角色合成图、四骨示意、播放/时间轴和少量参数准备 P10.0 草稿；P9 per-key single-flight 与 chain/split 缓存命中仍全字节重验，双快照不省略，三个决定按钮均经项目/动作/后果二次确认，取消零写入；
- 从 current P10.1 head 自动推荐唯一可探针项目，在 P10.2 页面只读编译七项结构报告和 P10.2a `0/8…8/8` 零权威诊断，并以通俗卡片、角色图和四骨采样见证显示结果；有界 derived cache 只复用完整 root/address/candidate/head/profile 身份相同的可重建结果，仍执行前后 exact replay/head 检查；
- 在 P10.2 页面生成 setup/base/combined 三域的 CaptureFraming 候选，通过一次确认保存独立 revision；current `accept/adjust` 可进入 package-centric Preview v2，且 v1 合同保持冻结；
- 从项目/动作包自动准备 P10.3 official Runtime execution，验证固定 Spine Player 4.2.119/Chrome 环境，要求许可勾选与每次运行二次确认，以 append-only 异步 job 报告进度，并在完成后自动进入 P10.3c v2；
- 在 P10.3c v2 页面用单时间轴复核 Setup 与 21 组 Body-sway A/B still；系统只预填本地通过草稿，异常项由人剔除，最终决定仍以 append-only history/CAS 保存；样本 A 已有全部通过的 revision 1；
- 在 P10.4a v2 页面只使用同一 completed `job_id` 自动复验 current approved head，不选文件或填 SHA；成功只表示可进入后续安全分析，release 仍 blocked；
- 在 P10.4b v2 页面用同一 `job_id` 自动运行九档 coupled-gain 与相邻时间段结构证明；`indeterminate` 按完成结果显示，只有 100% 点具备 sampled visual 覆盖，safe range 和 release 继续 blocked；
- 从 P9 package 自动进入 Seam Anchor 页面，以叠加图、确定性建议草稿和一次最终确认完成 P10.5b，并在 ready 时继续 P10.5c exact publication/readback；
- 在 P9 页面完成一次明确 human adoption 后，由本机编译 decision/reviewed policy、原子发布 MotionInstance v2 六文件 bundle，并立即 exact verify；CLI 仍可独立复验，review input 下载仅作备份；
- 通过离线命令生成和验证版本中立的 Layer Manifest、RigIR、mesh、IK、MotionIR、P10.6a/P10.6b v1/v2 与 P10.7a v1/v2；P10.7a v2 还可从 completed P10.6b 页面自动携带四个任务 ID，生成并 exact-readback 五文件 adapter，无需选择项目、文件或填写 SHA。
- 在操作者提供并确认有权使用官方 Spine Player 4.2.119 时，用冻结 P10.7b v1 捕获 P10.7a v1 的固定 sampled raster 证据；该入口不能消费 P10.7a v2。P10.7b v2 已有严格 session、collector、loopback server 与内存 harness，但还没有真实 browser runner、CLI、页面或 Runtime 执行入口。
- 从 strict canonical 示例 Manifest 只读审计两份真实样本的 P3→P10.7b 前置；审计不会自动执行阶段、代替人审或授予发布权。
- 使用独立 P10.7c 命令，把精确 capture 中唯一的 opaque setup 帧与既有 P6 approved golden 做零写入 RGBA 对照；该入口已交付，但真实样本仍需先补齐外部前置。

当前不能据此自动完成：

- 运行 See-through、挑选 seed、修补 PSD 或清理图层；
- 无人复核地生成可靠绑定、权重和通用动画；
- 自动生成眨眼、口型、头发物理、实时追踪或自由形变；
- 保证大幅动作下没有露底、裂缝、错误遮挡或翻三角；
- 把结构探针、离散截图、sampled raster 指标、锚点点距或一次人工决定当作连续时间或完整发布验收；
- 在未提供并确认授权的官方 Spine Runtime、job 未完成或尚未逐 case 人审时，把 v2 合同/测试结果声称为真实 Runtime 已执行、视觉已批准或 runtime 等价；
- 自动授予商业使用、发布许可或生成 Spine Editor 工程。

P10.7a v2 source adapter、自动页面与验证链已经存在，但它只说明 adapter 发出。P10.7b v2 的 source/session/内存 harness 也不改变这一点：它只闭合版本隔离的 plan、admission 和 artifact sessions，不创建持久化 evidence 或 raster。每个新 rig/clip 仍需分别完成 attachment 边界视觉回归、官方 Runtime 证据和许可审查；不要把 v2 地址交给冻结 P10.7b v1，其输出哈希保持不变。

### P3 Mesh 入口

在功能入口中心选择阶段 `P3`，可复制这两个帮助命令：

```powershell
python -B -m autospine_workbench compile-mesh-rig --help
python -B -m autospine_workbench verify-mesh-bundle --help
```

编译后回到主工作台底部的“P3 Mesh 证据”，显式选择 rig SHA 与 bundle SHA，再点击读取。这里显示的是 setup、权重热图、极值姿势和严格复验结果；它不是 mesh/weight 编辑器，也不会自动选中最新 bundle。

## 10. 当前阶段与下一开发入口

**当前阶段是 P10.7b-v2-runtime-session-harness。** P10.5d、P10.6a/P10.6b v2、P10.7a v2 自动入口，以及 P10.7b v2 source bridge、严格 session、collector、loopback server 与内存 harness 均已交付；机制测试不表示项目 A 已生成真实 P10.5d–P10.7a v2 凭据。当前仍没有真实 browser runner、evidence/store、CLI/UI 或 raster，也没有运行官方 Runtime。下一切片是真实 browser runner，再接 evidence/store 与自动授权入口；官方 Runtime 仍需操作者授权，release/raster/Runtime/完整边界/overlap 均 blocked。项目 B revision 16 必须完成自己的 P9/P10，并解决四条 `unobservable` 静态关系。对新的 Kimodo 输入，仍应先运行零写入准入审计：

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

readiness v1 继续冻结。A revision 6 已闭合到 P10.5c，P10.5d v2 自动入口已交付，但真实 probe 尚待当前 P10.4b run 完成并重启服务后执行；动态/Runtime 发布证据仍缺失。B revision 16 缺自己的 current P9/P10，并有四条下肢 seam `unobservable`。Runtime 基础设施不能绕过这些更早门禁。

P10.7c 的独立入口已经可从功能中心复制，也可直接查看帮助：

```powershell
python -B -m autospine_workbench compare-body-sway-spine42-v3-setup-golden --help
```

该命令需要每个项目真实的 P10.7a 与 P10.7b capture 精确地址，并同时锁定既有 P6 export/runtime golden 合同。当前 A/B 的 P9 已通过，A 也已有静态 P10.5c，但 A 的动作域、B 的完整静态 seam 和两项目官方 capture 都尚未关闭；不要用全零请求模板、P7/P8/P5 地址或 fixture 声称真实比较通过。准备 canonical 请求和读取报告见[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。

P0 Resolved Project v1、P10.6b v1/v2 MotionInstance v3 与 P10.7a v1/v2 Spine adapter bundle 机制均已完成。普通图层/关节复核不需要运行这些命令。新的 v2 链可先按
[编译 P10.6a v2 动作消费准入](how-to-compile-body-sway-motion-consumer-admission-v2.md)
把认证的 P10.5d v2 bundle 与其精确 P9 MotionInstance v2 bundle 自动闭合。只从 P10.5d 回执复制两个完整 SHA，不选择 JSON 文件或填写 P9 SHA：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-consumer-admission-v2 --help
```

旧命令 `compile-body-sway-motion-consumer-admission` 已冻结，只用于 P10.5d v1 历史链。
冻结[编译并复验 P10.6b MotionInstance v3](how-to-compile-motion-instance-v3.md)也只消费
P10.6a v1 成功输出；不要把 v2 admission 交给它。普通操作者应在 certified 的 P10.5d v2
完成页点击“继续生成 MotionInstance v3”。[自动页面](http://127.0.0.1:8765/motion-instance-v3-v2.html)
会携带精确任务地址、生成并读回三文件 bundle；无需选择项目、文件或填写 SHA。失败重试会先
要求确认并保留旧 attempt。以下命令只供专业地址编译与复验：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-instance-v3-v2 --help
python -B -m autospine_workbench verify-body-sway-motion-instance-v3-v2 --help
```

compile 只填写项目和 P10.5d probe/bundle 双 SHA；verify 只填写项目和 MIv3/bundle 双 SHA。
完整步骤见[编译并复验 P10.6b v2 MotionInstance v3](how-to-compile-motion-instance-v3-v2.md)。
冻结 v1 的专业命令为：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-instance-v3 --help
python -B -m autospine_workbench verify-body-sway-motion-instance-v3 --help
```

普通操作者在 P10.6b v2 页面完成后点击“继续生成 Spine 4.2 v3 Adapter”。
[P10.7a v2 自动页面](http://127.0.0.1:8765/spine42-v3-v2.html)会携带四个任务 ID，自动校验、
执行并精确读回固定五文件；不要单独打开无参数 URL。失败时只有点击“确认并创建新 attempt”
才会重试，旧回执不被覆盖。成功后看见“Spine adapter 已发出”即可停止，不要继续旧 Runtime 入口。

以下 v2 CLI 只供专业地址编译与历史复验：

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3-v2 --help
python -B -m autospine_workbench verify-body-sway-spine42-v3-v2 --help
```

compile 只填写项目和 P10.6b v2 MotionInstance v3/bundle 双 SHA；verify 只填写项目和
skeleton/bundle 双 SHA，均不选择文件。五文件、exact readback、错误处理和权限边界见
[自动生成并复验 P10.7a v2 Spine 4.2 v3 Adapter](how-to-compile-spine42-v3-v2.md)。

冻结 v1 历史链仍按
[编译并复验 P10.7a Spine 4.2 v3](how-to-compile-spine42-v3.md)使用自己的命令：

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3 --help
python -B -m autospine_workbench verify-body-sway-spine42-v3 --help
```

P10.7a v1/v2 的发布前 head observation 都不是永久审批权。v2 十项 authority 中只有
`spine_adapter_emitted=true`；五文件 exact readback 不证明 overlap、动态接缝、完整边界、
官方 Runtime、Runtime 等价、raster 视觉、永久 head、可发布 timeline 或 release。

冻结 P10.7b v1 的捕获、精确复验、raster 候选与人工 decision 基础设施已经可用，但只消费
P10.7a v1。它不能接收 P10.7a v2 skeleton/bundle SHA。P10.7b v2 已能从精确 v2 双 SHA生成
blocked plan/admission，并以严格 session、bounded collector 和 loopback server 完成全内存 capture
harness；这只是模拟 PNG 的传输与合同测试，不是官方 Runtime evidence。目前仍没有真实 browser
runner、持久化 evidence/store、CLI、页面、raster 或发布权。不要把 v2 内部对象交给下列冻结
v1 命令；v1 输出哈希保持不变。下一切片是真实 browser runner，再接 evidence/store 与自动授权
入口，官方 Runtime 仍需明确许可。
下列命令只用于冻结 v1：

```powershell
python -B -m autospine_workbench capture-body-sway-spine42-v3-runtime --help
python -B -m autospine_workbench verify-body-sway-spine42-v3-runtime --help
python -B -m autospine_workbench prepare-body-sway-spine42-v3-raster-review --help
python -B -m autospine_workbench submit-body-sway-spine42-v3-raster-review --help
```

冻结 v1 流程见[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)。
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
