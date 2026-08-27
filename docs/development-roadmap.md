# AutoSpine Workbench 后续开发路线

本文是 Explanation 与交付计划，面向维护者和需要评估可行性的项目负责人。它从 **P0 Resolved Project v1 合同与 P10.6a 已完成** 的事实出发，说明尚未实现的能力应按什么依赖关系推进。当前后续开发入口是 P10.6b。这里的阶段名、优先级和验收条件是建议，不代表对应功能已经存在，也不构成发布日期承诺。

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
| P0 | P10.6b MotionInstance v3 / timeline compiler | P10.6a 已为它建立了明确准入，是当前最短关键路径 |
| P0 | P10.7 P6 adapter 接入与官方 Runtime 回归 | 只有穿过目标 runtime，body-sway 才形成可验证交付链 |
| P1 | Revision 历史浏览/恢复 UI | 历史已不可变保存，但操作者尚不能便捷查看或安全恢复 |
| P1 | 主工作台 Spine 导出编排入口 | 离线 P6 已完成，主项目能力仍明确为 `export_spine=false` |
| P1 | Attachment switch 基础合同 | 眨眼和口型的共同前置能力 |
| P1 | 自动眨眼、口型候选与人工复核 | 价值高、动作域相对局部，适合在离散切换合同上先落地 |
| P1 | 真实 Kimodo/P9 质量门禁 | 当前仅有合成兼容性证据，真实动作质量风险必须单独关闭 |
| P2 | 头发弹簧、自由形变、多骨权重、runtime IK | 需要新的连续变形、约束和视觉安全合同 |
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
P10.6b MotionInstance v3
        ↓
P10.7 Spine 4.2 adapter + runtime/raster regression
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

## P10.6b：MotionInstance v3 与 timeline compiler

**建议优先级：P0，立即开始。**

依赖：

- 认证的 `BodySwayMotionConsumerAdmission v1`；
- 精确 P9 MotionInstance v2/reviewed bundle；
- P10.3c visual head 与 P10.5b seam head 的 current-state reader；
- setup-local rotation、root translation、marker 和 stepped draw-order 现有语义。

交付：

- `MotionInstance v3` JSON Schema、值对象和语义 validator；
- pure timeline compiler，将 unit-gain body-sway rotation 与 MIv2 基础 channel 明确合成；
- compile run、不可变 bundle、严格 reader 和独立 verify 命令；
- source closure 内嵌 admission/P9 精确身份，消费前后重新检查两个 current head；
- 对 channel 冲突、tick 重复、loop closure、非有限数和不支持 interpolation 的 fail-closed 规则。

进入下一阶段的验收条件：

- 同一 canonical 输入产生相同 MotionInstance/bundle SHA；
- 完整 reader 能从精确地址逐字节重编，不扫描 `latest`；
- visual 或 seam head 在消费期间漂移时不发布任何 bundle；
- MIv2 root、marker、draw-order channel 逐键保留，body-sway rotation 只影响允许的四骨；
- loop、有限数、setup-local 语义和三套 rig 回归通过；
- release gate 仍明确 blocked，不能在本阶段声称 Spine Runtime 或 raster 通过。

主要风险：current-head TOCTOU、MIv2 与 body-sway channel 合成顺序、tick/插值语义漂移，以及为了赶进度直接复用 P10.6a stdout 而跳过重新观察。

## P10.7：接入 P6 Spine 4.2 与 Runtime 回归

**建议优先级：P0，紧接 P10.6b。**

依赖：MotionInstance v3 严格 bundle、现有 P6 Spine 4.2 profile、操作者提供且已授权的 `@esotericsoftware/spine-player@4.2.119`。

交付：

- P6 adapter 的显式 v3 capability profile；
- MIv3 → Spine 4.2 timeline 编译与五文件内容寻址 bundle；
- 固定 canvas、DPR、tick/case 的官方 Runtime capture plan；
- attachment 完整边界的 raster 指标与人工截图复核合同；
- setup、现有 idle/wave 和 body-sway 的兼容回归。

验收条件：

- 两份真实 See-through 样本和至少一个结构差异 fixture 均可由官方 Runtime 加载；
- adapter 对未知 timeline/attachment/constraint fail loud，不静默降级；
- setup 和既有 P6 golden 不发生未批准变化；
- body-sway 固定帧、极值姿势、loop 接缝和 attachment 边界均有可回放证据；
- capture 记录 runtime 精确版本和授权确认，test stub 不得进入正式证据链。

主要风险：Spine interpolation 与版本中立语义不完全同构、不同 GPU/浏览器 raster 差异、官方 Runtime 获取和许可前置条件。

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

**建议优先级：P1，可与 attachment switch 并行。**

依赖：可合法使用的真实 Kimodo checkpoint 输出、camera/calibration evidence、现有 P7–P9 精确链和人工 policy review。

交付：不可变真实样本集、source provenance、P8 投影校准、P9 foot/depth 决定、三 rig 重定向、Spine Runtime capture 和人工质量报告。heading/scale 只有在独立 reviewed 合同完成后才能进入 runtime。

验收条件：至少包含慢动作、快速动作、交叉肢体、转身和脚接触案例；三 rig 无非有限数和明显滑脚；人工决定覆盖全部候选；P9 bundle reader 与官方 Runtime 截图回归通过；合成 fixture 与真实质量结论明确分开。

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
