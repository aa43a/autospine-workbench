# AutoSpine Workbench 后续开发路线

本文是 Explanation 与交付计划，面向维护者和需要评估可行性的项目负责人。已交付 P0、P10.2/P10.2a、P10.2 动态视口与 region 换绑候选、P10.5b/P10.5c、P10.6b、P10.7a、P10.7b 与独立 P10.7c setup regression。真实 `wave-left-v1` 的 A/B 历史 P9 精确链已关闭。样本 A 已保存 P10.1 r2（decision `70d62da6…`）为 `adjust/pending_probe`；旧 P10.2 report `4406289e…` 仍以固定素材坐标记录 `structural_rejected`。`1024×1024` 现在明确只是 See-through/setup 坐标，不是 Rig 或 Runtime 相机硬边界；P10.2 v3 另给出可缩放、平移和完整包络适配的零权威动态视口候选。唯一责任附件 `layer-007-handwear-l` 的动作证据推荐 `forearm.left → upper-arm.left`，但必须由操作者在绑定工作台明确确认并保存新 revision；其后 Manifest/P2–P10 需按新身份重建。P10.3 尚未消费动态视口，所以该候选本身不构成 P10.3 准入。A 的 P10.5b r2/P10.5c 仍只关闭静态锚点。B 旧链的 P10 数字不能外推到绑定 revision 16；B 必须完成新 P9 adoption，再重建 P10.0/P10.1 并重跑 P10.2/P10.2a。

样本 B 在上述历史链之后又保存了绑定 revision 16。新 Manifest/P2–P5 已 strict verify，
`wave-left-v1-r16-draft` 也已生成，但仍停在 pending Depth proposal：旧 P9/P10 决定不会跨链
继承。当前最先要关闭的是新 P9 人工采用；`ankle.left=unobservable` 还要求左腿 foot-lock 保持
阻塞。下文涉及 B 的旧 P9/P10.1/P10.2 数字时，均应理解为历史固定链证据，而不是 r16 新链结论。

## 规划原则

后续工作继续遵守现有边界：

1. 先定义版本中立合同、语义 validator 和失败语义，再实现目标版本 adapter。
2. 自动候选与人工决定分离；模型或算法变化不得静默复用旧决定。
3. 所有消费方按精确内容地址读取上游，并在需要 current authority 时重新检查 head。
4. 数值、结构、raster、人工视觉、官方 Runtime 和发布许可是不同证据层，不能互相替代。
5. 新生产文件默认不超过 300 行，400 行是硬上限；优先拆成 pure core、I/O、validation、CLI/UI adapter。
6. 外部模型、Spine Runtime 和素材许可由操作者提供并确认；仓库不隐式下载或再分发。

## 建议优先级

| 优先级 | 能力 | 原因 |
| --- | --- | --- |
| P0 | B revision 16 的新 P9 人工采用 | 新 P3/P4/P5 已生成独立 draft；须人工批准正式 Depth policy、生成 Depth candidates 并完成最终 adoption，旧 P9 不得复用；左腿 foot-lock 保持 blocked |
| P0 | A 的动作证据换绑确认与下游重建 | P10.2 已区分固定素材坐标与动态视口，并为 `layer-007-handwear-l` 推荐 `forearm.left → upper-arm.left`；须明确确认并保存新 override revision，再重建 Manifest/P2–P10；动态视口候选尚不能进入 P10.3 |
| P0 | B revision 16 的 P10.0/P10.1 重建与 P10.2 重跑 | 历史链 `8/8 = 334/334`、`0/8 = 333/334` 不适用于 r16；新 P9 adoption 后须重编 candidate、显式提交新 P10.1，再以新 P10.2/P10.2a 判断参数或上游修复 |
| P0 | A/B 的 P10.3→P10.4a→P10.4b1→P10.4b2 动作域 | 仅在各自新链 P10.2 得到 `manual_visual_required` 后准备 Runtime/视觉复核；`viewport_adjustment_available` 尚不被 P10.3 消费 |
| P0 | A 的 P10.5d 动态接缝验证 | 只有 P10.4b2 与既有 P10.5c 双 SHA 都闭合后，才在精确动作域上运行动态接缝代理 |
| P0 | B revision 16 的 seam 能力重验 | 历史链 P9/seam 可精确复验，但四条下肢不可观测不能外推到 r16；须按新 Manifest/P3/candidate 重验后，才能选择上游修复或版本化 partial 合同 |
| P0 | P10.7c setup golden 独立回归 | 零写入入口已交付；真实执行仍依赖 exact P10.7a/capture 与批准 P6 基线，readiness v1 保持冻结且第八项仍 missing |
| P0 | P10.7b 两份真实样本验收 | Runtime/capture/metrics/review 基础设施已存在，但真实链尚未到达 P10.7a；仍需先关闭各自 seam 门禁，再做官方 Runtime 和人工决定 |
| P1 | Revision 历史浏览/恢复 UI | 历史已不可变保存，但操作者尚不能便捷查看或安全恢复 |
| P1 | P10.3 package-centric 自动采集编排 | 当前仍需人工闭合 exact 地址；在出现合法 `manual_visual_required` head 后，可由服务端从 `package_id` 生成临时预览、在显式许可确认后异步捕获并自动交接 exact capture 地址 |
| P1 | 主工作台 Spine 导出编排入口 | 离线 P6 已完成，主项目能力仍明确为 `export_spine=false` |
| P1 | Attachment switch 基础合同 | 眨眼和口型的共同前置能力 |
| P1 | 自动眨眼、口型候选与人工复核 | 价值高、动作域相对局部，适合在离散切换合同上先落地 |
| P1 | 扩展真实 Kimodo 动作质量样本集 | 单一 `wave-left-v1` 关闭了结构链，但尚未覆盖快慢动作、交叉肢体、转身、接触和官方 Runtime 视觉质量 |
| P2 | P3/P5 v2 分段四肢网格、头发弹簧、自由形变、多骨权重、runtime IK | 手臂与分段腿不能静默扩写 leg-only v1；需要新的连续变形、约束和视觉安全合同 |
| P2 | See-through/pose 离线 runner | 可提高自动化，但依赖模型、显存、许可证和确定性封存策略 |
| P2 | Spine Editor 工程与更多版本 adapter | 必须按版本、格式和许可证隔离，不能扩展现有 4.2 声明来冒充兼容 |
| P3 | 实时面部与身体追踪 | 依赖稳定 rig 控制通道、校准和降级策略 |
| 横向门禁 | 生产化 | 安全、备份、迁移、资源预算和可观测性应随各阶段逐步引入 |

关键路径建议：

```text
Resolved Project v1 Schema + semantic validator（已完成）
        │
P10.6a（已完成）
        ↓
P10.6b MotionInstance v3（已完成）
        ↓
P10.7a Spine 4.2 adapter + immutable bundle（已完成）
        ↓
P10.7b capture/metrics/review 基础设施（已完成）
        ↓
P10.7b-readiness 显式 Manifest 审计（已完成入口）
        ↓
P10.7c 独立 setup golden 比较机制（已完成入口；真实执行在 capture 后）
        ↓
真实 `wave-left-v1` 六输入审计 + P7/P8（已完成）
        ↓
A/B P5 重定向 + P9 package/preflight/安全 Foot 辅助采用（已完成）
        ↓
P9 异常复核 + 一次 human adoption → 本地发布/exact verify（A/B 已完成）
        ↓
绑定 revision 改变 → 新 Manifest/P2–P5 → 独立 P9 draft → 再次 human adoption（B r16 当前在此）
        ↓
P10.5b 自动看图复核 → P10.5c package publication（A 已真实闭合静态凭据）
        ↓
按新 P9 地址重建 P10.0 候选 → P10.1 显式人工确认（B r16 尚未重建）
        ↓
P10.2 current-head 自动结构探针 + P10.2a `0/8…8/8` 诊断 + 动态视口/region 换绑候选（机制已完成；B r16 尚未重跑）
        ↓
视口自由查看；绑定候选经明确确认新 revision，或非零幅度 draft 经显式 P10.1 revision，再重建/重跑 P10.2
        ↓
P10.3 Runtime/视觉复核（package-centric 自动采集编排尚未实现）→ P10.4a current-head 准入
        ↓
P10.4b1 离散幅度包络 → P10.4b2 连续证明
        ↓
P10.5d 动态接缝验证（组合 P10.4b2 动作域与既有 P10.5c）
        ↓
B 上游修复或 partial 合同（现有完整合同 fail closed）
        ↓
两份真实 See-through 样本官方 Runtime + 人工验收（需要外部授权环境）
        ↓
attachment switch ──→ blink / mouth
        │
        ├────────────→ deform / runtime IK
        └────────────→ live tracking control channels

真实 Kimodo/P9 ──────┘（可与 attachment switch 并行）
See-through/pose runner（独立输入质量轨，可并行）
Revision 历史 UI（独立 authoring 可用性轨）
主工作台 Spine 导出编排（P6 已完成，UI 仍待接入）
```

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

这里的“已完成”包括 A 的真实静态凭据：P10.5b revision 2 已由操作者以 `6/6 accept`、`24` 个
anchor pairs 确认并明确取代 revision 1；对应 P10.5c bundle 已发布并通过 exact replay。它只
固定六条 setup locator，不能直接进入 P10.5d；当前要先关闭
P10.0/P10.1、P10.2、P10.3、P10.4a、P10.4b1 与 P10.4b2 动作域。B 历史链的四条下肢关系
不可观测，自动流程只会保存 blocked 结论而不会发布完整 P10.5c；revision 16 必须按新
Manifest/P3/candidate 重新判断，不能继承该 blocker 或把它自动改成通过。

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
candidate-bound P10.1 revision。当前 A r2 是 `adjust/pending_probe`；旧 v1 report 在固定素材坐标中
拒绝 canvas containment，v3 另行提供动态视口和换绑候选，但尚不构成 P10.3 准入。B 的 r2
`adjust/pending_probe` 与其 sampled canvas containment 拒绝都属于 revision 16 之前的历史链；
r16 完成新 P9 后必须生成新的 P10.0 candidate 和 P10.1 revision。新的 `adjust` 成功也只进入
`pending_probe`，下一项仍是七项 sampled 结构诊断。

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
当前骨和同链一跳父/子骨，始终是 `authority: none`。真实 A 的 `layer-007-handwear-l`
当前 rigid 绑定为 `forearm.left`，证据推荐 `upper-arm.left`：region 包络中的骨段覆盖由 1
增至 2，root-compensated motion extent 改善约 `31.81%`，最大 viewport overflow 诊断约从
`157.26 px` 降至 `25.54 px`。这不证明视觉或接缝正确；绑定工作台只能在独立建议卡预览目标骨，操作者仍须
明确确认并保存新 override revision。保存会改变 Resolved/Manifest/RigIR 身份，因此旧
P3/P5/P9/P10 派生产物只保留为历史证据，必须按新链重建。

历史 B exact P9/P10 链在 `8/8` 有 `334/334` 个 canvas 失败 tick，在 `0/8` 有 `333/334` 个，
关联 `layer-006-objects`、`layer-000-back-hair` 与 `layer-008-hand-r`；因此只能断言该旧链不存在
纯参数候选。revision 16 改变上游身份后，必须先完成新 P9，再重建 P10.0/P10.1 并重跑 P10.2，
不能假设新链仍失败或已经修复。当前 A 的旧 v1 report 仍为 `structural_rejected`，P10.2 v3
另有动态视口和换绑候选；B r16 尚无新 P10.2 报告。P10.3 目前不消费动态视口，因此真实双
样本都没有合法 P10.3 head。

## 下一阶段规划：P10.3 package-centric 自动采集

这项编排**尚未实现**，也尚未定义如何消费 `DynamicViewportFit v1`。目标是在未来出现
`manual_visual_required` current head 后，让普通操作者
只选择项目/package，而不是手填七个 SHA 和四段 capture 地址。服务端应从 `package_id` 重新读取
current P10.1/P10.2，闭合七个上游 SHA，生成 temporary preview，启动可恢复的异步 capture，
并在成功后把返回的 project/preview/bundle/artifact exact 地址自动交给视觉复核页。

自动化不能取消两类人工授权：启动真实 capture 前必须显式确认官方 Runtime 的使用许可与本次
运行；逐 case 的视觉结论及其最终 CAS 提交仍由操作者确认。项目推荐、SHA 闭合、临时预览、任务
状态、capture 地址发现和页面跳转可以自动完成。任何 head 漂移、结构拒绝、Runtime 缺失、许可未
确认或 capture 不完整都必须 fail closed，且不得生成 P10.3 准入。

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

## 已完成：P10.6b MotionInstance v3 与 timeline compiler

P10.6b 已交付，不再是规划项。操作入口见
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
字节可重放。Spine adapter bundle 已由 P10.7a 关闭；P10.7b 只增加 sampled official-runtime
raster evidence 与人工 decision，不会授予连续时间或 release authority。后续维护必须继续
防止 current-head TOCTOU、MIv2/channel 合成和插值语义漂移。

## 已完成：P10.7a Spine 4.2 v3 Adapter 与五文件 Bundle

P10.7a 已交付，不再是规划项。操作入口见
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

## P10.7b：Raster 基础设施已交付，真实双样本验收待完成

**当前优先级：P0。基础设施可用；真实资产验收仍需要外部授权环境。**

依赖：P10.7a 五文件 bundle，以及操作者提供并明确确认有权使用的
`@esotericsoftware/spine-player@4.2.119`。仓库不会从 CDN 回退、捆绑 runtime，或把包内
`LICENSE` 文件存在当作授权确认。

已交付：

- 固定 runtime 版本、canvas、DPR、case/tick、setup attachment inventory 和资源上限的 capture plan；
- runtime JS/CSS、`package.json`、`LICENSE`、浏览器可执行文件与 P10.7a 来源的精确身份封存；
- opaque/transparent composite 与每个 setup attachment isolate 的正式浏览器捕获通路；
- alpha union、missing/extra/xor、边界、裁切和 isolate 非空的 sampled raster 指标；
- manifest/metrics/PNG 的不可变 store、精确 reader 与 P10.7a source replay；
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

**当前优先级：P0。审计入口已交付；报告显示真实链仍被更早前置阻塞。**

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
| `seethrough_output` | P9 exact reader 已通过；P10.1 r2 已保存；旧 P10.2 report `4406289e…` 固定素材坐标拒绝，v3 已给动态视口与换绑候选 | P10.5b revision 2 与 P10.5c exact bundle 已存在 | 明确确认 `layer-007-handwear-l: forearm.left → upper-arm.left` 并保存新 revision，再重建下游；P10.3 尚不消费动态视口 |
| `seethrough_output_5` | 历史 P9 exact reader 已通过；r16 新 P9 尚待 adoption，冻结请求也未声明 | 历史 P3 candidate 的四条腿/脚不可观测结论不能替代 r16 新链复验 | 官方 Runtime 包与 P6 baseline 可用，但 r16 须重建 P10.0/P10.1、重跑 P10.2 后再判断更早 blocker |

A 的 seam checkpoint 必须表述为 `reviewed_seam_anchor_set_address_not_declared`。这只说明冻结请求
没有提供 P10.5c 双 SHA，不说明 current review head 或真实工件为空。A 的 current P10.5b revision 2 和
P10.5c exact bundle 已经存在，应把 [pilot handoff](pilots/kimodo-wave-left-v1.md) 中的双 SHA 写入
新 canonical 请求；冻结请求中的 P9 `null` 同样只表示该请求未声明当前已存在的 exact 地址。

项目 B 不得把 `unobservable` 自动改成 accept。进入完整 P10.5c 前必须修复上游腿/脚语义或
See-through 分层，并让新的 Manifest/P3/candidate 内容地址失效旧决定；若产品确实接受缺腿脚
接缝，只能另立版本化 partial seam 合同、能力边界和独立验收，不能扩写现有六关系合同。

最短后续顺序：

1. 从 [pilot handoff](pilots/kimodo-wave-left-v1.md) 读取 A 与 B 历史链已复验 P9 双 SHA；这些地址只供历史复验。B revision 16 必须先完成新 P9 adoption，再把新地址写入 canonical readiness 请求；不得把历史 B 地址冒充当前链，也不得手工格式化冻结 baseline。
2. 对 A 在 P10.2 自由缩放/平移查看完整动作包络；动作证据已推荐 `layer-007-handwear-l: forearm.left → upper-arm.left`。回绑定工作台明确确认并保存新 override revision，然后重建受影响的 Manifest/P2–P10 地址；现有 r2/report 保留为历史证据。
3. A 只有重建后的 P10.2 得到 `manual_visual_required` 才能进入 P10.3 及后续动作域；`viewport_adjustment_available` 不能替代该条件。B 在新 P9 adoption 后按新地址重建 P10.0/P10.1、重跑 P10.2/P10.2a；不得搬用旧 P10/seam 结论。
4. 在精确 P9/P10.5d 地址上依次完成 P10.6–P10.7a；每次只把实际生成的双 SHA 回填请求。
5. 使用现有且已获授权的官方 Runtime 执行 P10.7b capture、精确复验和逐 case/attachment 人工决定。
6. 使用已交付的 `compare-body-sway-spine42-v3-setup-golden` 独立比较 setup case 与既有 P6 approved golden。readiness v1 已冻结且不会消费这份报告；即使前七项通过，它的第八项仍保持 missing，只会给出 `ready_for_p6_setup_comparison`。

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
`wave-left-v1` 历史链已到达 P7/P8、两个目标 P5 与各自 exact replay 通过的 P9；A 已闭合真实
P10.5b/P10.5c 静态凭据，但 P10.1–P10.5d 动作域尚未关闭。B revision 16 尚待新 P9、P10.0/P10.1、
P10.2 与新 seam 复验，历史四条腿/脚不可观测不能作为新链结论；真实 P10.7a/capture 也尚未交付。只有这些前置关闭后，
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

**当前状态：`wave-left-v1` 的历史链已完成 intake、P7/P8、两个目标 P5、A/B human adoption、P9 发布与 exact verify；A 的 P10.5b r2/P10.5c exact bundle 已闭合。A 的 P10.1 r2 也已保存；旧 P10.2 report `4406289e…` 保留固定素材坐标的拒绝，v3 已另行提供动态视口候选，并为 `layer-007-handwear-l` 推荐 `forearm.left → upper-arm.left`。下一步是明确确认换绑、保存新 revision 并重建下游。B r16 尚待新 P9 adoption 与后续 P10 重建。P10.3 尚未消费动态视口，两者都尚未进入 P10.3。**

上述状态描述的是已采用的历史精确链。样本 B revision 16 已产生新的 Manifest/P2–P5 地址，并
准备 `wave-left-v1-r16-draft`；它尚无正式 Depth policy、Depth candidates 或新 P9 adoption。
新链的 `layer-008-hand-r` 保留 `body.arm.upper → upper-arm.left`，但在 leg-only P3 v1 中为
rigid region，P3/P5 mesh 检查诚实返回 `reviewed-noop`。`ankle.left=unobservable` 也没有使
现有启发式骨端成为真实足点；左腿 root correction/foot-lock 必须保持人工阻塞。完成新 P9 后，
B 必须先重建 P10.0/P10.1、重跑 P10.2/P10.2a；canvas、seam 与 Runtime 结论都要按新地址重新
建立，不能搬用旧 current head 或历史 334/333 结果。

依赖：可合法使用的真实 Kimodo checkpoint 输出、checkpoint manifest、generation request、recorded sidecar、显式 map/camera、现有 P7–P9 精确链和人工 policy review。

已交付的 M1.0 `audit-kimodo-pilot-intake` 会安全读取六份精确文件，要求两份 provenance 原件的逐字节 SHA 与 recorded sidecar 闭合，在内存中重跑 P7 结构编译，并验证 camera/map 一致性。输出是 path-free、自哈希、零写入报告；它明确把 checkpoint authenticity、动作质量、P8 projection、P9 review 与 release authority 保持为 false。操作见[审计真实 Kimodo Pilot 输入](how-to-audit-real-kimodo-pilot-intake.md)。

已交付的 P9 安全收口把 policy identity 和 candidate inventory 从浏览器推断改为 loopback-only、zero-write Python preflight；它验证原始 JSON、完整 standalone 合同、声明 SHA 与跨 source/policy 绑定，但不保存或批准状态。`wave-left-v1` 的两份 proposal 已人工批准，A/B depth candidates 也已生成并通过该 preflight。复核台能按项目发现并自动加载 exact package、重算身份，显示 Correction/residual 时间轴、动态重点窗口和角色足点 observation；拖动时间轴或一键操作只会把 `state=candidate`、observations 完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot candidates 写成带 provenance、可撤销的辅助草稿。Depth、`rejected_*`、缺证、非有限值、超阈值与 `adjust` 仍逐项处理；重点窗口只是视觉导航，不改变安全判定。

当绑定或语义修正使 P3/P4/P5 身份改变时，已交付的 `prepare-motion-policy-review-draft` 可以在新 namespace 中原子准备一套可重放的非权威输入：它交叉验证精确 P3/P4/P5/P7/P8，重生 Kimodo evidence 与 standalone Foot candidates，并从当前 slot/bone role/setup order 导出 `pending_human_review` Depth proposal。它故意不写正式 Depth policy、Depth candidates、decision 或 P9 bundle，所以不会让旧决定静默跨链复用，也不会被默认 package 发现当成可采纳项。下一步仍是操作者显式批准正式 policy，再生成 Depth candidates 并进入一次最终 P9 human adoption。该命令是精确链维护入口，尚不是普通操作者的零 SHA Web 编排。

最终 human adoption 使用独立 `POST /api/motion-policy/review-packages/{package_id}/adoptions` 写边界和 `X-Autospine-Intent: motion-policy-adoption-v1`。服务端重新加载 exact package，只接受严格 review input；写入前用当前 Resolved + Manifest 双 SHA 的两次快照确认 package 仍为 current，随后才原子发布并 exact verify P9。A 已完成 P10.5b/P10.5c 静态闭环并保存 P10.1 r2；其 P10.2 动态视口只解决自由查看与适配候选，`layer-007-handwear-l` 的换绑仍须明确确认并保存新 revision，然后重建下游。B revision 16 则须先完成新 P9 adoption，再重建 P10.0/P10.1 并重跑 P10.2/P10.2a。两者都须取得 `manual_visual_required` 才能进入 P10.3。

历史实物状态：真实运行的 `wave-left-v1` 已有 recorded 六输入、intake 报告、通过 exact reader 的 P7/P8 bundle、绑定到 A/B 历史版本的 P5 bundle、正式 depth policy、各自的 foot/depth candidates，以及分别 exact replay 通过的 P9 reviewed-motion bundle；collapsed sample 为零。两份 depth report 各有 120 个 sample、0 个 event；历史 A/B 的 P9 双 SHA 见 [pilot handoff](pilots/kimodo-wave-left-v1.md)。这不认证 checkpoint 或批准作品质量，也不授权 B revision 16。新链的 P9、P10 和 seam 都须按新地址重新建立；若新证据仍显示腿脚不可观测，才在该新链上选择上游修复或版本化 partial 合同。

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
