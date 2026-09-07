# AutoSpine Workbench 功能与入口参考

开发集[PNG / PSD 坐标复核](how-to-benchmark-mapping.md)：Benchmark CLI 生成离线叠加页，
支持缩放/平移/镜像草稿下载与精确身份重载；独立的显式映射复核记录入口保持 Benchmark 范围，不生成 Rig。
现可点击对应锚点、下载/恢复草稿，并通过 CLI 拟合变换、查看逐点残差；
退化或高残差拟合会阻塞，原变换继续显示。
页面可下载接受/拒绝请求，CLI 显式确认后记录决定；只有 exact accepted 决定可生成待标注模板。

2026-09 自动化转向见 [当前状态](current-state-2026-09.md)。主工作台右侧“Spine 预览与异常复核”已支持异步构建、结构异常定位、保存复核后续跑、取消与 ZIP 下载。仍可运行 `python -m autospine_workbench.automation preview <project-id> --output preview.zip`。两种入口均自动解析地址，输出静态 setup JSON/Atlas/PNG/QA，没有动画或发布权；队列当前限定 setup-region。详见[操作说明](how-to-build-region-spine-preview.md)。

本文是面向操作者和开发者的 Reference。P10.3、P10.4a/b v2 和 P10.5d v2 自动入口均已交付。P10.5d 页面从 P10.4b 完成态携带 exact `job_id+safety_run_id`，自动闭合 current P10.5c，以 BelowNormal worker 和 append-only attempts 执行，再由父进程 exact readback/current-head recheck。CLI/store 与历史 verify 仍可用于显式地址复验。真实 A 尚待当前 P10.4b run 完成并重启服务后执行；release、raster、Runtime、视觉与 overlap 仍 blocked。v1 合同保持冻结。计划项见[开发路线](development-roadmap.md)。

## 统一入口

启动服务后打开：

- [功能入口中心](http://127.0.0.1:8765/workflow-hub.html)：按阶段、入口类型和状态搜索全部功能；
- [绑定复核工作台](http://127.0.0.1:8765/)：图层、拆分、关节、候选和 P3 证据复核；
- [身体摆动设置](http://127.0.0.1:8765/idle-behavior-review.html)：从已采用 P9 链自动准备 P10.0 候选，并由操作者显式提交 P10.1 决定；
- [身体摆动结构探针](http://127.0.0.1:8765/body-sway-probe.html)：实时分类 current P10.1 heads，仅在 ready 且与当前 Resolved Project 匹配的项唯一时自动推荐、重放并可视化 P10.2 七项结构诊断、P10.2a 离散 gain 诊断与 P10.2b 自动取景确认；
- [P10.3 官方 Runtime 自动采集](http://127.0.0.1:8765/body-sway-runtime-capture.html)：按 package 自动准备 Preview v2、校验固定环境、显式确认后创建异步 official Runtime job；
- [P10.3c v2 时间轴视觉复核台](http://127.0.0.1:8765/body-sway-review-v2.html)：由 completed job 的完整 `job_id` 进入，以 setup + 21 组 A/B 时间点复核 43 个不可变 case；默认通过仅为本地草稿，最终保存完整人工 sampled still 决定；
- [P10.4a v2 复核准入](http://127.0.0.1:8765/body-sway-review-admission-v2.html)：由 P10.3c 成功回执携带同一 `job_id` 进入，自动重放 current approved head 并显示是否可进入后续安全分析；
- [P10.4b v2 自动安全分析](http://127.0.0.1:8765/body-sway-safety-analysis-v2.html)：由 P10.4a 成功结果携带同一 `job_id` 进入，在独立低优先级子进程中自动运行九档离散结构探针与相邻连续区间证明；长计算显示盒级心跳，失败后需二次确认才创建新尝试；
- [P10.5d v2 动态接缝自动分析](http://127.0.0.1:8765/body-sway-dynamic-seam-v2.html)：由 P10.4b 完成态携带 exact job/run 进入，自动选择 current P10.5c；失败新 attempt 需二次确认；
- [P10.3c v1 视觉复核台](http://127.0.0.1:8765/body-sway-review.html)：冻结的历史/回归入口，不用于新 v2 job；
- [接缝自动复核与静态锚点生成](http://127.0.0.1:8765/seam-anchor-review.html)：P10.5b 自动看图复核；ready 时由同一次最终确认继续 P10.5c 发布与精确读回；
- [Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html)：P9 项目/package 自动加载、安全 Foot 辅助采用、异常处理，以及一次人工确认后的本地编译、发布和精确复验。

功能入口中心读取 [`web/workflow-catalog.json`](../web/workflow-catalog.json)，列出已注册 CLI、任务页面和尚未实现的计划项。对于 CLI，它只复制 `python -B -m autospine_workbench <command> --help` 帮助命令，不在浏览器或服务端执行命令；源码模式下须先在当前 PowerShell 执行 `$env:PYTHONPATH = (Resolve-Path .\src).Path`，再复制和运行帮助命令。文档卡片通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开；查看器只读获取 `/docs/<文件名>.md`，不能访问目录外文件，并把响应作为纯文本显示，不解析 HTML 或执行文档内容。

入口状态含义：

| 状态 | 含义 |
| --- | --- |
| 可用 | 仓库内已有实现；仍须满足该功能的输入和证据门禁 |
| 需要外部环境 | 已有入口，但需要仓库外 runtime、模型或许可证确认 |
| 规划中 | 当前没有可交付实现，入口只链接到开发路线 |

## 浏览器功能

### 绑定复核工作台

| 功能 | 入口 | 当前边界 |
| --- | --- | --- |
| 项目发现与切换 | 顶部项目选择器 | 发现已有 See-through audit，不运行 See-through |
| 图层浏览与 QA | “图层”模式、图层列表和 QA 面板 | 搜索、显隐、语义、左右、bbox、空层及合成差异；画布可缩放并以空白左拖/任意位置中键拖动平移 |
| 图层 authoring | 右侧图层编辑器 | 语义、side、disposition、setup 可见性、pivot、目标骨和备注 |
| 双侧切分复核 | 右侧“切分预览审查” | 接受或拒绝精确 split artifact；算法变化使旧决定 stale |
| 关节校正 | “关节”模式和坐标编辑器 | 拖动、数值输入、键盘微调、恢复自动位置 |
| 四肢候选比较 | 右侧“候选审查” | accept、adjust、reject、unobservable；证据按 SHA 回看 |
| P3 Mesh 证据 | 页面底部“P3 Mesh 证据” | 显式选择 rig/bundle SHA 后只读重验；不是权重编辑器 |
| 动作证据换绑 | 从 P10.2 的“复核自动换绑”进入 | 自动选择责任图层，并在独立建议卡预览同链一跳目标骨；不污染共享 Rig 表单，且一次明确确认后才以 candidate/current-chain/CAS 保护保存 revision |
| Revision 保存 | “保存校正”或 `Ctrl+S` | override v3、CAS、append-only history、409 草稿恢复 |

### 身体摆动设置

普通流程列出已经 adopted 且能够精确重放的 P9 链。Package inventory 会保留历史 exact 链供操作者显式查看和审计，但只有其上游身份与当前 Resolved Project 匹配时才进入自动推荐；历史链不得因仍可重放而复用旧 P10.0/P10.1。服务端从选定 package 重新闭合 Layer Manifest/P3/P5/P9，并编译对应 P10.0 idle candidate，浏览器不要求选择 JSON、输入路径或抄写 SHA。list/detail 可按 `project_id` 限定发现范围；同一服务进程内 P9 exact replay 以 per-key single-flight 合并重复并发构建，命中仍枚举 inventory、读取全部受保护文件字节并重算 seal。P10.1 history、current head 和 CAS 不缓存。

页面以角色合成图、躯干四骨示意、播放/暂停、时间轴和少量幅度/节奏控件呈现候选；原始身份和历史只放在技术详情。自动加载、推荐值、播放预览或拖动时间轴都只形成 `unvalidated_draft`，不会写 revision。“保存 P10.1”“不使用身体摆动”和“当前无法判断”三个按钮都会先打开二次确认弹窗，显示项目、动作、决定类型与后果；取消、Esc 或点击遮罩均不调用 mutation。只有操作者在弹窗中选择“确认并提交”，页面才把完整参数或明确的非采用决定、candidate SHA 和 current-head 基线提交为 candidate-bound P10.1 revision；`adjust` 成功状态仍是 `pending_probe`，必须继续 P10.2 结构探针，不能据此声称 Runtime、视觉、动态接缝或发布通过。

### 身体摆动结构探针

普通流程不再要求执行七地址 CLI、选择 candidate/decision 文件或复制 SHA。只读 package inventory 会实时读取 current-project-matched、candidate-bound P10.1 current head，分类为“可探针”“需回 P10.1”或“不适用”；历史 exact 链不进入普通清单，只有掌握 exact package ID 的审计直达入口才能只读复验。只有 current-project-matched ready 项唯一时页面才自动选择。详情加载采用 `exact replay → history/exact decision → compile or bounded derived-cache lookup → exact replay → history`；cache key 绑定 state root、完整 exact package/address、candidate SHA、current revision/decision SHA 与 probe/canvas profile SHA。命中不跳过后半段 exact replay/head 检查，任何 candidate 或 head 漂移都会 fail closed。

页面显示角色 composite、四骨代表样本时间轴、五项自动结构卡和两项后续门禁卡。预览以 SVG `viewBox` 支持 5%–800% 缩放、指针锚点滚轮缩放、拖拽/方向键平移、原始素材框重置与完整动作包络适配；角色图、骨骼和越界证据使用同一变换。SHA、source seal 与 canonical report 收在专家详情；下载只作备份。`viewport_adjustment_available` 只表示旧报告唯一拒绝项是素材框 containment 且动态 fit 成功，内嵌 v1 report 与 release gate 不变；其他 FK/mesh/拓扑拒绝仍保持 `structural_rejected`。

当拒绝精确属于上述 canvas-only 情形时，同页生成独立的 `CaptureFramingCandidate v1`。候选用相同坐标变换覆盖 setup、base、combined 三类完整 attachment 包络，以固定 640×640、DPR=1 和 32 px 余量给出 world viewport，并最多展示四个责任点。候选没有 authority；操作者须在确认弹窗中明确选择采用、不采用或无法判断。Decision history 使用 candidate/current P10.1 双绑定和 CAS，输入漂移、历史冲突或重复基线不会静默覆盖。

derived cache 是进程内有界性能优化，保存可重建的 report/adjustment/preview/dynamic viewport/rebind candidates，不落盘、不跨进程、不授予审批或发布权。key 同时绑定四类 analyzer profile，算法变化不会静默复用旧候选。stored split revalidation 另有有界进程缓存，key 绑定 source/preview/manifest 全字节内容、Resolved/decision 身份与 runtime profile；失败或任何字节/身份变化均不复用。两份 current-head/current-chain 快照仍保留。

同一次详情编译还会返回 P10.2a `BodySwayCanvasAdjustmentCandidates v1`。它把已复核的四骨幅度统一乘以离散 gain `0/8…8/8`，分别复跑 sampled canvas 与 sampled geometry，结果只用于零权威诊断。`0/8` 只回答“去掉 body-sway 后基础动作是否仍越界”，永远不能成为新的 body-sway 参数。只有**非零** gain 的两类检查都通过时，系统才产生可带回 P10.1 的 `unvalidated_draft`；它不会自动保存、批准或改写 current head。操作者必须在 P10.1 明确确认一个新 revision，再回到 P10.2 重跑完整报告。

截至本次真实状态复核，`seethrough_output` 已闭合到 current P10.5c 静态集。P10.5d v2 自动入口也已交付，但真实 A 尚待当前 P10.4b run 完成并重启服务后执行；动态/视觉接缝证据和 release 仍缺失。`seethrough_output_5` revision 16 的 current seam candidate 还有四条 `unobservable`。

### P10.3 official Runtime 采集与 P10.3c v2 复核

采集页从 `package_id` 自动闭合 current P10.1、P10.2、CaptureFraming、world viewport、Preview v2、projection、plan、source、assets、timing、selection 和完整 cases。固定环境校验绑定 Spine Player 4.2.119 的 JS/CSS/package/LICENSE 与 Chrome；只有操作者勾选许可并对本次运行二次确认后，才创建 append-only 异步 job。job 可刷新查询进度；失败或服务关闭造成的中断不自动重试，当前没有用户主动取消 API，未封存截图不会发布为 execution。

P10.3 v2 execution runner `1.1.0` 固定 `page_lifetime=collector-terminal`，不再携带冻结 v1 驱动的 `--dump-dom` 或 `--virtual-time-budget`。它只在 exact 截图已经提交且 runner 主动 teardown 的条件下容忍 stdout reader 关闭异常；提交前读取失败、输出超限、reader 未退出或 pipe 无法关闭继续 fail closed。新失败事件保存 path-free 精确 `failure_code`，不公开异常文本、路径或命令行。六次历史失败 job 不会被升级或改写；后续 43/43 completed job 已覆盖真实 runner 1.1.0 路径。

completed job 绑定 project/Preview v2/execution bundle/artifact set 四段内部地址，并以完整 `job_id` 自动进入 v2 复核页。服务端从 job 解析 exact 地址，重验 current P10.1/CaptureFraming，再准备 v2 candidate、图像和 append-only history。每个 case 必须由人选择 `approve`、`reject` 或 `unobservable`；系统绝不自动批准。全部批准只得到 v2 sampled visual head，不证明连续时间、完整接缝、runtime 等价或发布安全。P10.4a v2 已以独立合同消费该 head，只授予 `admitted_for_safety_analysis`；P10.4b v2 再以 job-only consumer 生成九档离散结构点和相邻时间段连续证明。CPU 工作由独立低优先级子进程执行，父进程仍独占 append-only event/completed 写入并独立复验 staged 文档；`continuous_boxes` 盒级心跳允许页面/API 在长证明期间持续查询。只有 `8/8` 继承 sampled visual 审批，其他幅度和全部区间仍无人工视觉覆盖；冻结 v1 合同不能读取或替代 v2 head。

v2 时间轴使用 exact URL 页面级图片池：当前位置优先、最多两张并发，并在后台预载全部 43 帧；复访不重复赋值 `img.src`，覆盖数只接纳已加载并显示的组。candidate 完整 current/PNG 校验后同时返回当时的 history，以及 120 秒固定到期、进程内、只读的图片会话。会话与 job/candidate/case/PNG 交叉绑定，只能读取签发时已经验证的内容寻址像素；过期、淘汰或错误绑定直接失败，不写磁盘、不读取 decision、不授予 authority。无会话 exact URL 仍执行逐请求 current 校验。服务端另有 candidate-snapshot 粒度、双条目/256 MiB 上限的 single-flight LRU，并以 completed job 为键保存可删除的非权威 Preview mount snapshot。snapshot v3 显式绑定由 292 个静态依赖模块生成的 Preview compiler 摘要；mount 命中仍重验 exact execution、所选项目逐字节 source/算法 seal、P3/P5/P9 内容地址、P10.1/CaptureFraming heads 和 Preview/artifact seals。decision PUT 禁用持久 mount 与图片 session，实时复验 authority/current heads 并继续 head CAS；只有通过各自 current validator 的键控进程内派生缓存可复用。会话期间发生的来源漂移会在 PUT 以 409 零写入拒绝。缓存从不保存或推断人工 decision/revision，HTTP 仍为 `no-store`。真实 43 帧测试中，含 current/history/PNG 预热的 candidate 为 `6.15 s`，之后单张读取 P50 `6.7 ms`、P95 `11.4 ms`。

旧 v1 页面、CLI、浏览器 driver、capture store 与 review namespace 保持冻结，继续用于历史证据和回归，不与 v2 execution/job/history 混用。

### Seam Anchor 复核台

普通流程从 P9 成功回执携带 exact `package_id` 进入；服务端重放 package 与共享 P3 来源、复验 P3 bundle，并自动加载左右六条静态接缝关系和 candidate namespace 的 current head。Layer Manifest/P3 三 SHA 手填保留为专业 fallback。

candidate HTTP envelope 除 canonical candidate 外还固定返回：

- `setup_canvas.width/height`；
- 每个 option 的 parent/child attachment image、`canvas_offset_xy` 与同序 `anchor_points`；
- `autospine-seam-anchor-review-assist` v1 确定性 advisory 文档。

页面在统一 SVG 画布中合成 parent/child alpha，绘制 contact bbox、编号 anchor 和配对连线；原始 SHA、contact 数字、locator 表与单层图默认位于关闭的技术详情。assist 会把唯一候选和不可观测项写入可撤销草稿；多候选只设置 `highlight_option_id`，且显示“建议重点查看 ≠ 批准”。点击多候选 option 才会形成该关系的 `accept` 草稿。任何自动填充、高亮、current-head 绑定或进度完成都不写 revision。

最后一次明确确认才以 CAS 提交完整 P10.5b decision。若包含 `reject/unobservable`，只保存 blocked revision；若六条均 `accept/adjust` 且处于 package 模式，页面继续调用 package-bound P10.5c publication，服务端重放 current decision、发布三文件 bundle、按精确上游读回，并返回 path-free receipt。P10.5b 已提交而 P10.5c 失败时，只能重试 publication，不重复人工 decision。P10.5c 成功只提供静态 set；必须先有精确 P10.4b2 动作域才能进入 P10.5d，且两者都不授予 runtime/视觉或 release authority。

### Motion Policy 复核台

样本 B revision 16 已在新 `wave-left-v1-r16-draft` namespace 中准备 Foot candidates、pending Depth proposal 与 draft manifest。旧 `wave-left-v1` adoption 仍是可复验、可在 package inventory 中显式查看的历史证据，但不能授权新 P3/P4/P5 链；P9 API 以当前 Resolved Project + Layer Manifest 双 SHA 把它标记为 `historical`，页面禁用该项，历史 adoption POST 也以 409 零写入拒绝。当前草案不等于正式 policy、Depth candidates、human decision 或 P9 adoption。新 P9 完成后还必须重建 P10.0/P10.1 并重跑 P10.2。

Foot v1 没有 joint observability 字段。若目标关节被人工标记为 `unobservable`，数值有限、IK 探针通过或 Foot candidate 为 `candidate` 仍不能证明真实足点。当前样本 B 的 `ankle.left` 与鞋口代理不重合，左腿 root correction/foot-lock 不得自动批准。

若绑定、语义或重定向发生变化，旧 P9 决定不能静默继承到新 P3/P4/P5 链。专业 CLI `prepare-motion-policy-review-draft` 会重放显式 P3/P4/P5/P7/P8 地址，并在新 namespace 中准备 Kimodo evidence、standalone Foot candidates 和 pending Depth proposal。它会写入可重放草案，但不生成正式 Depth policy、Depth candidates、human decision 或 P9 adoption；草案本身不会出现在可采用 package 列表中，回执也不返回本机目录。

普通模式先从只读 package API 列出本地项目/动作；存在推荐项时自动选择，并按 exact package ID 加载正式 policy、Foot/Depth reports。package ID 绑定项目、动作、clip、三份报告身份和 candidate inventory，不按文件名、mtime 或 `latest` 推测。服务端重算 package 身份，页面随后再用 loopback-only、zero-write Python `candidate_inventory` 复验 source、schedule、policy/depth 交叉绑定与 `candidate_ids_sha256`。通过后，证据模型按时间排序 Foot samples，显示曲线、重点窗口和角色足点。

启用时间轴辅助采用时，一次拖动会把经过范围内尚未决定且满足当前规则的安全 Foot candidates 作为一个可撤销事务写入草稿；“一键采用”覆盖其余安全 Foot。安全规则固定要求 Foot `state=candidate`、observations 完整且数值有限、correction ratio 与 residual 均不超过各自合同上限的 80%。辅助决定带来源，不覆盖现有人工或批量决定。Depth、`rejected_limit`、`rejected_conflict`、缺证、非有限值、超阈值和 `adjust` 不自动批准，仍进入异常区；重点窗口只是边界/极值/p95 等视觉提示，不单独排除候选。

只有 100% 覆盖、全局字段合法并由操作者执行一次最终采用后，页面才向当前 exact package 的 adoption 入口提交严格四字段 human review input。后端重新读取 package，不信任浏览器提供 P3/P5 地址或 candidate 文档；它编译 decision、reviewed policy 与 MotionInstance v2，原子发布六文件 bundle，再用返回的双 SHA exact verify。相同 canonical 输入可幂等复用同一地址。成功回执提供 `package_id` 驱动的 Seam 自动入口；它只交接精确证据，不自动批准关系。页面下载 review input 仅供备份；CLI 保留为专业复验路径。该流程不是零点击发布，P9 成功也不证明 seam、官方 Runtime、raster、连续时间或 release authority 通过。

“专业模式”保留 proposal 批准、三文件与声明 SHA 手工导入，用于外部副本审计和身份排障。它使用与普通模式相同的 Python preflight 与最终采纳门禁。

## CLI 功能

先在项目根目录设置源码路径：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench --help
python -B -m autospine_workbench <command> --help
```

下表与当前 CLI parser 的 66 个命令一一对应。具体必填 SHA、文件路径和外部前置条件以各命令 `--help` 及链接的 how-to 为准。

### P0：服务与合同

| 命令 | 功能 |
| --- | --- |
| `serve` | 启动仅监听 loopback 的 Web 工作台和 HTTP API |
| `validate-rig` | 验证 RigIR 交叉引用、拓扑和有限数不变量 |

Resolved Project v1 是已完成的 P0 合同能力，但没有伪造一个独立 CLI 或操作页面。工作台保存/读取流程继续生成既有字节；开发者可使用 `schemas/resolved-project-v1.schema.json` 和 `autospine_workbench.resolved_snapshot_validation.require_resolved_snapshot(...)` 做结构与语义校验。完整字段、信任边界与版本规则见 [Resolved Project v1 参考](resolved-snapshot-reference.md)。

### P1：图层与四肢候选

| 命令 | 功能 |
| --- | --- |
| `analyze-joints` | 发布固定输入的关节候选分析 artifact |
| `import-pose` | 将固定 COCO17 检测转换为 canonical pose v2 |
| `evaluate-pose` | 将 pose observations 与人工复核四肢点作诊断比较 |
| `materialize-manifest` | 从 reviewed state 发布 region-first Layer Manifest bundle |
| `publish-split-previews` | 为已 author 的 bilateral split 发布不可变左右预览 |

操作说明：[姿态导入与评估](how-to-import-and-evaluate-pose.md)、[四肢候选](how-to-run-pose-alpha.md)。

### P2：Region RigIR

| 命令 | 功能 |
| --- | --- |
| `compile-rig` | 编译并发布一个精确 region-only RigIR setup bundle |
| `run-probes` | 对一个 RigIR 文档运行确定性 FK/setup 探针 |
| `verify-setup-golden` | 只读比较 setup bundle 与明确批准的 visual golden |

操作说明：[编译 Region RigIR](how-to-compile-region-rig.md)。

### P3：Alpha Mesh 与两骨 LBS

| 命令 | 功能 |
| --- | --- |
| `compile-mesh-rig` | 从精确 P2 地址生成 alpha mesh、两骨权重、探针与视觉 bundle |
| `verify-mesh-bundle` | 按精确 P3 rig/bundle SHA 重建并只读复验 |

工作台的“P3 Mesh 证据”提供只读入口；完整合同边界见[架构中的 P3 门禁](architecture.md#阶段门禁)。

P3 profile-v1 只接受精确 `body.leg → thigh/calf` hinge。`body.arm.upper/lower` 与 `body.leg.upper/lower` 会保留语义、side 和目标骨，但作为 rigid region 进入后续链；没有合格 target 时得到可复验的 `reviewed-noop`。该结果只表示没有 v1 mesh target，不代表接缝或视觉安全已经通过。分段手臂/腿 mesh 与相应 P5 regression 属于未来 P3/P5 v2，不会静默改变 v1。

### P4：离线两骨 IK

| 命令 | 功能 |
| --- | --- |
| `compile-ik-targets` | 为左右臂腿生成解析 two-bone IK handle 和探针 bundle |
| `verify-ik-bundle` | 按精确 profile/bundle SHA 重放 P4 工件 |

操作说明：[编译两骨 IK](how-to-compile-ik-targets.md)。

### P5：MotionIR 与动作重定向

| 命令 | 功能 |
| --- | --- |
| `compile-builtin-motion` | 编译并发布确定性的内建 `idle` 或 `wave.left` MotionIR |
| `verify-motion-bundle` | 只读复验一个精确 MotionIR bundle |
| `compile-bvh-motion` | 用显式 map 将固定 BVH 编译为 MotionIR bundle |
| `verify-bvh-motion` | 只读复验一个精确 BVH MotionIR bundle |
| `compile-motion-retarget` | 从精确 P3/P4/MotionIR 链生成 MotionInstance 和回归证据 |
| `verify-motion-retarget` | 重放一个精确 motion-retarget bundle |

操作说明：[编译 MotionIR 与重定向](how-to-compile-motion.md)。

### P6：Spine 4.2 Adapter

| 命令 | 功能 |
| --- | --- |
| `compile-spine42` | 从精确 P3 或 P3/P5 链发布固定 Spine 4.2 五文件 bundle |
| `verify-spine42` | 重建上游并复验精确 Spine 4.2 bundle |

操作说明：[导出 Spine 4.2](how-to-export-spine42.md)。

### P7：Kimodo 动作输入

| 命令 | 功能 |
| --- | --- |
| `audit-kimodo-pilot-intake` | 零写入闭合真实 NPZ、recorded sidecar、map、camera 与两份上游 provenance 原件，只报告 P7/P8 编译准入 |
| `compile-kimodo-motion` | 从固定 NPZ、source sidecar 和 map 生成 MotionIR bundle |
| `verify-kimodo-motion` | 重编并复验精确 Kimodo NPZ MotionIR bundle |

操作说明：[真实 Pilot 输入审计](how-to-audit-real-kimodo-pilot-intake.md)、[Kimodo NPZ](how-to-compile-kimodo-npz.md)；Kimodo-shaped BVH 使用 P5 的 `compile-bvh-motion`，见[Kimodo BVH](how-to-compile-kimodo-bvh.md)。

### P8：相机感知 3D→2D 投影

| 命令 | 功能 |
| --- | --- |
| `compile-projected-motion` | 通过显式 CameraModel 将精确 Kimodo 动作投影到 2D |
| `verify-projected-motion` | 重放精确 ProjectedMotionIR bundle |
| `probe-projected-scale` | 从精确投影与目标 rig 报告只供复核的骨长尺度候选 |

操作说明：[编译投影动作](how-to-compile-projected-motion.md)。

### P9：Reviewed Motion Adoption

| 命令 | 功能 |
| --- | --- |
| `compile-kimodo-policy-evidence` | 从精确 P7/P8 编译不含人工决定的策略证据 |
| `prepare-motion-policy-review-draft` | 从新 P3/P4/P5 与既有 P7/P8 原子准备独立 namespace、standalone Foot 候选和 pending Depth proposal；不生成正式 policy、Depth candidates、批准或 adoption |
| `compile-heading-evidence` | 通过显式 policy map 编译 heading evidence |
| `probe-foot-lock` | 报告只供人工复核的 foot-lock 候选 |
| `probe-depth-order` | 报告只供人工复核的 pairwise depth-order 候选 |
| `compile-motion-policy-decision` | 将显式人工选择绑定到精确候选报告 |
| `compile-reviewed-motion-policy` | 将已批准决定编译为版本中立 root/draw-order policy |
| `compile-motion-instance-v2` | 将 reviewed policy 应用到精确 P5 instance |
| `export-spine42-v2` | 只读构建 reviewed motion 的 Spine 4.2 v2 export report |
| `publish-reviewed-motion-bundle` | 发布 MotionInstance v2 六文件 bundle |
| `verify-reviewed-motion-bundle` | 重放精确 P9 reviewed-motion bundle |

操作说明：[准备新的 Motion Policy 复核草案](how-to-prepare-motion-policy-review-draft.md)、[复核 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

### P10.0–P10.4：Idle 与 Body-sway

| 命令 | 功能 |
| --- | --- |
| `compile-idle-behavior-candidates` | 从精确 P3/P5/P9 编译 idle 行为候选 |
| `compile-idle-behavior-decision` | 将人工 review 绑定到精确 idle 候选 |
| `compile-body-sway-probe` | 生成七项 sampled body-sway 结构诊断 |
| `compile-body-sway-preview` | 冻结 v1：在内存中生成不具发布权的临时 Spine 4.2 preview |
| `capture-body-sway-runtime` | 冻结 v1：用操作者提供且已授权的 Spine Runtime 捕获并封存证据 |
| `prepare-body-sway-visual-review` | 冻结 v1：按精确 capture 地址准备 sampled still 人工复核 |
| `submit-body-sway-visual-review` | 冻结 v1：提交覆盖全部 case 的 visual-review revision |
| `compile-body-sway-review-admission` | 冻结 v1：准入 v1 当前 approved visual head；不能消费 v2 head |
| `compile-body-sway-review-admission-v2` | 从 completed job 自动重放 current approved P10.3c v2 head，编译 compile-time 安全分析准入 |
| `verify-body-sway-review-admission-v2` | 按显式 canonical admission 复验 exact job/execution/decision 仍为 current；不声称永久 head authority |
| `compile-body-sway-safety-analysis-v2` | 只凭 completed `job_id` 重放 P10.4a v2，并编译九档幅度候选与全部相邻 Preview v2 区间证明；默认输出 path-free 摘要，`--documents` 输出 canonical 文档 |
| `compile-body-sway-amplitude-envelope` | 冻结 v1：沿统一 gain 生成九档 sampled 候选 |
| `compile-body-sway-continuous-proof` | 冻结 v1：对 sampled-linear preview 的单位 gain 区间作有界证明 |

普通 v2 流程使用页面，新 v2 CLI 保留给精确重放和审计。操作说明：[Idle/body-sway](how-to-review-idle-behaviors.md)、[P10.3 Runtime 采集](how-to-capture-body-sway-runtime.md)、[P10.3c v2 视觉复核](how-to-review-body-sway-runtime.md)、[P10.4a v2 自动准入](how-to-admit-body-sway-review-v2.md)、[P10.4b v2 自动安全分析](how-to-analyze-body-sway-safety-v2.md)、[冻结 v1 连续证明](how-to-compile-body-sway-continuous-proof.md)。

普通操作者优先使用[身体摆动设置](http://127.0.0.1:8765/idle-behavior-review.html)。页面自动选择无歧义项目、以 `project_id` 限定 list/detail 范围，并由服务端 exact replay 上游而隐藏文件/SHA 输入；P9 exact-chain cache 按 key single-flight 且命中仍做全字节 seal 重验，stored split revalidation 与 P10.2 derived cache 也只复用完整内容/身份 key 对应的可重建结果。history/head/CAS 与前后双快照继续实时读取，所有缓存均不落盘或授予 authority。CLI 保留给历史复验和专业排障。页面准备出的候选是 `unvalidated_draft`，必须由操作者在显示项目、动作、决定和后果的二次确认弹窗中提交才形成 P10.1 revision；所有取消路径零写入，且 P10.1 通过并不代替后续 P10.2、P10.3、P10.4a、P10.4b1 或 P10.4b2。

### P10.5：接缝锚点

| 命令 | 功能 |
| --- | --- |
| `compile-seam-anchor-candidates` | 从精确 Layer Manifest/P3 静态链编译六条接缝候选 |
| `prepare-seam-anchor-review` | 准备固定六关系的静态接缝证据 |
| `submit-seam-anchor-review` | 提交覆盖六关系的人工 review revision |
| `compile-reviewed-seam-anchor-set` | 将 current ready head 发布为 reviewed seam set bundle |
| `verify-reviewed-seam-anchor-set` | 只读复验一个精确历史 seam set bundle |
| `compile-body-sway-dynamic-seam-probe` | 覆盖全部相邻 tick 和统一 gain 的 reviewed-anchor 点距代理 |
| `compile-body-sway-dynamic-seam-probe-v2` | 从显式 P10.4b v2 run/proof SHA 与 P10.5c v1 双 SHA 编译、三次复核 current heads，并发布固定三文件 bundle |
| `verify-body-sway-dynamic-seam-bundle-v2` | 按 probe/bundle 双 SHA 复验历史 exact bytes；不检查或授予 current authority |

操作说明：[接缝候选](how-to-compile-seam-anchor-candidates.md)、[人工复核](how-to-review-seam-anchors.md)、[Reviewed Set](how-to-compile-reviewed-seam-anchor-set.md)、[冻结 v1 动态探针](how-to-probe-body-sway-dynamic-seams.md)、[P10.5d v2 编译与复验](how-to-compile-body-sway-dynamic-seam-v2.md)。

表中 `compile-body-sway-dynamic-seam-probe` 是冻结 P10.5d v1 入口，只接受 v1 proof。两个 v2
命令已交付独立 path-free source closure、probe schema、pure analyzer/compiler/full-replay
validator 和内容寻址 store/exact reader。compile 发布 `source/probe/bundle-manifest` 固定三文件
inventory，并在分析前、发布前、发布后共三次复核 current heads；verify 只复验历史 exact bytes。
server/job/UI 自动入口已接入，普通用户可从 P10.4b 完成态一键进入；真实样本 A 尚无 v2
动态 probe 回执，必须等待当前 P10.4b run 完成并重启服务后执行。

### P10.6a：动作消费者准入

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-motion-consumer-admission` | 冻结 v1：读取 P10.5d v1 probe 文件，重放 P9 并产生零写入 setup-local timeline 消费准入 |
| `compile-body-sway-motion-consumer-admission-v2` | 只凭项目与 P10.5d v2 probe/bundle 双 SHA exact-read 固定三文件 bundle，并从 source closure 自动重放 P9；不选择文件、不写 state |

操作说明：[冻结 v1 准入](how-to-compile-body-sway-motion-consumer-admission.md)、[P10.6a v2 自动精确地址准入](how-to-compile-body-sway-motion-consumer-admission-v2.md)。两版使用独立 format/profile/hash domain，不能互换。v2 自动闭合 P10.5d v2/P9、Manifest/P3/target/timing/Preview v2，并在 pure core 前后复查 current visual-v2/seam-v1 heads；成功只产生 path-free、compile-time admission。

准入本身不包含 MotionInstance v3、Spine timeline、runtime 等价或发布权。冻结 P10.6b v1 仍只接受 v1 wrapper；P10.6a v2 由独立 P10.6b v2 compile/verify 入口消费。MotionInstance payload 的 setup-local track 语义没有变化，因此来源升级没有创建 v4。

### P10.6b：MotionInstance v3

普通操作入口是[P10.6b v2 自动生成页面](http://127.0.0.1:8765/motion-instance-v3-v2.html)。它只从 certified 的 P10.5d v2 完成页进入，自动携带三个精确任务 ID，生成并读回固定三文件 bundle；不选择项目、文件或填写 SHA。页面成功不解除 Spine adapter、Runtime、Raster 或发布门禁。

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-motion-instance-v3` | v1 来源链：命令/store 双重查 current heads，把完整 P10.6a v1 成功 wrapper 原子发布为三文件 v3 bundle，并按地址读回；不能消费 v2 admission |
| `verify-body-sway-motion-instance-v3` | 按精确 v3/bundle 双 SHA 重编历史 bundle，不声明 current-head authority |
| `compile-body-sway-motion-instance-v3-v2` | v2 来源链：只凭项目与 P10.5d probe/bundle 双 SHA自动读取 exact bundle/P9，生成并复验 P10.6a v2 admission，再发布 source-contract v2 三文件 bundle；不选择文件 |
| `verify-body-sway-motion-instance-v3-v2` | 只凭项目与 MIv3/bundle 双 SHA历史重放 v2 admission/source/run；不选择文件或读取 current heads |

操作说明：[冻结 v1 MotionInstance v3](how-to-compile-motion-instance-v3.md)、[P10.6b v2 MotionInstance v3](how-to-compile-motion-instance-v3-v2.md)。两条来源链的 payload 都是 `format_version=3`，但 admission、source、bundle 地址域、filesystem namespace 和 run contract 版本隔离，不能交叉验证。run 只授予 MotionInstance v3 emitted；attachment overlap/完整边界、dynamic seam safety、raster/视觉、官方 Runtime、永久 head、Spine adapter、publishable timeline 和 release authority 均保持 false/blocked。

### P10.7a：Spine 4.2 v3 Adapter Bundle

普通操作入口是[P10.7a v2 自动生成页面](http://127.0.0.1:8765/spine42-v3-v2.html)。它只从
completed P10.6b v2 页面进入，自动携带 `job_id`、`safety_run_id`、`dynamic_run_id` 与
`motion_run_id`，自动 inspect/start/poll/result；无需选择项目、文件或填写 SHA。失败回执
append-only，确认重试才会创建新 attempt。

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-spine42-v3` | 冻结 v1 source adapter：从 v1-source MIv3 双 SHA 重放 P9/P5/P3，在 current-head 门禁下发布五文件 Spine 4.2 v3 bundle，并按地址读回 |
| `verify-body-sway-spine42-v3` | 按 skeleton/bundle 双 SHA 重建完整上游和五文件历史产物，不读取 current heads |
| `compile-body-sway-spine42-v3-v2` | v2 source adapter：只凭项目与 P10.6b v2 MIv3/bundle 双 SHA重放独立来源合同，在 current-head 门禁下发布五文件 bundle 并 exact-readback；不选择文件 |
| `verify-body-sway-spine42-v3-v2` | 只凭项目与 skeleton/bundle 双 SHA从 `spine42-v3-v2` 历史地址重建完整上游、run/report 和五文件；不选择文件或读取 current heads |

操作说明：[冻结 v1](how-to-compile-spine42-v3.md)、[P10.7a v2 自动入口与专业 CLI](how-to-compile-spine42-v3-v2.md)。v2 使用独立 source contract、adapter profile、skeleton hash、run/report 合同和 `spine42-v3-v2/<skeleton-sha>/<bundle-sha>` 地址域；五文件固定为 `skeleton.json`、`skeleton.atlas`、`skeleton.png`、`run-manifest.json`、`export-report.json`，compile 发布后 exact-readback，历史 verify 从上游逐字节重建。两版地址不能交叉读取。

v2 run 十项 authority 中只有 `spine_adapter_emitted=true`。attachment overlap、dynamic seam safety、完整边界、官方 Runtime、Runtime 等价、raster 视觉、永久 head、publishable timeline 与 release authority 均为 false/blocked。机制交付不表示真实样本 A 已生成这份凭据。

### P10.7b v2：Runtime Source、Runner 与 Evidence Store

这一阶段仍是 Python 内部能力，没有 CLI、页面或自动入口。`VerifiedSpine42V3RuntimeSourceBridgeV2`
只接收项目、P10.7a v2 skeleton SHA 与 bundle SHA；它通过 v2 exact reader 历史重放固定五文件，
不读取 current heads，再以独立 v2 source/profile/plan/admission 哈希域生成：

- `official-runtime-capture-plan-v2.json`；
- `official-runtime-source-admission-v2.json`。

source admission 只确认 `p10_7a_v2_exact_replayed=true` 与
`bounded_capture_plan_emitted=true`。官方 Runtime loaded/equivalence、raster 指标与视觉、人审、
永久 current-head authority、可发布 Spine timeline 和 release authority 全部为 false，
`release_gate` 固定为 `blocked`。

已新增的 strict v2 session set 按 plan 中的固定 artifact 顺序，把 source admission、Runtime
JS/CSS 字节身份、adapter 三资产和预期 observables 逐项闭合。bounded collector 对每个 artifact
只接收一次 capture/error 终态并限制单项/总 PNG 大小；loopback-only server 校验 Host、Origin、
路径、方法、content type 与所有版本绑定。内存 harness 已用模拟 PNG 验证完整 HTTP/collector
闭环，且保持冻结 v1 session/输出哈希不变。

`run_spine42_v3_runtime_capture_v2` 是新增的内部 Windows real browser runner。它要求
`license_acknowledged is True` 先于任何 I/O，对精确 P10.7a v2 bundle 只读一次，锁定
Spine Player 4.2.119 runtime 包和 browser executable，并为每个 artifact 在全新的临时 profile
中通过独立 loopback URL 采集。执行期间会持续校验 collector 完成前缀、server 健康、
browser 身份和结束时 Runtime 包身份；任一偏差都 fail closed。

runner-issued 结果现在可由 `build_spine42_v3_runtime_evidence_v2` 封装为
`status=captured_unreviewed`。bundle 的固定前缀库存为五份 canonical JSON：manifest、plan、
admission、session set 和 runtime reports；其后严格按 plan 顺序附带 PNG captures。authority
只新增 official runtime loaded、capture completed 与 isolated attachment raster captured；
raster metrics、人工视觉、Runtime 等价和 release 仍为 false/blocked。

`Spine42V3RuntimeStoreV2` 使用独立 `spine42-v3-runtime-v2` namespace 与 v2 bundle address
domain 原子发布；并发相同发布收敛为复用，不覆盖既有内容。`VerifiedSpine42V3RuntimeReaderV2`
只接受项目、skeleton SHA、P10.7a v2 bundle SHA 与 capture bundle SHA 四段显式地址，读取并
完整重放固定 JSON 与全部 PNG，不扫描 mutable heads。任一 inventory、大小写、alias、字节或
上游身份偏差都会 fail closed。

当前仍无 P10.7b v2 完整 CLI/UI、raster metrics、人工复核或发布权；guarded 授权内核已交付，执行/API 为接续工作区改动。机制测试使用 mock
browser/runtime 边界，没有真正启动经授权的官方 Runtime；v1/v2 地址不能交叉读取。guarded v2 runtime authorization 已于 4254151 交付；后续优先推进 PipelineRun 与一键 Spine，实际 Runtime 执行仍需操作者明确授权。

### P10.7b v1：官方 Runtime 与 Sampled Raster 证据

| 命令 | 状态 | 功能 |
| --- | --- | --- |
| `capture-body-sway-spine42-v3-runtime` | `external_required` | 冻结 v1：用操作者提供并确认有权使用的官方 Spine Player 4.2.119 与本机 Chrome，捕获固定 case 的 composite 和全部 setup attachment isolate，计算 sampled raster 指标并发布不可变 evidence |
| `verify-body-sway-spine42-v3-runtime` | `available` | 按 P10.7a v1/capture 双 SHA 复验目录库存、PNG、metrics、manifest 与精确 v1 来源 |
| `prepare-body-sway-spine42-v3-raster-review` | `available` | 从精确 capture 只读编译逐 case、逐 attachment 的 candidate，不作人工批准声明 |
| `submit-body-sway-spine42-v3-raster-review` | `available` | 将覆盖全部 candidate 行的显式人工输入编译为 path-free decision；不发布 revision 或 release authority |
| `audit-body-sway-spine42-v3-readiness` | `available` | 用只读 pure replay compiler/validator 复验 strict canonical 请求中的精确地址并报告八个 checkpoint；不扫描 latest/current review head，也不运行外部阶段、Runtime、发布或写入 |

capture manifest 会记录 runtime JS/CSS、`package.json`、`LICENSE`、浏览器、capture plan、P10.7a 来源与 PNG 摘要。`LICENSE` 文件存在不等于已经取得授权，许可确认仍由操作者负责。

这些现有命令和 reader 只消费 P10.7a v1，不能接受 P10.7a v2 skeleton/bundle SHA。上面的
P10.7b v2 source/session/runner/evidence store 也没有把 v2 SHA 交给冻结入口；其可寻址
`captured_unreviewed` bundle 没有 metrics、人审或 release authority。在 v2 自动授权入口完成前，
不得由 P10.7a v2 自动页面触发外部采集；之后的官方 Runtime 执行仍须操作者明确授权。

指标只以 `alpha >= 1` 的二值掩码比较捕获计划内 transparent composite 与 attachment isolate union，并检查 missing/extra/xor、边界、裁切和非空 isolate。人工 decision 只覆盖同一组 sampled case 与 setup attachment inventory。两者都不证明未采样时间、连续 runtime raster safety、永久 current-head authority、publishable timeline 或 release authority；release gate 始终 blocked。

操作说明：[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)、[审计两份真实样本的 Spine 4.2 v3 就绪状态](how-to-audit-spine42-v3-readiness.md)。公开结构见 [request Schema](../schemas/spine42-v3-readiness-request-v1.schema.json) 与 [report Schema](../schemas/spine42-v3-readiness-report-v1.schema.json)；Schema 不替代 canonical/self-hash/dependency 的 Python 语义 validator。readiness v1 已冻结，第八项仍固定为 `p6_setup_golden_comparison_not_declared`。新增 P10.7c 不修改该合同；有效审计只说明本次显式地址的 preflight 结果，不等于 setup golden 对照或发布权。

冻结的示例请求仍没有声明两项目的 P9 exact 地址，所以直接运行示例仍会报告 `exact_reviewed_motion_address_not_declared`；这不代表工件不存在。A 与 B 历史链的 P9 双 SHA 已通过独立 exact reader，见 [pilot handoff](pilots/kimodo-wave-left-v1.md)。A revision 6 已完成 current P9/P10、CaptureFraming、43/43 execution、P10.3c v2 revision 1 与 P10.5c 静态集；冻结请求中的 `null` 不能替代这些 current 地址。B revision 16 仍不能把历史 P9 或旧 P3 seam 结论写成当前链。P10.4a v2 和静态 P10.5c 都不能替代 P10.5d v2、连续视觉或发布验收。

### P10.7c：P6 Setup Golden 独立回归

| 命令 | 状态 | 功能 |
| --- | --- | --- |
| `compare-body-sway-spine42-v3-setup-golden` | `available` | 锁定 comparison profile、显式 P3、P6 export/runtime golden 合同和精确 P10.7a/P10.7b 地址，重放后只读比较唯一 opaque setup 帧 |

操作说明：[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。请求与报告分别使用独立的 `spine42-v3-setup-regression-*-v1` Schema；report/sample 自哈希只是内容身份，命令的 gate 会从 exact P6/P10/capture/PNG 在内部重新计算并绑定 sample。命令不会运行 Runtime、扫描 `latest`/current head、写入 state 或修改 approved PNG；stdout 报告临时且不可寻址，readiness v2 前仍需 immutable comparison bundle。`passed` 只表示固定 setup 帧在批准阈值内，不证明动画 case、连续时间安全、永久审批或发布权。A revision 6 已接受 CaptureFraming revision 1，完成一份真实 official Runtime execution 和 P10.3c v2 revision 1，P10.4a v2 已可编译安全分析准入；它仍未提供 P10.7c 所需的 current-chain P10.7a/P10.7b/golden 闭合。B revision 16 还须完成自己的 P9/P10/seam，因此两者都没有 current-chain P10.7c 通过结论。

## HTTP 写入边界

P9、Idle 与 Seam 自动页面使用下列 package 资源；preflight 与 GET 零写入，authority-changing POST 都只在各自最终确认后调用：

| 方法与资源 | 行为 | 安全边界 |
| --- | --- | --- |
| `GET /api/motion-policy/review-packages` | 发现固定文件名的本地 exact review package，重算身份并返回唯一 current 推荐项 | loopback-only HTTP projection v2；响应 path-free，以当前 Resolved + Manifest 双 SHA 标记 `current/historical`；磁盘 package 与 package ID 仍为 v1，历史项不自动加载 |
| `GET /api/motion-policy/review-packages/{package_id}` | 按完整 package ID 读取正式 policy、Foot/Depth reports、预检 inventory 与当前绑定对齐状态 | HTTP projection v2；exact ID 必须绑定项目、动作、clip、三份报告 SHA 与 candidate inventory；alignment 不写回 v1 工件，历史项仅供审计，损坏或变化时 fail closed |
| `GET /api/idle-behavior/review-packages` | 从已 adopted P9 链发现 P10.0/P10.1 review package，并保留历史 exact 链供显式查看 | 可用 `project_id` 限定范围；不按 mtime/`latest` 猜测；只有 current-project-matched 链可自动推荐；P9 replay 按 key single-flight，命中仍做全字节 seal 重验 |
| `GET /api/idle-behavior/review-packages/{package_id}` | 服务端 exact replay P3/P5/P9/P10.0，返回角色预览、四骨参数建议和 current history | 可带匹配的 `project_id` 限定范围；immutable chain/split 缓存非权威；history/current head 与双快照实时读取 |
| `GET /api/idle-behavior/review-packages/{package_id}/canvas-adjustment-drafts/{candidate_sha256}` | 重放同一 P10.2a 诊断并把唯一非零通过候选与 current P10.1 entry 组成只读预填入口 | 与 P10.2 详情共享 root/address/candidate/head/profile 全绑定的有界 derived cache，但仍做前后 exact replay/head 检查；响应零写入、零权威，最终仍走 P10.1 人工确认和 CAS |
| `POST /api/idle-behavior/review-packages/{package_id}/decisions` | 二次确认后提交一次显式 P10.1 人工决定 | 取消不发请求；确认要求 `X-Autospine-Intent: body-sway-human-review-v1`、exact candidate、`explicit_confirmation=true` 与实时 head CAS；成功仍为 `pending_probe` 或明确 `not_applicable` |
| `GET /api/idle-behavior/structural-probes` | 实时分类各 package 的 current P10.1 head，并只在 ready 项唯一时返回推荐 package | path-free、零写入；历史 ready revision 不会覆盖新的 reject/unobservable head |
| `GET /api/idle-behavior/structural-probes/{package_id}` | 重放 exact P3/P5/P9/P10.0/P10.1 链，编译 P10.2 七项诊断、P10.2a `0/8…8/8` gain 诊断与有界可视投影 | 派生缓存 key 绑定 state root、完整 exact address、candidate SHA、current revision/decision SHA 与 probe/canvas profile；命中仍执行前后 exact replay/head 检查，head 漂移 fail closed；零写入且不授予 Runtime、视觉或发布权 |
| `POST /api/idle-behavior/structural-probes/{package_id}/rebind-adoptions/{candidate_sha256}` | 一次明确确认后采用当前 region 换绑建议并追加 override revision | 要求 `X-Autospine-Intent: region-rebind-adoption-v1`；服务端重放 exact 候选、当前 Resolved/Manifest、来源骨与 P10.1 head，并在共享候选事务锁内完成最终 head 核验和 override CAS；revision 内保存可信 provenance，取消或任一身份漂移均零写入 |
| `POST /api/idle-behavior/structural-probes/{package_id}/capture-framing-decisions` | 一次明确确认后追加 P10.2b 自动取景 revision | 要求 `X-Autospine-Intent: capture-framing-human-review-v1`、candidate SHA、base revision/head SHA 与 `explicit_confirmation=true`；服务端重建候选并双检查 P10.1/project chain，漂移或 CAS 冲突零写入 |
| `GET /api/p10/runtime-capture/packages/{package_id}` | 零写入准备 package-centric Preview v2 与固定 Runtime/Chrome 环境状态 | 自动闭合 current P10.1/CaptureFraming；响应不授予许可或执行 authority |
| `POST /api/p10/runtime-capture/jobs` | 在许可勾选和本次运行二次确认后创建 official Runtime capture job | 要求 `X-Autospine-Intent: p10-official-runtime-capture-v2`；request 绑定 current 身份；append-only，失败/服务中断不自动重试；无用户 cancel API |
| `GET /api/p10/runtime-capture/jobs/{job_id}` | 按完整 job ID 读取异步进度、事件、终态和 completed execution 地址 | path-free、零写入；失败事件保留精确安全 `failure_code`；刷新只查询，不重新提交或自动恢复执行 |
| `GET /api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/candidate` | 从 completed job 解析 exact execution，重验 current source，预热全部 PNG，并返回 v2 candidate、current history 与短期只读图片会话 | job 未完成、source 已变化、PNG 不完整或 execution 读回失败时 fail closed |
| `GET .../visual-review-v2/candidates/{candidate}/cases/{case}/image/{png}` | 无会话时严格重验 current；短期会话只读取已预热的 candidate 精确 PNG | 完整 SHA，响应 ETag 绑定 PNG SHA；会话过期/交叉绑定直接失败；零写入 |
| `GET .../visual-review-v2/candidates/{candidate}/history` | 读取 v2 连续 revision 与 current head | 不自动选择或生成任何人工决定 |
| `GET .../visual-review-v2/candidates/{candidate}/history/{revision}/{decision}` | 读取一个精确 v2 decision | exact revision/decision 双地址；零写入 |
| `PUT .../visual-review-v2/candidates/{candidate}/decisions` | 追加覆盖全部 case 的 v2 人工 decision | 独立 v2 intent、candidate 绑定和 head CAS；绝不自动批准 |
| `GET /api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/admission` | 重放 completed execution 与 current approved P10.3c v2 head，返回 canonical P10.4a v2 admission | 只接受完整 `job_id`；双快照观察只在 compile time 有效；零写入、path-free、`no-store`，release gate 固定 blocked |
| `GET /api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/safety-analysis-v2` | 快速获取 P10.4b v2 ready 或 active 入口状态 | 只恢复仍在执行的 run；terminal/no run 返回 ready，后续独立 worker 子进程重新编译 current admission，不复用历史完成结果；不猜 latest |
| `POST .../safety-analysis-v2/runs` | 创建或恢复当前 job 的异步 combined analysis run | body 固定为空对象；要求 `X-Autospine-Intent: p10-body-sway-safety-analysis-v2`；exact replay 在低优先级子进程中执行，完整 proof 可能需较长时间；父进程独占事件/完成态写入，不写人工决定 |
| `GET .../safety-analysis-v2/runs/{run_id}` | 查询 run 阶段、盒级心跳、进度和失败分类 | append-only 状态；`continuous_boxes` 表示首次细分，`continuous_validation` 显示第二遍精确重算的真实盒级进度；`failed_retryable` 与 `failed_terminal` 明确分离；旧 receipt 不可变，新尝试需二次确认 |
| `GET .../safety-analysis-v2/runs/{run_id}/result` | 读取 amplitude/continuous 公共投影、claims、release gate 与两份内容地址回执 | HTTP 不返回可能含逻辑资源字段的完整 canonical 文档；`indeterminate` 是合法 completed proof，safe range 固定不可用 |
| `GET /api/motion-policy/review-packages/{package_id}/seam-review-entry` | 零写入重放 exact package 与 Foot/Depth 共享 P3 来源，复验 P3 bundle，重新准备 P10.5b candidate | 不接受客户端 Manifest/P3 SHA；响应 path-free，只返回 exact 地址、candidate SHA、可观测性摘要与 blocker |
| `POST /api/motion-policy/review-packages/{package_id}/seam-publications` | 从已提交的 current ready P10.5b decision 编译、发布并 exact-readback P10.5c | 独立 intent；只接受 package/candidate/revision/decision 身份，不接受路径或客户端上游地址；响应 path-free |
| `POST /api/motion-policy/preflight` | 从原始 JSON 文本运行 inner strict decoder；`policy_identity` 返回 Python canonical SHA，`candidate_inventory` 解包受支持 envelope 后重算 policy/foot/depth 三 SHA、完整 standalone 合同、交叉绑定、四项计数及候选 ID 清单 SHA | loopback + exact same-origin、JSON、`X-Autospine-Intent: motion-policy-preflight-v1`；外层 48 MiB、内层 policy/foot/depth 1/16/16 MiB；不读路径、不写 state、不批准或发布 |
| `POST /api/motion-policy/review-packages/{package_id}/adoptions` | 用严格 human review input 编译 decision/reviewed policy，原子发布 MotionInstance v2 六文件 P9 bundle，并按精确双 SHA 读回复验 | loopback + exact same-origin、JSON、`X-Autospine-Intent: motion-policy-adoption-v1`；服务端重读完整 package，不接受任意路径、shell 命令或客户端提供的上游地址；成功响应 path-free |

Preflight POST 只用于承载有界完整 JSON 文档，不代表 mutation。P9 adoption、P10.1 decision、CaptureFraming decision、Runtime job 创建、P10.3c v2 decision、region rebind adoption 与 seam-publication 属于独立写边界；它们的最终确认不能互相替代。本地 HTTP 服务的主要写操作包括：

| 方法与资源 | 写入内容 | 并发边界 |
| --- | --- | --- |
| `PUT /api/projects/{id}/overrides` | override v3 与 resolved snapshot | `base_revision` CAS |
| `PUT .../visual-review/candidates/{candidate}/decisions` | 冻结 v1 P10.3c sampled visual decision revision | exact v1 candidate、intent header 与 head CAS |
| `POST /api/p10/runtime-capture/jobs` | P10.3 v2 append-only execution job request/events | 两次显式确认、current P10.1/framing 身份；失败/中断不自动重试 |
| `PUT /api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/candidates/{candidate}/decisions` | P10.3c v2 sampled visual decision revision | completed immutable job、exact v2 candidate、独立 intent 与 head CAS |
| `POST /api/idle-behavior/review-packages/{package_id}/decisions` | P10.1 idle/body-sway decision revision | exact package/candidate、显式确认、intent header 与 head CAS |
| `POST /api/idle-behavior/structural-probes/{package_id}/capture-framing-decisions` | P10.2b CaptureFraming decision revision | exact candidate/current P10.1/project chain、显式确认、intent header 与 head CAS |
| `POST /api/idle-behavior/structural-probes/{package_id}/rebind-adoptions/{candidate_sha256}` | 候选绑定的 override revision 与不可变 `revision_provenance` | exact package/candidate/current chain/来源骨、显式 intent、P10.1 共享事务锁与 override `base_revision` CAS |
| `POST .../seam-anchor-reviews/.../candidates/{candidate}/decisions` | P10.5b seam decision revision | exact candidate、intent header 与 head CAS |
| `POST /api/motion-policy/review-packages/{package_id}/adoptions` | P9 decision、reviewed policy、MotionInstance v2 与六文件不可变 bundle | exact package、显式 intent、穷尽 human decision、内容地址幂等复用及发布后 exact verify |
| `POST /api/motion-policy/review-packages/{package_id}/seam-publications` | P10.5c ReviewedSeamAnchorSet 三文件不可变 bundle | 已提交 current ready P10.5b decision、独立 intent、package/source 重放、双快照与发布后 exact readback |

其余浏览器 API 为读取或 zero-write 计算。Package 推荐、motion-policy preflight 的 `passed`、辅助 Foot 草稿、P10.0 推荐参数和时间轴预览都不是最终 human adoption；P9 与 P10.1 各自需要独立的显式最终确认。CLI 对 exact decision/policy/bundle 的编译与复验继续作为专业审计和无浏览器重放路径。离线 CLI 中的 `compile`/`publish` 命令可能向 state root 发布内容寻址工件，因此运行前仍应查看对应 `--help` 和 how-to。完整路由见 [README 的 HTTP API](../README.md#http-api)。

## 当前能力边界

- P3/P5 可以进入现有 P6 Spine 4.2 导出链。
- P6 当前只有离线 CLI；主工作台没有 Spine 导出编排，Project API 的 `export_spine` 仍为 `false`。
- resolved snapshot 已确定性生成并被下游寻址，现有独立 v1 JSON Schema、严格语义 validator、派生 QA 校验及 r5/r7 历史哈希回归；它仍没有独立 CLI/UI，外部 candidate/split artifact 字节重放继续由各自 binder 负责。
- override history 已 append-only 保存，但主工作台尚无历史浏览/恢复 UI；安全恢复必须追加新 revision，不能改写历史。
- P7 real-pilot intake 审计已经可用：它把真实 NPZ、recorded sidecar、map、camera 与两份 provenance 原件闭合为零写入 path-free 报告。`wave-left-v1` 已通过该审计并完成 P7/P8、历史 A/B P5 exact replay、正式 depth policy/depth candidates 和各自历史 P9 exact replay，身份集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)。Preflight 或辅助草稿本身仍不认证 checkpoint 或批准动作质量；B revision 16 的 current P9 必须在新链上重新 human adopt 并 exact verify。
- P10 body-sway 已交付到 P10.5d v2 自动入口，包括 CLI/store、BelowNormal worker、append-only attempts、父端 exact readback/current-head recheck 和页面。A revision 6 仍须等待当前 P10.4b run 完成并重启服务后真实执行；runtime/raster/overlap、可发布 safe range 和 release authority 仍缺失。冻结 v1 始终不能消费 v2 head。B revision 16 仍须沿自己的链重建。
- `blink`、口型和头发目前只存在 idle candidate 类型或规划入口，没有可靠素材生成、绑定与 runtime 交付。
- See-through/pose 推理、真实 Kimodo checkpoint authenticity/动作质量验收、实时追踪、自由形变、runtime IK、生产部署仍未实现。

不要把结构验证、fixture、sampled screenshot/指标、anchor-point 距离、loader replay 或一次人工 decision 写成连续 raster 安全、真实双样本验收或发布通过。
