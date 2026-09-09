# AutoSpine Workbench 后续开发路线

2026-09-09：[主工作台动画候选](how-to-build-animated-spine-preview.md)已连接登记来源、网格、有限动作、十七点/绑定复核与下载。
当前已扩展到三个开发样本和四个可见测试项目，候选无生产权；分类与批量绑定预填入口已接入，下一主线是首批十角色的可测量自动化与通用 Mesh 验证，
详见[自动化产品路线](automation-roadmap-2026-09.md)。下文旧“下一切片”描述为历史记录，不代表当前优先级。

两侧已选手臂已接入11附件包，全量复核入口已准备。下一步消费剩余图层的明确决定，
按新包重跑完整组合、肩部接触与遮挡验证；不静默批准pending图层或570残余像素。

刚性层与腿鞋分区的9附件同包已通过官方Runtime验证。下一步整合已选手臂Mesh，
并准备14个pending图层的集中复核，不把现有缺项静默绑定到root或自动采用。

整角色上下文诊断已落地Alice；下一切片将已确认刚性绑定与当前分区候选接入同一Adapter。
未决定层和残余继续列为缺项，之后执行官方Runtime完整合成/遮挡回归；静态来源参考不算动画完成。

右侧同帧ROI定位与4／8邻接敏感性已完成；没有确认封闭孔洞，不据此修改权重。
下一切片转向完整角色合成与开放式细缝、原有空白、颜色／重叠回归，不新增自动采用权。

Alice右侧独立采样已交付（183目标，58处alpha下降、无新增低于8中心点）。
下一步复核同帧局部变化的空间位置和轮廓／颜色／重叠含义，再判断修复需求；仍未完成完整角色门禁。

2026-09-08：已整合[保守候选预览入口](how-to-seam-candidate-hub.md)，不再要求操作者在多个临时播放页切换。
下一切片补Alice右侧独立代表性Runtime采样，随后补原有空白、颜色／重叠与完整角色覆盖。
不得将零疑似点视为准入通过，或继续以新纵向证据阶段替代生产能力。

本文面向维护者与评估可行性的项目负责人。当前执行顺序以 [2026-09 自动化产品路线](automation-roadmap-2026-09.md) 为准：保留可信认证内核，优先完成普通用户的一键生产流，再推进自动语义/关节、通用 Mesh/Weight 与动作质量。项目级 PipelineRun、主工作台异步 region 预览、结构异常队列与 ZIP 下载已交付；预览默认目标为 Spine 4.3.26，可显式选择 4.2。范围与限制见 [操作说明](how-to-build-region-spine-preview.md)。

guarded v2 Runtime 授权已于 `4254151` 提交，后续 manager、执行与 HTTP API 也已纳入开发 checkpoint，不能再视为“下一切片”。已有 P9/P10 精确链继续原位保留，其历史 4.2 地址与 v1 合同保持冻结。机制交付不代表样本 A/B current 已封存，也不代表官方 Runtime、raster、人工视觉、完整边界、overlap 或 release 已通过。B 的不可观测状态继续 fail closed；详见 [当前状态](current-state-2026-09.md) 和 [独立 checkout 基线](baseline-frozen-checkout-2026-09.md)。

P9 页面现已增加 pending draft 自动发现与一键晋级入口。它会自动选择唯一 current 草案，显示角色与 setup 遮挡关系，并在一次明确确认后生成正式 Depth policy、Depth candidates 和新的 exact review package。草案晋级不等于最终 P9 adoption；候选仍须复核，并再次明确提交最终 human adoption。旧 P9 以及依赖旧 P3/P9 的 P10/P10.5 决定只保留历史证据。canvas-only 的新链不会放宽 v1，而是通过已经交付的 CaptureFraming decision、Preview v2、official Runtime execution v2 与 P10.3c v2 review 承接 setup、base、combined 完整包络。

B 的 `ankle.left=unobservable` 仍要求左腿 foot-lock 保持阻塞。下文标记为“旧链”的 A/B P9、
P10.1、P10.2 或 P10.5 数字只代表历史固定链；A revision 6 current P10.5c 地址以
[pilot handoff](pilots/kimodo-wave-left-v1.md) 的独立表格为准，不能与旧链互换。

## 规划原则

后续工作继续遵守现有边界：

1. 先定义版本中立合同、语义 validator 和失败语义，再实现目标版本 adapter。
2. 自动候选与人工决定分离；模型或算法变化不得静默复用旧决定。
3. 所有消费方按精确内容地址读取上游，并在需要 current authority 时重新检查 head。
4. 数值、结构、raster、人工视觉、官方 Runtime 和发布许可是不同证据层，不能互相替代。
5. 新生产文件默认不超过 300 行，400 行是硬上限；优先拆成 pure core、I/O、validation、CLI/UI adapter。
6. 外部模型、Spine Runtime 和素材许可由操作者提供并确认；仓库不隐式下载或再分发。

## 当前执行优先级

执行顺序以 [2026-09 自动化产品路线](automation-roadmap-2026-09.md) 为准：
冻结可信链 → PipelineRun/一键 Spine → Review Queue → 自动语义/关节 →
Mesh/Weight v2 → AnimationIR → 表情与次级运动 → Runner/Beta → Blender/生产化。
下文保留旧阶段的技术说明与历史验收记录；其中旧 P0/P1 标签不再代表产品排期。

## 已完成入口：P10.5b 自动复核与 P10.5c 发布

这部分开发能力已经交付，不再要求普通操作者逐条读取 SHA、contact 数字或 locator JSON：

- candidate envelope 提供 `setup_canvas`，以及 parent/child attachment 的
  `canvas_offset_xy`、`anchor_points` 和精确图片地址；页面合成 alpha、contact bbox 与编号连线；
- 确定性 advisory assist 自动填唯一候选和不可观测项；多候选只给建议高亮，明确
  “建议重点查看 ≠ 批准”，点击候选才形成 `accept` 草稿；
- package 自动入口绑定 current head；SHA、原始 JSON、contact 数值、locator 表和单层图默认
  隐藏在技术详情；
- 一次最终确认才提交 P10.5b。ready 时继续 package-bound P10.5c publication 与 exact
  readback；P10.5b 已提交而 P10.5c 失败时，只能重试 publication，不重复写人工 revision。

这里的“已完成”同时包括 A 的两条彼此隔离的真实静态链：旧链 P10.5b revision 2 与 P10.5c
bundle 继续只供历史复验；revision 6 current 链另有 candidate `ea1c0211…`、decision
`9db91b9a…`、review revision 1、set `00de666e…` 和 bundle `e23e3792…`，已按 Manifest
`81bc00cb…` 与 P3 `309e4ef1…`/`92b398a8…` 精确复验。A 不再需要重复人工复核静态接缝。
B revision 16 的 current candidate 只有两条关系可复核、四条 `unobservable`；完整 P10.5c
仍被素材/语义与 P9/P10 上游阻塞。

## 当前入口：P10.0–P10.2a 身体摆动设置与结构诊断

普通操作者从 `idle-behavior-review.html` 进入。页面只发现已经 adopted 且可以精确重放的 P9
package，存在唯一或确定性推荐项时自动选中；服务端重新闭合 Layer Manifest/P3/P5/P9 并编译
P10.0 candidate，不要求用户选择文件、输入路径或填写 SHA。

已交付的读取优化仅复用同一服务进程内的 immutable exact-chain 对象。P9 replay 对相同 key 使用
single-flight，list/detail 可按 `project_id` 限定发现范围；缓存命中仍会读取全部受保护文件字节并
校验 seal。该缓存不落盘、无 authority，并明确排除 P10.1 history、current head 与 CAS。

P10.2 详情和 P10.2a→P10.1 草稿交接还共享有界的进程内 derived cache。其 key 绑定解析后的
state root、完整 exact package/address、P10.0 candidate SHA、P10.1 current revision/decision
SHA，以及 probe、canvas adjustment、dynamic viewport、region rebind 四类 profile SHA；任一 root、输入、head 或算法 profile 变化
都不会命中旧结果。每个请求仍在缓存查找/编译的前后执行 exact replay、candidate 比对和
current-head 检查。缓存只保留可重建的 report/adjustment/preview/viewport/rebind candidate，不落盘、不跨进程、不授予
authority；冷启动、首次 package 发现或新 key 的请求仍可能较慢。

current-chain 发现已移除 `list_projects()` 的完整摘要构建。stored split revalidation 使用有界进程缓存，key 绑定 source/preview/manifest 全字节内容、Resolved/decision 身份与 runtime profile；Manifest 缓存继续逐字节绑定源 raster 与算法身份。任一内容、决定或 runtime 变化都会失效，失败不缓存；before/after 双快照仍完整保留，禁止用 TTL、mtime 或 `latest.json` 近似替代。实测全项目 warm list/detail 从约 `10.85 s` 降至约 `0.61 s`，A scope warm 约 `0.28 s`；冷启动仍需约 `18 s` 完整重放 A 的 P9 链。

P10.1 package inventory 会保留可精确重放的历史 P9/P10 链，供操作者显式选择查看与审计；
P10.2 普通 inventory 则只列 current-project-matched 地址，历史链须凭 exact package ID 走只读审计详情。
这项历史可读性不等于 current authority。自动推荐必须先确认链的上游身份仍与当前 Resolved
Project 匹配，历史不匹配项不得进入推荐，也不得携带旧 P10.0 candidate 或 P10.1 current head
到新绑定 revision。

角色合成图、躯干四骨示意、播放/暂停、时间轴与少量幅度/节奏控件用于理解和调整候选。自动
推荐、时间轴预览和参数默认值只构成 `unvalidated_draft`。保存、拒绝与不可判断三个决定按钮
统一显示项目、动作、决定类型和后果的二次确认弹窗；取消、Esc 与遮罩点击都在 mutation 前返回，
不会写 revision。只有操作者点击“确认并提交”才通过独立 intent 和实时 current-head CAS 追加
candidate-bound P10.1 revision。A 的旧 r2/report 产生了换绑建议；操作者已经采用建议并保存
revision 6，因此旧 head 不再匹配 current Resolved/Manifest。A r6 已生成并采用新的 P10.0/P10.1，
随后完成 P10.2–P10.4 与 current P10.5c 静态集。B 的 r2 与 sampled canvas containment 拒绝属于
revision 16 之前的历史链，仍必须在新 P9 adoption 后生成新的 P10.0 candidate 和 P10.1 revision。
新的 `adjust` 成功也只进入 `pending_probe`，下一项仍是
七项 sampled 结构诊断。

P10.2 的 `GET /api/idle-behavior/structural-probes` 会实时分类所有 current P10.1 heads，仅在
`adjust/pending_probe` ready 项恰好唯一时给出推荐；reject、unobservable 或缺少 current head
的 package 不会被自动送入探针。详情入口按 `history → exact decision → compile → history`
读取同一 package，任一 decision、revision、candidate 或 head 漂移都 fail closed。两个 GET
均为 path-free、zero-write，页面切换项目、拖动代表样本时间轴和下载报告都不会产生 revision。

页面只把五项自动结构检查和两项后续门禁投影为可视卡片。素材 canvas 是 setup 坐标基准，
不是 Rig/Runtime 相机硬边界；预览支持自由缩放、拖拽平移、重置和按完整动作包络适配。
旧 `BodySwayProbeReport v1` 继续按固定素材坐标保留原状态和哈希；若它唯一拒绝项是
`sampled_canvas_containment` 且动态适配成功，P10.2 v3 entry 只把公开状态重分类为
`viewport_adjustment_available`，不会改写内嵌 report 或解除 release gate。FK、mesh、拓扑等
任何其他结构拒绝仍 fail closed。`manual_visual_required` 也只开放 P10.3 准备，不能跳过
P10.4a/P10.4b1、动态接缝、官方 Runtime 或 release 门禁。

同一次 P10.2 详情编译还生成 P10.2a `BodySwayCanvasAdjustmentCandidates v1`，在保持周期、
相位和上游动作不变的前提下，对四骨幅度统一乘以 `0/8…8/8`，比较 sampled canvas 与 sampled
geometry。整个文档是零权威诊断：`0/8` 只能识别基础动作越界，不能成为 body-sway 候选；只有
非零 gain 的两类检查同时通过，才返回一个 `unvalidated_draft`。即使出现 draft，操作者仍须回
P10.1 明确确认新 revision，再重跑 P10.2，系统不得直接把诊断写成 current decision。

同一 exact schedule 还只生成一次完整 pose/attachment geometry，再由该证据派生
`DynamicViewportFit v1` 与所有越界 region 的 `RegionRebindCandidates v1`。后者默认只比较
当前骨和同链一跳父/子骨，始终是 `authority: none`。A 旧链对
`layer-007-handwear-l: forearm.left → upper-arm.left` 的建议曾显示骨段覆盖由 1 增至 2、
root-compensated motion extent 改善约 `31.81%`、最大 viewport overflow 诊断约从
`157.26 px` 降至 `25.54 px`。操作者已明确确认并保存 revision 6；新 Manifest/P2–P5 与 P9 草案
已按新身份生成。该采用动作不证明视觉或接缝正确，旧 P3/P5/P9/P10 派生产物只保留历史证据。

历史 B exact P9/P10 链在 `8/8` 有 `334/334` 个 canvas 失败 tick，在 `0/8` 有 `333/334` 个，
关联 `layer-006-objects`、`layer-000-back-hair` 与 `layer-008-hand-r`；因此只能断言该旧链不存在
纯参数候选。revision 16 改变上游身份后，必须先完成新 P9，再重建 P10.0/P10.1 并重跑 P10.2，
不能假设 B 的新链仍失败或已经修复。A revision 6 已完成 current P9、P10.1 与 P10.2 重建，
当前报告的唯一结构拒绝项是旧素材框 containment；B revision 16 仍须按自己的 current chain
完成同序重建。A 的 P10.2b CaptureFraming 已接受 revision 1，已经具备生成 Preview v2 的
authority；六次历史 execution 失败且未发布部分证据，runner 1.1.0 的后续 execution 已完成
43/43，P10.3c v2 sampled visual head 已在 revision 1 全部通过。

## 已完成垂直切片：P10.2b CaptureFraming 与 P10.3 v2

现有 `DynamicViewportFit v1` 只是一项 candidate-only 的 combined-pose 查看建议；它声明
`authority:none`，也没有被 TemporaryPreview v1 或 RuntimeCapture v1 封存。现有 v1 还固定
`world_viewport.x/y=0`，并要求内嵌 P10.2 report 为 `manual_visual_required`。这些语义必须冻结，
不能通过放宽 validator 或改写旧 report 来接纳非零取景。

本阶段已经交付下列版本化合同：

1. `CaptureFramingCandidate v1` 绑定 current P10.0 candidate、P10.1 revision/decision、
   P10.2 report、精确 P3/P5/P9 地址和 analyzer profile。证据必须显式覆盖 `setup`、所有 `base`
   ticks 和所有 `combined` ticks 的 attachment geometry，而不是只复用当前 combined envelope；
   输出直接针对固定 640×640 capture aspect，包含 margin、有限的 world viewport 与完整 evidence digest。
2. `CaptureFramingDecision v1` 与候选分离，支持 `accept/adjust/reject/unobservable`。
   页面可以预选确定性的 `accept`，但只有一次显式确认才写 decision；`adjust` 后必须重跑三类包络
   containment。candidate、current head、source/profile 任一变化都会使旧决定 stale。
3. `TemporaryBodySwayPreview v2` 不修改 v1 准入：原本已经是 `manual_visual_required` 的链继续走
   冻结 v1；新 v2 只在 report 为 `structural_rejected` 且拒绝项精确等于
   `sampled_canvas_containment`、其余结构检查全部通过/不适用，且存在 current accept/adjust framing
   decision 时放行。preview source 必须封存 framing candidate/decision/evidence SHA，capture plan 的
   world viewport 必须与决定逐值一致。原 report 的字节、状态和 SHA 保持不变。
4. `RuntimeCapture v2` 使用独立 validator、bundle、store、reader、Schema 和地址域，允许上述有限
   非零 world viewport，并把 preview v2 与 framing 身份封存到 validated capture payload。exact
   session、collector、runner 与 execution store 已在后续 P10.3 子阶段补齐；只有 completed official
   execution 才能声明本次 Runtime 已执行，单独 payload 仍只能声明 `ready_for_official_runtime_execution`。
   旧 preview/capture v1 继续按原哈希复验且继续拒绝非零 x/y；即使 v2 最终得到 0/0/canvas，也
   不能与 v1 共用 identity。

页面不会要求操作者选择 JSON 或填写 SHA：结构探针会自动加载与当前 package 绑定的候选，显示
setup/base/combined 三个覆盖域与最多四个责任附件/时刻。采用、不采用和无法判断都经过二次确认；
保存后自动刷新 current revision。取消、head 漂移、来源变化和 CAS 冲突均不会静默重试或伪造决定。

CaptureFraming 只授予“按该取景准备 capture”的权限，不修改 Rig/Motion，也不证明视觉质量、
runtime 等价、连续时间、动态 seam、安全范围或 release。P10.3c 仍须对 runtime sampled stills 做
独立人工复核；后续 P10.4/P10.5 门禁也保持不变。FK、mesh、拓扑、数值等任何非 canvas 结构拒绝
必须在进入 v2 preview 前 fail closed。

## 已完成：P10.3 package-centric 自动采集与 P10.3c v2 合同

普通操作者现在只选择项目/package；服务端自动闭合 current P10.1、P10.2、CaptureFraming、
world viewport、Preview v2、projection、plan、source 与完整 cases。固定本地 profile 校验 Spine
Player 4.2.119 的 JS/CSS/package/LICENSE 和 Chrome。只有许可勾选与本次运行二次确认同时成立，
才会创建 append-only 异步 job。页面可按 job ID 查询进度；失败或服务关闭造成的中断不会自动重试，
当前没有用户主动取消 API，partial output 不会作为 official execution 发布。

完成的 job 按 project/Preview v2/execution bundle/artifact set 四段地址封存 execution，并用完整
`job_id` 自动进入 P10.3c v2。candidate、history、decision 与 store 使用独立 v2 namespace；每个
case 都必须进入完整人工 decision，系统不自动提交或批准。页面把 43 case 压缩为 setup + 21 组
基础/摆动 A/B 时间点，默认通过仅是浏览器草稿。样本 A 当前已完成 CaptureFraming revision 1；
六次失败 job 仍不可变且没有部分 execution，runner 1.1.0 的后续 job 已完成 43/43 official Runtime
采样，P10.3c v2 revision 1 已批准全部 sampled still。

P10.3c v2 的展示性能加固已经交付：candidate 完整校验后预热全部 PNG，并签发 120 秒、固定到期、
进程内且零权威的图片读取会话；响应同时携带该次 current history。页面按完整 exact URL 创建唯一
图片节点，当前位置优先、最多两张并发，并在后台预载全部 43 帧；只有真实加载并显示的组才计入
覆盖。会话 GET 只做 job/candidate/case/PNG 精确匹配，过期、淘汰或交叉绑定失败不会回退昂贵路径；
无会话 URL 保留逐请求 current 校验供审计兼容。会话期内源漂移不会替换已经验证的旧像素，但 PUT
从不读取会话或持久 mount，会实时复验 authority/current heads 并以 409/CAS 零写入拒绝旧来源；通过
current validator 的键控进程内派生缓存仍可复用。HTTP 继续 `no-store`。跨重启冷启动还新增 completed-job
持久 mount snapshot：新 job 完成时预写，旧 job 首次读取时回填；snapshot v3 显式绑定由 292 个
静态依赖模块生成的 Preview compiler 摘要。GET 只在 exact execution、所选项目的逐字节 source/算法
seal、P3/P5/P9 内容地址、P10.1/CaptureFraming 和 Preview/artifact 全部一致时复用；无关项目与其他
adoption 不再触发该 mount 的完整重放。PUT 禁用持久 mount/图片会话，并在实时 current 校验后执行 CAS；
缓存不保存 decision、history 或 revision。真实 43-case job 完整回填约 `74.61 s`；持久 mount 下旧 candidate
准备为 `6.00–6.15 s`。加入 history 合并与全帧预热后，本次新进程真实 candidate 为 `6.15 s`；随后
43 张、共 13,139,764 bytes 的会话图片顺序读取合计 `334.1 ms`，P50 `6.7 ms`、P95 `11.4 ms`、
最大 `23.4 ms`。这是服务端/HTTP 实测；浏览器仍需完成本地 PNG decode 与 paint。

旧 execution v2 驱动继承了冻结 v1 的 `--dump-dom` 与 `--virtual-time-budget`，会和异步
collector-terminal 生命周期竞争；另一个失败窗口发生在 exact 截图已提交后，主动 teardown 与
stdout reader 关闭相互竞争。新的 v2 runner `1.1.0` 固定 `page_lifetime=collector-terminal`，移除
上述两个参数，并且只在截图已经提交、异常确由主动 teardown 引发时容忍 reader 关闭错误。提交前
读取失败、输出超限、reader/pipe 未安全关闭和截图未提交仍 fail closed。未来失败任务保存 path-free
精确 `failure_code`；历史 job 与冻结 v1 均不改写。该实现已由 43/43 completed job 覆盖真实运行路径。

## 已完成：P10.4a v2 admission/consumer

独立 P10.4a v2 已从 completed job/execution 四段地址重放 Preview v2 与 authoritative
captures，按 `history A → exact v2 decision → history B` 观察 current approved head，并输出
path-free、compile-time-only admission。任何 source/head 漂移、未完成 job、reject/unobservable
或 exact replay 失败都 fail closed。冻结 `BodySwayReviewAdmission v1`、P10.4b1 和 P10.4b2
仍只消费 v1 visual review。P10.4b v2 已沿独立合同接收该 admission；
之后仍须连接同版 seam consumer，release authority 始终保持 blocked。

## 已完成：P10.4b v2 幅度与连续结构分析

P10.4b v2 以 completed `job_id` 为唯一专业/普通入口，并在编译前后重新确认 P10.4a v2
admission 仍为 current。`BodySwayAmplitudeEnvelopeCandidate v2` 沿 coupled-gain 射线生成
`0/8…8/8` 九个结构点；`BodySwayContinuousPreviewProof v2` 对 Preview v2 的每一对相邻
tick 与统一 `λ∈[0,1]` 作有界区间细分。两份文档使用独立 Schema、profile 与自哈希，不能与
冻结 v1 工件互换。

普通页面只接收 `job_id`，自动创建或恢复 append-only 异步 run，并把结果分成离散结构点、
连续相邻段、仅覆盖 `8/8` 的视觉审批和明确不可用的可发布安全范围四条轨道。
`indeterminate` 是预算内没有形成完整证明的合法完成结果；它不会被错误显示为执行失败。

CPU 密集编译现在运行在独立低优先级 worker 子进程中。子进程经有界 canonical JSONL 协议
报告固定阶段和 `continuous_boxes` 盒级心跳，只能写入 run 绑定的 staged 工件；父进程是
append-only 事件日志和 `completed` 状态的唯一写入者，并在完成前独立重读、校验两份 staged
文档。取消或服务关闭会终止该 worker 的进程树，不会留下可被误认作完成的部分结果。页面/API
查询不再与区间证明争用同一 Python 进程；失败 attempt 保留不可变 receipt，操作者二次确认后
才能创建新 attempt。

sealed replay 已增加两项回归门禁：JSON round-trip 后的 `reason_codes/scope/exclusions`
按合同数组语义比较，避免 tuple/list 表示差异造成假失败；全局盒预算按实际剩余量逐段递减，
禁止在预算耗尽前伪造 global fallback。manager 也会区分来源变化、来源不可用、无效请求、
分析校验失败、分析失败和 worker 进程失败，不再把所有命令错误误标为 `source_changed`。

P10.5d v2 已建立独立、path-free 的 source closure，精确绑定 P10.4b v2 proof、current
P10.5c v1 双 SHA、Manifest/P3/RigIR 和 current-head 观察。纯函数 analyzer/compiler、probe
Schema、full-replay validator、CLI 和内容寻址 store/exact reader 已交付。compile 在分析前、
发布前、发布后共三次复核 current heads，再发布固定 `source/probe/bundle-manifest` 三文件
inventory 并 exact-readback；verify 只复验历史 exact bytes，不授予 current authority。尚待
server/job/UI 自动入口也已交付：exact job/run 自动解析 current P10.5c，独立 BelowNormal worker
执行，append-only attempts 保留失败回执，父进程完成 exact readback/current-head recheck。真实 A
仍待当前 P10.4b run 完成并重启服务后执行。runtime、raster、overlap、未采样视觉与 release
authority 仍保持 blocked。

## 已完成：P10.6a v2 动作消费准入

冻结 P10.6a v1 继续只接受 P10.5d v1 probe 文件。新命令
`compile-body-sway-motion-consumer-admission-v2` 使用独立 format/profile/hash domain，公开
输入只有项目与 P10.5d v2 probe/bundle 双 SHA；它按精确地址读取固定三文件 bundle，并从
source closure 自动重放 P9，不要求操作者选择文件或填写 P9 SHA。

v2 编译固定执行 `P10.5d exact read → P9 exact read → before current heads → pure core →
after current heads → seal → detached replay`，任一来源篡改、跨项目/动作串线或 head 漂移都
fail closed。命令零写入，成功输出 path-free admission 和 compile-time observation；它不
生成 MotionInstance v3、Spine adapter、Runtime 或发布权。操作入口见
[编译 P10.6a v2 动作消费准入](how-to-compile-body-sway-motion-consumer-admission-v2.md)。

版本隔离的 P10.6b v2 admission/source/bundle/run/reader 已交付。setup-local track payload
语义未改变，因此输出仍使用 MotionInstance v3；冻结 P10.6b v1 不会静默接收 v2 admission，
也没有仅为来源版本变化创建 MotionInstance v4。真实 A 仍需先完成当前 P10.4b run 并实际执行
P10.5d–P10.7a v2，测试 fixture 不能作为这条真实凭据。P10.7a v2 source adapter、自动 UI 与
P10.7b v2 source bridge、严格 session、collector、loopback server、Windows real browser runner
与 captured-unreviewed evidence/bundle/store/exact reader 已交付。guarded v2 runtime authorization 已于 4254151 交付；后续优先推进 PipelineRun 与一键 Spine。

## 已完成横向前置：Resolved Project v1

P0 已在正式冻结点交付独立 `schemas/resolved-project-v1.schema.json` 与无第三方依赖的严格
语义 validator，并修正撤销 split authoring 后 stale QA 消失的 pre-P0 缺陷。公开 validator
重算 canonical 内容地址，校验 project/layer/joint/bone 交叉引用、candidate inventory/run
identity、current/stale split provenance，以及由 resolved 实体状态派生的完整 QA 列表。

该修正可能改变相应临时状态重新生成时的 QA/SHA，但不会把旧决定静默标为 current。历史回归
确认两份真实样本的 r5/r7 snapshot 哈希未受影响；当本地缺少对应 audit 或历史 revision
fixture 时，该真实样本用例会明确跳过，不能据此宣称它已在当前环境执行。Draft 2020-12
Schema 的实例校验同样依赖可选 `jsonschema`，但 Python 语义 validator 及其测试不依赖该包。

v1 的字段、哈希算法和语义现已冻结。未来只要 resolved 生成算法、QA 派生规则或 provenance
解释发生语义变化，就必须发布 `autospine.resolved-project/v2` 及新的 Schema/validator；不得
沿用 v1 token、改写 r5/r7 历史地址，或让既有 candidate/split 决定静默获得新含义。完整
合同见 [Resolved Project v1 参考](resolved-snapshot-reference.md)。

## Revision 历史浏览与恢复 UI

**建议优先级：P1。历史已存在，但当前主工作台没有浏览或恢复入口。**

依赖：append-only override history、override v3 validator、当前 `base_revision` CAS 和候选/split 重新绑定逻辑。

交付：

- 历史索引与精确 revision 的只读 API，返回受限摘要和 canonical 客户端字段；
- 主工作台中的 revision 列表、字段差异预览和“载入为恢复草稿”；
- 恢复时以当前 head 为 `base_revision` 走普通 v3 保存，创建一个新 revision；
- 冲突、候选缺失、split stale 和历史内容损坏的 fail-closed 提示。

验收条件：浏览历史不写 state；恢复 r3 时 r1–rN 字节和 SHA 均不改变，而是追加 rN+1；两个页面并发恢复只有一个 CAS winner；历史候选算法已变化时不能冒充 current accept；刷新后可以读回新 revision，并保留“来源 revision”审计说明。

主要风险：把“恢复”错误实现为覆盖 `latest.json` 或修改历史 slot；历史中已失效的 candidate/split 决定被错误升级；大型 revision diff 造成浏览器内存或敏感备注泄漏。

## 主工作台 Spine 导出编排入口

**建议优先级：P1。离线 P6 已完成，但当前 Project API 仍明确返回 `export_spine=false`。**

依赖：精确 P3/P5 地址、现有 `compile-spine42`/`verify-spine42`、P6 capability profile，以及受限本地命令执行或人工 PowerShell 交接策略。

交付建议分两步：

1. 主工作台增加“Spine 4.2 导出”表单，显式选择/填写 P3 与可选 P5 双 SHA，先做只读校验，再生成可复制的精确 CLI 命令。
2. 若确需在页面内执行，再增加 allowlist job service：只接受结构化 command ID/参数，不接受任意 shell；提供明确确认、进度、取消、日志脱敏和精确输出地址。

验收条件：UI 与 CLI 对同一地址生成相同参数和结果；不解析 `latest`，不自动选择首项；未知版本或能力不匹配时阻止导出；命令复制模式不得把 `export_spine` 宣称为可执行能力，只有安全 job path 实际交付后才可改变该 capability；成功后按精确 bundle 地址回读并显示 verify 结果。

主要风险：把本地 HTTP 变成任意命令执行入口、长任务阻塞 server、参数或路径注入、旧 bundle 被误选，以及把 Spine Runtime/Editor 许可误当成代码已解决的问题。

## 已完成：P10.6b v2 MotionInstance v3 来源合同与 Bundle

P10.6b v2 已交付独立 core、prepared pipeline、bundle/run/filesystem namespace、store、exact
reader、compile/verify CLI 和从 certified P10.5d 完成态进入的自动页面。普通页面无需项目、文件
或 SHA 输入；专业操作入口见
[编译并复验 P10.6b v2 MotionInstance v3](how-to-compile-motion-instance-v3-v2.md)。

公开 compile 输入只有项目与 P10.5d v2 probe/bundle 双 SHA；命令自动读取 exact P10.5d、从
source closure 读取 P9、生成并 detached-replay P10.6a v2 admission。公开 verify 输入只有项目
与 MotionInstance v3/bundle 双 SHA；两者都不选择文件或扫描 `latest`。

已交付边界：

- setup-local payload 继续使用 `format_version=3` 和既有 profile/shape；
- admission/source closure、bundle address domain、filesystem namespace 与 run manifest 升级到 v2；
- 固定三文件 inventory 为 admission-v2、MotionInstance v3 与 run-v2；
- MIv2 root translation、markers、stepped draw order 逐值保留，rotation overlay 只允许躯干四骨；
- command 与 store 分层复查 current visual-v2/seam-v1 heads，发布后按 exact 双 SHA 读回；
- historical verify 重建 P10.5d/P9/admission/payload/run，但不观察或授予 current-head authority；
- v1 literal admission/MIv3/bundle/Spine hashes 继续冻结。

run-v2 只授予 `motion_instance_v3_emitted=true`。attachment area overlap、dynamic seam safety、
完整 attachment 边界、raster/视觉、官方 Runtime、永久 head authority、Spine adapter、
publishable timeline 与 release authority 均固定 false/blocked。

版本匹配的 P10.7a v2 source adapter 与自动入口已由下方独立阶段交付。冻结 P10.7a v1 虽然
消费相同 format v3 payload，却绑定 v1 bundle/source contract；不得把 P10.6b v2 双 SHA 直接
交给它或静默扩写旧 reader。真实 A 尚未实际到达 P10.6b v2，不能用机制测试替代资产凭据。

## 已完成：P10.6b v1 MotionInstance v3 与 timeline compiler

P10.6b v1 已交付并冻结。它只消费 P10.6a v1 wrapper；P10.6a v2 已由上方独立 P10.6b v2
来源合同消费。操作入口见
[编译并复验 P10.6b MotionInstance v3](how-to-compile-motion-instance-v3.md)。

依赖：

- 认证的 `BodySwayMotionConsumerAdmission v1`；
- 精确 P9 MotionInstance v2/reviewed bundle；
- P10.3c visual head 与 P10.5b seam head 的 current-state reader；
- setup-local rotation、root translation、marker 和 stepped draw-order 现有语义。

已交付：

- `MotionInstance v3` JSON Schema、值对象和语义 validator；
- pure timeline compiler，将 unit-gain body-sway rotation 与 MIv2 基础 channel 明确合成；
- compile run、不可变 bundle、严格 reader 和独立 verify 命令；
- source closure 内嵌 admission/P9 精确身份，公开命令与 store 都在待发布值构造前后重新检查两个 current head；
- 发布后精确地址读回、64 MiB admission 上限，以及只开放 v3 emitted 的 authority/blocked release gate；
- 对 channel 冲突、tick 重复、loop closure、非有限数和不支持 interpolation 的 fail-closed 规则。

已关闭的进入下一阶段条件：

- 同一 canonical 输入产生相同 MotionInstance/bundle SHA；
- 完整 reader 能从精确地址逐字节重编，不扫描 `latest`；
- visual 或 seam head 在消费期间漂移时不发布任何 bundle；
- MIv2 root、marker、draw-order channel 逐键保留，body-sway rotation 只影响允许的四骨；
- loop、有限数、setup-local 语义与既有多 rig MotionIR/P9 回归保持通过；
- release gate 仍明确 blocked，不能在本阶段声称 Spine Runtime 或 raster 通过。

保留边界：head observation 只覆盖本次发布前编译，不是永久 authority；历史 verify 只证明精确
字节可重放。冻结 Spine adapter bundle 已由 P10.7a v1 关闭；v2 来源由下方独立 P10.7a v2 adapter 消费。
P10.7b 只增加 sampled official-runtime raster evidence 与人工 decision，不会授予连续时间或 release authority。后续维护必须继续
防止 current-head TOCTOU、MIv2/channel 合成和插值语义漂移。

## 已完成并冻结：P10.7a v1 Spine 4.2 v3 Adapter 与五文件 Bundle

P10.7a v1 已交付并冻结。它只消费 v1-source P10.6b bundle；不能静默复用到 P10.6b v2，
该独立 v2 adapter 现已由下一节交付。冻结入口见
[编译并复验 P10.7a Spine 4.2 v3 Bundle](how-to-compile-spine42-v3.md)。

已交付：

- 独立 adapter profile `3.0.0`，显式支持 rotation、root translation、marker、stepped draw order、region 与 weighted mesh；
- 未知 timeline、attachment、constraint 和 interpolation fail loud，不修改或扩写旧 P6 profile/hash；
- 公开编译输入只有 project 与 MIv3 双 SHA，并完整重放 MIv3→P9→P5/P3→RigIR/源 PNG；
- 固定 JSON/atlas/PNG/run/report 五文件库存与独立 `spine42-v3` 内容地址；
- command/store current-head 门禁、原子写入、发布后精确读回，以及不观察 current heads 的历史 verify；
- 300 行生产文件硬门禁与 P6/P10.6b 零回归。

已关闭的进入下一阶段条件：同一输入产生相同 skeleton/bundle SHA；任一上游跨线或文件篡改
fail closed；历史 reader 能从完整上游逐字节重建；run 唯一授予 `spine_adapter_emitted=true`。
官方 runtime、raster、永久 head、publishable timeline 和 release authority 均保持 false/blocked。

## 已完成：P10.7a v2 Spine 4.2 v3 Adapter 与自动入口

P10.7a v2 已交付独立 source contract、adapter profile、skeleton hash、run/report 合同、
`spine42-v3-v2/<skeleton-sha>/<bundle-sha>` 地址域、五文件 store/exact reader、compile/verify CLI，
以及从 completed P10.6b v2 成功态进入的非专业页面。操作见
[自动生成并复验 P10.7a v2 Spine 4.2 v3 Adapter](how-to-compile-spine42-v3-v2.md)。

已交付边界：

- 页面自动携带 `job_id+safety_run_id+dynamic_run_id+motion_run_id`，不选择项目、文件或填写 SHA；
- append-only attempt 在首次就绪时自动创建，失败只有确认后才创建新 attempt，completed 重读幂等；
- 固定 inventory 为 `skeleton.json`、`skeleton.atlas`、`skeleton.png`、`run-manifest.json`、`export-report.json`；
- compile 只收项目与 P10.6b v2 MIv3/bundle 双 SHA，verify 只收项目与 skeleton/bundle 双 SHA；
- compile/store 观察 current heads，发布后按精确地址读回；历史 verify 不读取或授予 current authority；
- v1/v2 source、skeleton hash、run/report、bundle identity 与 reader namespace 互不混用。

已关闭的机制验收：同一 canonical 输入产生相同 skeleton/bundle SHA；来源跨线、inventory 篡改或
地址错配 fail closed；历史 reader 从完整上游逐字节重建五文件。authority 十项中只有
`spine_adapter_emitted=true`；attachment overlap、dynamic seam safety、完整边界、官方 Runtime、
Runtime 等价、raster、永久 head、publishable timeline 和 release authority 均为 false/blocked。

机制通过不等于真实 A 已完成 P10.7a v2。冻结 P10.7b v1 capture/reader 不能消费 v2
skeleton/bundle SHA，P10.7a v2 页面也不得自动运行外部采集。

## 已完成：P10.7b v2 Runtime Evidence Store

source bridge 按项目、P10.7a v2 skeleton SHA 与 bundle SHA
调用 exact reader 历史重放固定五文件，不读取 current heads，再确定性生成
`official-runtime-capture-plan-v2.json` 与 `official-runtime-source-admission-v2.json`。
source contract、runtime profile、plan 和 admission 使用独立 v2 哈希域；v1 来源、跨版本重封装
或任一上游篡改均 fail closed。

admission 只开放 `p10_7a_v2_exact_replayed` 与 `bounded_capture_plan_emitted`。严格 v2 session set
按 capture-plan artifact 顺序逐项绑定 admission、plan、Runtime JS/CSS 字节、adapter
skeleton/atlas/texture 与预期 observables。bounded in-memory collector 只接受每个 artifact 一次
capture/error 终态，并限制单 PNG、总字节和错误文本；loopback-only server 校验 Host、Origin、
路径、方法、content type 与所有输入身份。

`run_spine42_v3_runtime_capture_v2` 已把这套合同接到 Windows real browser runner。它先要求
`license_acknowledged is True` 和 Windows，再对精确 P10.7a v2 bundle 执行一次 exact read；执行期
锁定 Spine Player 4.2.119 Runtime 与浏览器 executable lease，并为每个 artifact 建立全新浏览器
profile 和 loopback capture URL。Runtime/浏览器身份漂移、跨版本、篡改或交叉接线均 fail closed。

runner-issued 结果现可生成 `captured_unreviewed` evidence。固定前缀 inventory 为 manifest、plan、
admission、session set、runtime reports 五份 canonical JSON，再按 capture plan 顺序附带 PNG；
manifest 只声明 official Runtime loaded、capture completed 与 isolated attachment raster captured，
不声明 metrics、人工视觉、Runtime 等价或 release。

bundle 使用独立 `spine42-v3-runtime-v2` namespace 与 v2 address domain。atomic store 在写入前后
完整 replay，并使并发相同发布收敛到同一不可变地址；exact reader 只接受 project、skeleton SHA、
P10.7a v2 bundle SHA、capture bundle SHA 四段地址，单次读取上游和每个声明文件，拒绝缺失、额外、
错大小写、alias、篡改和跨线输入，也不观察 current heads。

当前没有 P10.7b v2 完整 CLI/UI、raster metrics、人工复核或发布权；guarded 授权内核已交付，执行/API 为接续工作区改动；官方 Runtime 等价、
视觉、永久 head、可发布 timeline 与 release authority 仍为 false，gate 固定 blocked。机制测试
使用模拟/替身边界，没有真正启动经授权的官方 Runtime。冻结 v1 reader、session、合同和输出哈希
保持不变。guarded v2 runtime authorization 已于 4254151 交付；后续优先推进 PipelineRun 与一键 Spine；外部执行始终要求操作者明确许可。

## P10.7b v1：Raster 基础设施已交付，v2 真实双样本验收待完成

**历史优先级：P0；现归入 Certification Core 维护。基础设施可用；真实资产验收仍需要外部授权环境。**

依赖：冻结 P10.7a v1 五文件 bundle，以及操作者提供并明确确认有权使用的
`@esotericsoftware/spine-player@4.2.119`。仓库不会从 CDN 回退、捆绑 runtime，或把包内
`LICENSE` 文件存在当作授权确认。

已交付：

- 固定 runtime 版本、canvas、DPR、case/tick、setup attachment inventory 和资源上限的 capture plan；
- runtime JS/CSS、`package.json`、`LICENSE`、浏览器可执行文件与 P10.7a v1 来源的精确身份封存；
- opaque/transparent composite 与每个 setup attachment isolate 的正式浏览器捕获通路；
- alpha union、missing/extra/xor、边界、裁切和 isolate 非空的 sampled raster 指标；
- manifest/metrics/PNG 的不可变 store、精确 reader 与 P10.7a v1 source replay；
- candidate 与人工 decision 分离，逐 case、逐 attachment 的 exhaustive review 合同；
- capture、verify、prepare、submit 四个 CLI 与功能入口中心接入。

`capture` 标记为 `external_required`；其余命令在已有精确 capture 上可直接使用。capture
证据的 authority 只覆盖“目标 runtime 已在本次固定会话加载、attachment isolate 已捕获、
sampled 指标已计算”。candidate 不声明人工判断；decision 也只覆盖操作者显式复核的离散
case 和 setup attachment inventory。continuous time、永久 current head、publishable timeline、
publish/release authority 固定为 false/blocked。

仍待完成的真实验收：

- 两份真实 See-through 样本都要先产生可精确重放的 P10.7a bundle；
- 两份样本分别使用已授权官方 Runtime 完整 capture，test stub 与另一角色证据不可替代；
- setup 与既有 P6 golden 对照，不允许未批准变化；
- 每份 capture 都要按地址复验，并由操作者逐 case、逐 attachment 形成完整 decision；
- 至少一个结构差异 fixture 继续作为工具链回归，但其通过不等同于真实样本视觉通过。

真实双样本完成后，P10.7b 也只形成 bounded sampled evidence。若产品需要连续 runtime raster
安全、永久审批或发布授权，必须建立新的独立合同和验收阶段，不能扩写现有 decision 的含义。

操作入口见[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)。

主要风险：Spine interpolation 与版本中立语义不完全同构、不同 GPU/浏览器 raster 差异、
真实样本缺少 P10.7a 前置地址，以及官方 Runtime 获取和许可条件。

## P10.7b-readiness：真实样本精确地址审计

**历史优先级：P0；现归入 Certification Core 维护。审计入口已交付；报告显示真实链仍被更早前置阻塞。**

`audit-body-sway-spine42-v3-readiness --manifest ... --state-root .\workspace
[--document-only]` 接受一个 strict canonical 单行请求。请求必须显式固定每个项目的 Layer
Manifest、P3 rig/bundle，以及可选的 P9、P10.5c、P10.6b、P10.7a、Runtime capture 与
raster decision 地址。命令会在内存中运行只读 pure replay compiler/validator 来重建并验证
声明的 exact artifacts；它不扫描 `latest` 或 current review head，不运行外部阶段、官方
Runtime、capture、发布或写入，不代替人工决定，也不授予 publish/release authority。操作与示例见
[审计两份真实样本的 Spine 4.2 v3 就绪状态](how-to-audit-spine42-v3-readiness.md)。

冻结的示例 Manifest 固定两份已审计的真实 Manifest/P3 地址，后续五组地址与 raster decision
全部为 `null`。它不代表当前工作区没有 P9；真实 P9 双 SHA 已通过 exact reader，见
[pilot handoff](pilots/kimodo-wave-left-v1.md)。审计只能对请求中显式声明的地址给出结论：

| 项目 | 最早共同动作 blocker | 接缝 blocker | Runtime 状态 |
| --- | --- | --- | --- |
| `seethrough_output` | 换绑已确认并形成 r6，current P9/P10 已重建 | P10.5c 已精确复验；P10.5d v2 自动入口已交付，等待当前 P10.4b run 完成并重启服务后真实执行 | CaptureFraming、43/43 Runtime、P10.3c v2 已通过；真实 P10.4b run 正在留档 |
| `seethrough_output_5` | 历史 P9 exact reader 已通过；r16 新 P9 draft 尚待晋级和最终 adoption | 历史 P3 candidate 的四条腿/脚不可观测结论不能替代 r16 新链复验 | 官方 Runtime 包与 P6 baseline 可用，但 r16 须重建 P10.0/P10.1、重跑 P10.2 后再判断更早 blocker |

A 的冻结 baseline checkpoint 可表述为 `reviewed_seam_anchor_set_address_not_declared`，因为该请求
没有声明 current 地址；这不代表工件不存在。A r6 current P10.5c 双 SHA 已闭合，应由未来明确
支持该版本链的请求填写 `00de666e…`/`e23e3792…`，不得换成旧链双 SHA，也不得反向改写冻结请求。

项目 B 不得把 `unobservable` 自动改成 accept。进入完整 P10.5c 前必须修复上游腿/脚语义或
See-through 分层，并让新的 Manifest/P3/candidate 内容地址失效旧决定；若产品确实接受缺腿脚
接缝，只能另立版本化 partial seam 合同、能力边界和独立验收，不能扩写现有六关系合同。

最短后续顺序：

1. 从 [pilot handoff](pilots/kimodo-wave-left-v1.md) 读取 A r6 current P9/P10.5c 与旧链地址；两条链必须按各自身份精确读取，不能互换。
2. A 从 runner 1.1.0 的 completed job、P10.3c v2 revision 1 和 P10.4a v2 继续生成并留档同一 job 的 P10.4b v2 amplitude/continuous 结果；六次失败 job 只保留为不可变历史。
3. 当前 P10.4b run 完成并重启服务后，从完成页一键进入 P10.5d v2，对 A 执行真实验证；冻结 v1 compiler 继续拒绝 v2。
4. B 在 Motion Policy 页面完成 r16 P9 adoption，再重建 P10.0/P10.1/P10.2；针对 2 可审 + 4 `unobservable` 的 current seam candidate 先修复上游或批准独立 partial 合同。
5. 在精确 P9/P10.5d v2 地址上运行已交付的 P10.6a/P10.6b v2；每次只使用实际生成的双 SHA，不能把 v2 admission 或 bundle 交给冻结 v1 consumer。
6. 从 P10.6b v2 成功页进入已交付的 P10.7a v2 自动页面，生成并 exact-readback 版本匹配的五文件 adapter；只记录实际回执，不把机制测试当作 A/B 凭据。
7. 用已交付的 P10.7b v2 source/session/real browser runner，从同一 P10.7a v2 双 SHA重放 blocked admission/plan 并构造固定 artifact sessions；只有显式许可真值与 Windows 才能执行。
8. 用已交付的 evidence/bundle/store/exact reader 把 runner-issued 结果原子封存为 captured-unreviewed 四段地址；这仍不是 metrics、人审或 release。
9. 开发自动授权入口；经操作者确认官方 Runtime 授权后，用完整 v2 持久化链执行 capture、精确复验和后续逐 case/attachment 人工决定。
10. 使用已交付的 `compare-body-sway-spine42-v3-setup-golden` 独立比较 setup case 与既有 P6 approved golden。readiness v1 已冻结且不会消费这份报告；即使前述检查通过，它的第八项仍保持 missing，只会给出 `ready_for_p6_setup_comparison`。

进入真实验收的条件：请求中每条依赖均由 exact reader 复验，A 的 seam 决定来自真实人审，B
满足明确选择的完整或新 partial 合同，官方 capture 与 raster decision 均与同一 P10.7a 地址
闭合。审计报告本身不是 pipeline runner、人工签字或发布许可。

## P10.7c-setup-regression：独立 P6 Setup Golden 对照

**当前阶段：实现已交付；真实 A/B 仍被外部前置阻塞。**

`compare-body-sway-spine42-v3-setup-golden` 读取独立 strict canonical 请求、固定 P6 export/runtime
golden 合同和精确 P10.7a/P10.7b 地址。它以冻结 comparison profile 和显式 P3 防止旧请求
静默复用新语义，只读证明 P6 与 P10.7a 绑定同一 P3、atlas/texture 身份不变、capture 来源与
固定 Runtime profile 闭合，再把唯一 opaque setup 帧与 approved PNG 计算 RGBA 指标。gate
会从 exact evidence 在内部重新计算 sample；报告自哈希只表示内容身份。命令不启动 Runtime、不扫描
`latest`/current head、不写 state，也不修改 approved golden。完整操作见
[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。

readiness v1 的 Schema、哈希和八项 checkpoint 已冻结；第八项仍固定为
`p6_setup_golden_comparison_not_declared`。P10.7c 使用独立合同，避免让旧请求或报告静默获得新含义。
当前只能确认机制与既有 P6 批准基线可被严格验证，不能声称真实 A/B 通过：共享的
`wave-left-v1` 历史链已到达 P7/P8、两个目标 P5 与各自 exact replay 通过的 P9；A r6 已完成
current P9/P10 与 P10.5c 静态集；P10.5d v2、P10.6a/P10.6b v2、P10.7a v2 自动机制和
P10.7b v2 source/session/real browser runner/evidence store/exact reader 已交付，但仍缺真实
P10.5d–P10.7a v2 凭据、自动授权入口及其后续真实 capture/metrics/review；B r16 仍停在
新 P9 草案及 2 可审 + 4 `unobservable` 静态关系。只有这些前置关闭后，
才能生成真实 canonical 请求并执行两项目对照。当前 stdout
报告仍是临时、不可寻址工件；进入 readiness v2 前还要交付封存 request/report、批准合同和批准
PNG 的 immutable comparison bundle，并由 reader 重放实际 capture。

## Spine Editor 工程生成与更多版本 Adapter

**建议优先级：P2；在 Spine 4.2 的 P10.7 证据链稳定后再扩展。**

依赖：版本中立 RigIR/MotionInstance 合同、P6/P10.7 capability matrix、操作者合法安装的目标 Spine Editor/Runtime，以及每个目标版本的明确格式资料和测试环境。

交付：

- 每个版本独立的 adapter package、profile ID、Schema 和不支持特性矩阵；
- 版本探测只输出 evidence，不猜测或伪造未知版本；
- 对可依法生成的 Spine Editor 工程建立独立 exporter、manifest 和导入检查；若格式或许可不允许可靠实现，则保持 `external_required/blocked`，提供 JSON/atlas 交接而不冒充 Editor project；
- setup、mesh、deform、constraint、timeline、attachment switch 的逐版本 golden 与 migration report。

验收条件：每个声明支持的版本都由对应官方 Editor/Runtime 实际加载；同一版本重复导出内容地址稳定；跨版本转换不支持的字段必须 fail loud；4.2 现有 bundle/golden 不回归；产物、runtime 和许可证来源均有明确记录，仓库不捆绑或再分发受限组件。

主要风险：Spine Editor 工程格式并非稳定公开交换合同、版本字段与实际语义不一致、不同 runtime 的 interpolation/constraint 行为漂移，以及许可证限制使自动化只能停留在外部工具交接。

## Attachment switch 基础合同

**建议优先级：P1；在眨眼和口型之前完成。**

依赖：RigIR slot/attachment 身份、MotionIR/MotionInstance 离散时间线、P6 capability matrix。

交付：

- 版本中立 `attachment_switch` timeline；
- slot 内附件集合、setup 默认值、离散 key 和缺失附件的 validator；
- candidate、人工 decision、reviewed switch policy 三层合同；
- P6 Spine 4.2 adapter 支持及 fixed-tick screenshot probes。

验收条件：相同 tick 的覆盖优先级确定、loop 首尾状态闭合、未知附件失败、三套不同附件数量的 rig 通过，且既有不含 switch 的哈希和结果保持不变。

主要风险：See-through 分层不一定包含开/闭眼或口型素材；同一 slot 的尺寸、pivot 与 draw order 不一致会造成跳动。

## 自动眨眼

**建议优先级：P1。**

依赖：attachment switch；经过人工确认的眼部语义、左右配对、open/closed 或 eyelid 素材。没有足够素材时必须 `unobservable`，不能从单张眼睛伪造可靠闭眼。

交付：

- 眼部附件可用性与左右同步候选；
- 可配置 blink 周期、持续时间、左右相位和随机种子的确定性 schedule；
- accept/adjust/reject/unobservable 决定；
- 编译到通用 switch timeline，并接入 P6 runtime capture。

验收条件：固定 seed 生成相同 schedule/hash；无过短闪烁、首尾闭合和重复 tick；至少三种眼部素材结构通过；两份真实角色分别得到可用或有证据的 blocked 结论；人工复核与官方 Runtime 截图通过后才可交付。

主要风险：头发遮眼、非对称表情、绘制风格差异、缺少闭眼素材，以及左右同时切换产生的视觉跳变。

## 自动口型与音素映射

**建议优先级：P1，可在 blink 合同稳定后并行。**

依赖：attachment switch、经过人工确认的嘴部附件集合；若使用音频，还需要独立的时间轴和外部音素/能量 evidence adapter。

交付：

- `rest/open/wide/round` 等最小 viseme inventory，不强制假定日语或英语专用集合；
- audio/phoneme evidence 与候选 viseme timeline 分离；
- 手工修正、静音回落、最短保持时间和抖动抑制；
- 通用 timeline、Spine 4.2 adapter 与 fixed-tick 视觉证据。

验收条件：静音稳定回到 rest；相同 evidence/map 产生相同 timeline；缺失 viseme 有显式 fallback 或 blocked；至少三段不同节奏输入和三个 rig 通过；音画对齐误差有固定指标并保留人工复核。

主要风险：单张分层图缺少完整口型、音素模型语言偏差、快速切换闪烁、音频隐私与模型许可证。

## 头发弹簧与次级运动

**建议优先级：P2。首版优先离线 bake，不直接做 runtime 物理。**

依赖：已确认的发束图层、hair chain/pivot authoring、稳定的角色主动作；长发连续弯曲还依赖多骨权重或 deform。

交付：

- hair chain 候选与人工修正界面；
- 固定步长、显式质量/阻尼/刚度/重力参数的确定性 spring solver；
- 角度限制、body/head 简化碰撞和失稳检测；
- bake 后的 setup-local rotation/deform timeline 与 probe bundle。

验收条件：相同输入逐字节确定；静止收敛、镜像、不同 FPS 和极端参数无 NaN；能量/角度不越界；loop clip 首尾可接受；至少短发、双束、长发三种结构通过视觉回归。

主要风险：See-through 发束边界和遮挡顺序不可靠、2D 碰撞近似、solver 爆炸、长发刚性骨链观感不足。

## See-through 与姿态模型离线 Runner

**建议优先级：P2，作为独立输入质量轨。**

依赖：操作者提供模型、权重、运行环境和许可证；现有 audit/COCO17 adapter 保持为稳定下游边界。

交付：

- job request、model identity、seed、环境和输出 manifest；
- See-through 多 seed 离线运行、候选评分和人工选择，不自动把“最高分”当 approved；
- pose runner 将原始输出封存后再进入现有 `import-pose`；
- 失败重试、资源上限、GPU/CPU 环境记录和可恢复队列。

验收条件：输入、权重、配置和 seed 可追溯；同环境重复运行身份稳定，无法保证位级确定时显式记录差异；两份真实样本完成推理→audit/pose→候选链；模型失败不会污染已发布下游。

主要风险：显存、运行耗时、模型 nondeterminism、权重许可、多 seed 成本，以及自动评分与人工美术偏好的错位。

## P3/P5 v2 分段四肢网格

**建议优先级：P2；当前 profile-v1 继续保持 leg-only。**

依赖：已审的上臂/前臂或大腿/小腿分层、明确肘/膝 pivot、P2 region setup，以及新的版本化
mesh compile、motion target 与 regression 合同。合并袖臂若没有可用肘部分割，只能保持 rigid，
不能仅靠把 `deform_class` 改成 hinge 获得可靠结果。

交付：P3 v2 eligibility/profile/schema/reader；arm-aware 中轴线和参数化权重；分段腿映射；
P5 v2 mesh regression；v1/v2 双读与能力矩阵；极值姿势、热图、接缝和 Runtime goldens。

验收条件：v1 地址和 golden 不变；至少三套真正分段的 rig 在 setup 精确重建；左右臂腿的权重和、
拓扑与 winding 不变量通过；安全角内无翻三角、明显裂缝或超限拉伸；P5 与官方 Runtime 固定帧
通过。当前样本 B 的临时 arm mesh 在 `+15°` 已翻转、`-30°` 拉伸超过 v1 上限，因此不能作为
通过 fixture；应先改善分层、拓扑或权重。

主要风险：合并衣袖没有真实肘部可变形边界、alpha 拓扑跨越遮挡、自动中轴线错误、arm/leg
合同与现有 leg-only schema 不一致，以及通过数值探针却仍产生风格化视觉裂缝。

## 自由形变与多骨权重

**建议优先级：P2。**

依赖：P3 alpha mesh、稳定 attachment 语义、明确哪些区域无法由 region/two-bone LBS 满足。

交付：多骨权重合同、weight authoring/候选、deform timeline、拓扑不变量、热图与极值姿势回归；P6 对不支持组合保持 fail loud。

验收条件：权重和、索引和 winding 不变量通过；setup 精确重建；极值姿势无翻三角、明显裂缝或越界；同一 deform clip 至少在三个兼容 rig 上通过；不合格输入显式 no-op/blocked。

主要风险：自动权重对风格化服饰不稳定、拓扑密度与性能、遮挡补全不足在大幅动作中暴露。

## Runtime IK Constraint

**建议优先级：P2；保留当前离线 IK 作为基线。**

依赖：P4 analytic IK profile、目标 Spine 版本 capability matrix、target timeline 和弯曲方向 authoring。

交付：版本中立 constraint contract、P6 显式 adapter、target/mix/bend timeline、离线 bake 与 runtime constraint 的 A/B probes。

验收条件：reachable/unreachable/镜像/退化输入无 NaN；setup 与离线解一致到固定容差；不支持版本或 mesh 安全角越界时拒绝导出；官方 Runtime 固定帧回归通过。

主要风险：runtime solver 与离线公式差异、constraint 顺序、scale/shear 组合和 mesh 安全范围。

## 真实 Kimodo/P9 质量门禁

**当前状态：A 已闭合 current P9/P10、CaptureFraming、43/43 Runtime、P10.3c v2 与 P10.5c。P10.5d v2 自动入口已交付；A 的下一步是等待当前 P10.4b run 完成、重启服务并真实执行，不是重做静态复核。B revision 16 仍须完成自己的 current chain 并解决四条 `unobservable`。**

样本 B revision 16 的新链仍有独立限制：`layer-008-hand-r` 保留
`body.arm.upper → upper-arm.left`，但在 leg-only P3 v1 中为
rigid region，P3/P5 mesh 检查诚实返回 `reviewed-noop`。`ankle.left=unobservable` 也没有使
现有启发式骨端成为真实足点；左腿 root correction/foot-lock 必须保持人工阻塞。完成新 P9 后，
B 必须先重建 P10.0/P10.1、重跑 P10.2/P10.2a；canvas、seam 与 Runtime 结论都要按新地址重新
建立，不能搬用旧 current head 或历史 334/333 结果。

依赖：可合法使用的真实 Kimodo checkpoint 输出、checkpoint manifest、generation request、recorded sidecar、显式 map/camera、现有 P7–P9 精确链和人工 policy review。

已交付的 M1.0 `audit-kimodo-pilot-intake` 会安全读取六份精确文件，要求两份 provenance 原件的逐字节 SHA 与 recorded sidecar 闭合，在内存中重跑 P7 结构编译，并验证 camera/map 一致性。输出是 path-free、自哈希、零写入报告；它明确把 checkpoint authenticity、动作质量、P8 projection、P9 review 与 release authority 保持为 false。操作见[审计真实 Kimodo Pilot 输入](how-to-audit-real-kimodo-pilot-intake.md)。

已交付的 P9 安全收口把 policy identity 和 candidate inventory 从浏览器推断改为 loopback-only、zero-write Python preflight；它验证原始 JSON、完整 standalone 合同、声明 SHA 与跨 source/policy 绑定，但不保存或批准状态。`wave-left-v1` 的两份 proposal 已人工批准，A/B depth candidates 也已生成并通过该 preflight。复核台能按项目发现并自动加载 exact package、重算身份，显示 Correction/residual 时间轴、动态重点窗口和角色足点 observation；拖动时间轴或一键操作只会把 `state=candidate`、observations 完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot candidates 写成带 provenance、可撤销的辅助草稿。Depth、`rejected_*`、缺证、非有限值、超阈值与 `adjust` 仍逐项处理；重点窗口只是视觉导航，不改变安全判定。

当绑定或语义修正使 P3/P4/P5 身份改变时，已交付的 `prepare-motion-policy-review-draft` 可以在新 namespace 中原子准备一套可重放的非权威输入：它交叉验证精确 P3/P4/P5/P7/P8，重生 Kimodo evidence 与 standalone Foot candidates，并从当前 slot/bone role/setup order 导出 `pending_human_review` Depth proposal。它故意不写正式 Depth policy、Depth candidates、decision 或 P9 bundle，所以不会让旧决定静默跨链复用。新增的 draft inventory/API 和 Motion Policy 页面会自动发现与 current Resolved + Manifest 匹配的草案，隐藏路径/SHA，并显示角色、slot/role 与 setup front。一次明确确认调用独立 `depth-policy-draft-adoption-v1` 写边界；服务端双检查 current chain、投影正式 policy、生成 Depth candidates、原子发布三文件 exact package 并读回复验。历史草案保持只读。

草案晋级仍不是最终 P9 adoption。它不生成 candidate decision、reviewed policy、MotionInstance v2 或六文件 reviewed-motion bundle；页面必须继续处理完整 Foot/Depth candidate inventory，再执行最终 P9 human adoption。A r6 的 current draft ID、P3–P5 与 proposal/Foot SHA，以及 B r16 的对应地址，都集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)。

最终 human adoption 使用独立 `POST /api/motion-policy/review-packages/{package_id}/adoptions` 写边界和 `X-Autospine-Intent: motion-policy-adoption-v1`。服务端重新加载 exact package，只接受严格 review input；写入前用当前 Resolved + Manifest 双 SHA 的两次快照确认 package 仍为 current，随后才原子发布并 exact verify P9。A r6 已走完 P9/P10、CaptureFraming、P10.3c v2 与 current P10.5b/P10.5c；P10.4a/P10.4b v2 能力已交付。B r16 仍须走完 P9，再重建 P10.0/P10.1、重跑 P10.2/P10.2a 和 seam。若新 P10.2 是 `manual_visual_required`，可进入冻结 P10.3 v1；若唯一拒绝项是 `sampled_canvas_containment`，必须先完成 CaptureFraming decision，再进入 package-centric P10.3 v2。任何其他结构拒绝都继续 fail closed。

历史实物状态：真实运行的 `wave-left-v1` 已有 recorded 六输入、intake 报告、通过 exact reader 的 P7/P8 bundle、绑定到 A/B 历史版本的 P5 bundle、正式 depth policy、各自的 foot/depth candidates，以及分别 exact replay 通过的 P9 reviewed-motion bundle；collapsed sample 为零。两份历史 depth report 各有 120 个 sample、0 个 event；历史 A/B 的 P9 双 SHA 见 [pilot handoff](pilots/kimodo-wave-left-v1.md)。A revision 6 的 current P9/P10/P10.5c 另有独立精确地址，也记录在同一 handoff；它们不认证 checkpoint、动态 seam 或作品质量。B revision 16 若继续显示腿脚不可观测，才在该新链上选择上游修复或版本化 partial 合同。

工程加固待办（P2，不阻塞当前人工门禁）：把 Foot FK/最小二乘校验的相对容差改为由 9 位量化误差、浮点 ULP 和明确坐标上限共同定义，并加入高尺度回归；为出现事件的 Depth pair 增加 window sample/score/state 图形化轨道；补齐快捷键的 modifier、IME composition 和 `defaultPrevented` 防护；让 TRACE/CONNECT 等未实现 HTTP 方法统一返回带 `Allow` 的 405。生产模块继续保持 300 行上限，接近上限时必须先拆分。

若未来需要无人值守发布，必须另立 Motion Policy Decision v2：显式定义 `review.method=automatic`、可版本化安全规则、风险预算、审计 provenance、回滚和 release gate。不能让 v1 页面替操作者勾选 `human`，也不能把现有辅助草稿改名为零点击审批。

验收条件：同六份输入重复审计报告哈希相同，审计 preview 与随后 P7 发布身份一致；真实样本集至少包含慢动作、快速动作、交叉肢体、转身和脚接触案例；三 rig 无非有限数和明显滑脚；人工决定覆盖全部候选；P9 bundle reader 与官方 Runtime 截图回归通过；合成 fixture 与真实质量结论明确分开。

主要风险：单目 3D 深度/朝向歧义、角色比例差异、contact 标签误差、真实模型版本和许可不可复现。

## 实时面部与身体追踪映射

**建议优先级：P3。**

依赖：稳定的 canonical face/body anchors、blink/mouth/IK 控制通道、摄像头输入授权、校准和丢失追踪降级策略。

交付：tracking observation schema、provider adapter、角色校准、滤波/限幅、控制通道 map、录制 trace 的离线重放，以及实时预览 transport。实时流不能直接改写 reviewed bind pose 或不可变动作证据。

验收条件：录制 trace 可确定性重放；镜像、多人误检、短时遮挡和长时丢失有明确状态；延迟和抖动达到预先设定预算；输入停止后安全回到 neutral；不记录摄像头内容时也能运行最小模式。

主要风险：隐私、实时性能、provider 漂移、屏幕左右与角色左右混淆，以及跟踪噪声触发 mesh/constraint 越界。

## 生产化

**建议优先级：横向门禁；不要直接把当前 loopback 服务暴露到网络。**

依赖：明确部署场景、用户角色、数据保留规则和许可证策略。

交付建议分为三步：

1. **本地可靠性**：状态备份/恢复演练、schema migration、磁盘与内存预算、超时、任务取消、结构化日志、崩溃恢复。
2. **团队协作**：身份认证、项目权限、审计日志、对象存储、任务队列、跨进程 CAS 和内容地址垃圾回收策略。
3. **发布运营**：CI artifact、供应链/SBOM、依赖与模型许可登记、指标告警、灾难恢复、容量和并发压测。

验收条件：故障注入后不可变 history 不损坏；备份可恢复到精确 revision；路径遍历、Host/Origin、请求体和资源耗尽测试通过；并发提交保持 CAS 语义；敏感输入不进入普通日志；升级和回滚都有演练记录。

主要风险：把本地信任模型错误扩展到远程、多租户路径泄漏、外部模型/runtime 许可证、长任务资源耗尽和状态垃圾回收误删仍被引用的工件。

## 每阶段通用完成定义

每项能力只有同时满足以下条件，才能在功能入口中心从“规划中”改为“可用”：

- 合同、Schema、语义 validator、错误码和资源上限已固定；
- candidate/evidence、人工 decision、compiled output 分离；
- deterministic 或明确记录 nondeterministic provenance；
- 精确地址 reader 可重建，算法变化不会静默复用旧决定；
- 单元、性质、退化输入和 state-tree 零副作用测试通过；
- 涉及图像/动画时有固定 case 的数值、raster 和人工证据；
- 操作手册、功能参考、架构说明和功能入口中心同时更新；
- 未证明的 runtime、视觉、许可证与发布 claim 仍明确 blocked。
