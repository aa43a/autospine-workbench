# AutoSpine Workbench

[翼片与四肢标准骨架合并](docs/how-to-wing-limb-preview.md)：琪露诺32附件完成官方Runtime 121帧检查，
旧四肢动作保持一致；翼片局部动作重挂标准骨架，袖口、裙摆及残余仍待复核。

[主翼与挂坠的完整角色上下文](docs/how-to-wing-character-preview.md)：琪露诺18源层、26附件通过官方Runtime 121帧检查；
16层仅作刚性身体参照，独立四肢动作尚未合入，没有新增绑定批准。

[手臂Mesh已接入组合包](docs/how-to-integrated-limbs.md)：11附件完成官方Runtime 121帧验证，原有附件逐帧坐标保持不变。
14个包缺项已列出并链接全量复核页；现有选择保留，未新增批准。

[刚性绑定与四肢候选同包](docs/how-to-mixed-character.md)：Alice 5个已选刚性层 + 4个腿鞋分区完成官方Runtime 121帧验证。
仍缺16层及570残余像素，完整动画继续阻塞；未新增选择或采用权。

[整角色上下文预览](docs/how-to-character-context.md)已加入：Alice原23层中，4个腿鞋分区播放候选，21层静态显示。
570个残余像素仍未绑定；该诊断页不是完整角色动画或官方Runtime验收。

[右侧局部空间复核](docs/how-to-seam-roi-context.md)：183个ROI已定位，4邻接的6个局部封闭疑点在8邻接下均触达裁剪边缘。
未确认封闭孔洞，也未排除开放细缝；候选和权重不变，继续完整角色视觉回归。

[Alice右侧独立边界采样](docs/how-to-seam-boundary-probes.md)完成：183个目标、732次Runtime捕获。
58个目标合成alpha下降，未新增低于8的中心点；统一入口已显示独立证据，候选仍待复核。

[保守候选统一预览](docs/how-to-seam-candidate-hub.md)：同页切换Alice／琪露诺、播放并下载已校验候选包。
两角色官方Runtime共242帧回归通过；Alice右侧局部目标仍未评估，原有空白保留，候选未采用。

[琪露诺双侧回退验证](docs/how-to-crino-stable-fallback.md)完成：六区域几何通过，边界增距仍<2px，622组Runtime原／回退局部图完全一致。
保守组合收敛为Alice左回退、右保留增量，琪露诺双侧回退；候选未自动采用，原有空白与未评估项仍保留。

[逐关系准入报告](docs/how-to-seam-admission.md)已整合几何、边界及Runtime合成证据。琪露诺全部311个已记录点均有合成alpha下降，左右增量继续复核。
Alice左回退仅在当前采样范围内无新增退化，右侧无目标样本仍为未评估；没有自动采用权。

[Alice 整段回退候选](docs/how-to-seam-stable-fallback.md)恢复左侧原轨道、保留右侧增量：两处边界增距仍<2px，七点Runtime目标RGBA恢复到原动画。
相对原动画无新增空白帧；原有空白仍保留，完整接缝未验收，候选尚无采用权。

[官方 Runtime 局部合成](docs/how-to-seam-local-runtime.md)已捕获 Alice 七点的 224 组 framebuffer 对照：增量后七点 alpha 均下降，四点低于 8。
共享／独立纹理目标 RGBA 一致；候选未采用，下一步评估逐关系稳定准入与回退。

[直接 UV alpha 核查](docs/how-to-seam-direct-alpha.md)在全部 318 个像素单元内检测到低合成 alpha 子采样点。
Alice 七点均有双 Mesh 覆盖，且三个中心叠加后不再低于 alpha8；原逐附件阈值不能直接作为合成门禁。下一步核对 Runtime 局部合成，候选未采用。

[亚像素 alpha 等值轮廓](docs/how-to-seam-gap-isoline.md)使 Alice 七点均呈相向边界；4／8 倍细分分类一致，最大距离变化约 0.01662px。
这是 CPU 样本场近似，候选仍未采用；下一步校准直接 alpha／Runtime 局部可见性。

[动态 alpha 边界证据](docs/how-to-seam-gap-boundary.md)已加入逐像素边缘距离、法向和 ROI 连通性。
Alice 左侧 1 个样本为相向边缘、6 个存在并列歧义；第 37 帧局部封闭，仍未确认裂缝或采用候选。下一步验证亚像素等值轮廓。

[附件运动补偿轨迹](docs/how-to-seam-gap-transport.md)将 Alice 左侧 6 条关联候选收敛为 4 条，第 36–38 帧连成三帧轨迹。
琪露诺左／右最长观测为 20／13 帧；这不证明真实裂缝，下一步补充 alpha 边界拓扑证据，候选未采用。

[新增空白跨帧轨迹](docs/how-to-seam-gap-tracks.md)已加入连通区域、世界坐标、保守关联和帧滑块复核页。
Alice 左侧 7 个样本形成 6 条候选轨迹；部分连续帧位移超过 3px，不能据此认定短暂噪声。下一步验证运动补偿关联，候选仍未采用。

[固定 deform 有界增量](docs/how-to-seam-increment.md)使四处原对应增距均低于 2 px，12 个区域无翻转；Alice 右侧空白峰值 3 → 1，且无新增空白帧。
新增[空白局部支撑分类](docs/how-to-seam-gap-context.md)：Alice 左侧 7 个跨帧新增像素样本均有相对附件支撑；琪露诺 311 个中 243 个仅有单附件支撑。标签尚不证明裂缝或外轮廓变化，候选未采用；下一步定位并校准这些证据。

[接缝平移约束实验](docs/how-to-seam-translation.md)已加入 alpha 支持的对应候选与前后对照。
四处腿鞋仍超限；整只鞋平移未解决非一致的边界运动，结果未采用，下一步验证真实接触轮廓与局部过渡。

[连续 corrective Bake](docs/how-to-continuous-corrective.md)已生成 30 FPS 受限动作，12 个区域的 60 FPS 几何采样通过；
Alice／琪露诺四处腿鞋邻近关系增距 7.84–13.75 px，接缝保持阻塞。完整角色尚未验收。

[组合 corrective 诊断](docs/how-to-combined-corrective.md)已接入主关节与远端的 stepped deform：
5/8 个三骨区域通过全部离散姿态几何检查，三处仍阻塞；官方 Runtime 273 帧通过。连续动作和动态接缝尚待验证。

[Spine分区诊断播放](docs/how-to-ownership-spine43.md)已接通4.3.26区域UV与Editor图片导出；
官方4.3 Runtime验证三个角色363个固定时刻通过。仅证明编码／采样一致，原变形与完整角色门禁继续保留。

[分区采样隔离](docs/how-to-ownership-atlas.md)已把ownership编译为6张共享纹理页，左右区和残余各自隔离。
像素重建与固定UV线性采样检查通过；Spine Adapter接入和原变形QA仍待完成。

[共享源纹理分区v2](docs/how-to-shared-partitions.md)已连接6个源图层、12个运动区的ownership、骨链与权重。
残余原样保留，RGBA／UV检查通过；共享纹理边界采样尚未编译到Spine，目标导出仍阻塞。

[横向宽度权重试验](docs/how-to-distal-width.md)：系数4下五处通过9个远端corrective探针，
三处仍阻塞，全链与组合动作尚未通过，未自动采用。

[踝／腕网格加密实验](docs/how-to-distal-grid.md)完成三个角色对照：完整alpha覆盖，混合顶点增至53–76个，
但八处仍阻塞且最差面积比退化。未采用；下一步验证图层横向宽度与权重过渡的关系。

[踝／腕 corrective 试算](docs/how-to-distal-corrective.md)已接通有界投影、逐骨局部偏移与角度线框对照。
八个区域仍阻塞；旧网格只有2–6个可移动顶点，加密对照结果见上方。

[分区全alpha覆盖修复](docs/how-to-partition-coverage.md)已接通，保留可见主组件检查并补齐透明边缘所在单元。
踝/腕前移权重试验单独保存且未采用；变形QA和R3验收仍继续推进。

[分区多区域权重实验](docs/how-to-partition-mesh.md)的v1基线生成12个左右独立区域网格，setup数值重建通过；
该旧基线12个区域均阻塞，后续覆盖修复见上方说明，尚未通过R3验收。

[残余归属复核](docs/how-to-residual-review.md)提供4px规则试算、alpha贡献对照和可撤销草稿；
六层试算补全673个低alpha像素，默认待复核，旧分区与绑定不变。

[无损组件分区](docs/how-to-layer-partitions.md)已接通：六个真实候选图层输出左右/残余 PNG 与 ownership 掩码，
RGBA 重建通过；残余与绑定仍待复核，尚未生成分区权重。

[剩余图层结构候选](docs/how-to-layer-structure.md)已接通：按 alpha 连通域与骨架位置提出双侧分区，
裙装提供刚性 setup 候选；模糊侧别和未知物件保持阻塞，尚未生成分区 PNG 或权重。

[头部部件绑定补全](docs/how-to-binding-completion.md)新增31项可复核候选，保留既有19项绑定；
三个角色提供集中复核页，新增建议仍待确认，裙装和双侧肢体等结构问题继续保留。

[已确认图层组合预览](docs/how-to-character-preview.md)已接通：刚性层与手臂动画同场景播放，
附肩部接触候选与范围清单；未确认图层、Draw Order 和正式接缝仍待处理。

[Spine 4.3.26 手臂诊断包](docs/how-to-elbow-spine43.md)已接通 JSON/Atlas/原 PNG 与 deform 时间轴编码。
仅输出已通过 Bake 的 Mesh，完整角色接缝和官方 Runtime 仍未验证。

[Corrective 烘焙与纹理预览](docs/how-to-elbow-bake.md)已接通：30FPS关键帧、120Hz插值QA，
支持播放/暂停与拖帧；尚未接官方 Spine Runtime 或完整角色接缝验证。

[肘部局部约束修正](docs/how-to-elbow-constraints.md)已接通：固定刚性端部、限制修正量，
独立检查面积、边长与翻转；通过只表示实验逐度数值 QA，不是正式动画或 Runtime 通过。

[肘部三方案对照](docs/how-to-elbow-comparison.md)已接通辅助骨与 corrective 局部偏移实验；
改善了面积收缩，但仍未达到实验阈值，尚未采用或导出。

[肘部面积检查](docs/how-to-mesh-area-screen.md)已接通逐度扫描与空间定位；
零翻转仍可能严重收缩，四张手臂当前均未通过实验面积阈值。

[关节平面权重改进](docs/how-to-joint-plane-refinement.md)为旧网格生成独立新权重profile，
沿骨段纵向平滑过渡并锁定远端刚性区域，保持旧拓扑/UV和旧QA阈值不变。

[三骨加权网格实验入口](docs/how-to-weighted-mesh.md)已接通：alpha网格、三骨归一化权重、局部坐标LBS
和固定角度翻转/拉伸QA。失败网格保留诊断并阻塞；尚未接正式Spine导出。

[Alpha骨链覆盖分析](docs/how-to-chain-coverage.md)已接通：4连通域、PSD坐标质心和逐骨21点覆盖诊断。
用户指令确认的19项默认选择已封存；无默认建议项保持待处理，覆盖报告不改写选择。

[多骨绑定v2](docs/how-to-layer-binding-v2.md)支持刚性单骨与整臂/整腿三骨链，双侧图层可选两条骨链。
名称侧别只是建议，草稿保存完整选项；网格、权重和动态QA按后续步骤接入，旧v1保持兼容。

[绑定复核草稿](docs/how-to-region-binding-drafts.md)支持逐层选择候选骨骼、记录拆层/语义问题或排除，
整份保存、恢复与撤销；CLI可核验来源并封存。初始记录全部待处理，不自动批准。

[图层绑定候选](docs/how-to-region-bindings.md)现可从辅助骨架生成逐层选项与位置叠图，
验证局部变换的四角重建。三角色62层中15层有建议，47层仍需补充语义或处理结构问题。

[辅助复核骨架预览](docs/how-to-assisted-skeleton.md)已接通：用户修正的17点直接生成20骨候选，
保留中央锚点、标记派生末端并验证局部变换。三个开发角色已重放；正式绑定采用尚待接入。

[关节标注页](docs/how-to-benchmark-pose-evaluation.md)现支持一次加载全部自动建议，
画布点选拖动、撤销、批量确认、整份保存与恢复。带模型建议的结果保存为模型辅助标注。

R2-B 新增[独立关节参考与误差评估](docs/how-to-benchmark-pose-evaluation.md)：显式记录
Benchmark参考，按共同GT点比较旧bbox／Pose／优化结果。三角色已生成空白标注页，
没有真实参考时误差保持未评估，不把草稿自动当作GT。

[R2-B 真实 Pose 入口](docs/how-to-real-pose.md)已在独立环境运行 DWPose ONNX，三个开发
角色各保留133点与完整SimCC张量，自动绑定Benchmark身份并生成只读对照页。
模型可见性/镜像未复核、人工GT仍为空，因此不自动采用或宣称精度验收完成。

[R2-A 技术链](docs/how-to-r2a.md)已接通规范 Pose 文件导入、双侧接触匹配、受约束关节优化与
20 骨候选骨架，一条 CLI 可生成可视报告并精确回读。已用 synthetic fixtures 验证；
真实模型推理已由 R2-B 接通，三角色独立 GT 精度与生产自动采用仍待完成，不将候选视为生产批准。

开发集新入口：[PNG / PSD 坐标复核](docs/how-to-benchmark-mapping.md)，生成离线叠加页，
调整并保存映射候选草稿，无需填写 SHA。支持对应锚点录入、草稿恢复及 CLI 拟合/残差诊断。
映射检查完成后可下载复核请求，显式记录接受/拒绝，并由接受决定准备待标注模板。
新增[图层语义复核](docs/how-to-benchmark-semantics.md)：查看逐层素材、名称建议和空层问题，保存可恢复的待复核标注。
可显式记录语义采用，并在[关节点录入页](docs/how-to-benchmark-joints.md)标记 PSD 坐标或不可观测原因。

首批 Benchmark 已冻结3开发/4可见/3holdout、其余10 reserve；支持源身份验证、
输入alpha检查和诚实的空评测报告。见[实际划分](docs/benchmark/first-batch-2026-09.md)
及[Benchmark CLI](docs/how-to-benchmark.md)。人工映射、坐标变换与关节标注仍待完成。

Spine 预览默认目标现为 **4.3.26**，界面与 CLI 可选择 4.2。
参见 [适配范围与验证边界](docs/spine43-adapter-2026-09.md)；历史 4.2 认证链保留。

开发方向已切换为受限输入自动生产流。主工作台现提供[构建 Spine region 预览](docs/how-to-build-region-spine-preview.md)：无需填写 SHA，支持异步构建、异常定位、复核保存后续跑、取消和 ZIP 下载。PipelineRun CLI 仍可独立使用。首版队列覆盖 setup region 的结构复核；通用 Mesh、动作和 Runtime 队列仍待扩展。见 [真实状态](docs/current-state-2026-09.md)、[新路线](docs/automation-roadmap-2026-09.md) 与 [三种运行模式](docs/adr-pipeline-profiles-v1.md)；旧精确链继续保留。

AutoSpine Workbench 是一个本地人工复核与离线编译工作流，用于查看 See-through PSD 审计结果、校正图层语义和 setup 可见性、调整启发式关节，并保存带 revision 的 override。它不会修改 PSD、审计 JSON 或 PNG；主 authoring 页面写入 `workspace/overrides`，P10 人工复核使用各自独立的 revision namespace，离线 publish/compile 命令按阶段写入内容寻址的 analysis、motion、build 或 runtime 工件。

**P9-real-kimodo-policy-adoption** 对真实 `wave-left-v1` 的 A/B 历史精确链已经关闭；双 SHA 见 [pilot handoff](docs/pilots/kimodo-wave-left-v1.md)。此后两个项目的绑定身份都发生了变化。样本 A 已由操作者确认 `layer-007-handwear-l: forearm.left → upper-arm.left` 并保存 override revision 6；新 Resolved/Manifest/P2–P5、P9、P10.1、P10.2 以及 P10.5b/P10.5c 静态接缝集均已按当前身份重建并精确复验。当前 P10.2 唯一结构拒绝项是旧素材框 containment，完整动作包络已经由动态视口覆盖。样本 B revision 16 仍须按它自己的 current chain 完成相同重建；旧 P9/P10/P3 证据不会跨链继承 authority。

Motion Policy 页面会自动发现与当前 Resolved Project 匹配的 pending P9 草案；唯一候选可自动选中，多个候选只需选择项目。操作者查看角色合成图和 setup 前后关系并明确确认后，服务端会重放当前链、生成正式 Depth policy 与 Depth candidates、发布并复验新的 exact review package，然后进入正常 P9 候选复核。这个“一键草案晋级”只关闭 Depth policy/candidate 准备，不是最终 P9 human adoption。

P10.2 的自由缩放/平移和 `DynamicViewportFit v1` 仍是零权威诊断；在此之上已新增独立的 `CaptureFramingCandidate/Decision v1`。只有 current `accept/adjust` 决定才能进入 package-centric `TemporaryBodySwayPreview v2`。P10.3 已把 Preview v2、固定本地 Spine Player 4.2.119/Chrome 环境校验、显式许可勾选、每次运行二次确认、可查询的异步 append-only job、official Runtime execution v2 封存和 P10.3c v2 交接串为普通用户入口。样本 A 的六次失败采集作为不可变历史保留且没有部分 execution；runner `1.1.0` 的后续 job 已完成 43/43。操作者已经沿 setup + 21 组 A/B 时间轴提交 P10.3c v2 revision 1，43/43 case 均为 `approve`，current head 为 `sampled_visual_approved`。P10.4a v2 现可只凭 completed `job_id` 自动双快照重放该 head；P10.4b v2 已沿同一 job 自动生成九档离散结构点和相邻时间段连续证明。其 CPU 编译运行在独立低优先级 worker 子进程中，页面以 `continuous_boxes` 心跳显示进展，父进程独立复验 staged 结果后才写入完成态；失败尝试保留不可变回执，创建新尝试前必须二次确认。人工视觉仍只覆盖 100% 幅度，可发布安全范围明确不可用，release gate 继续 blocked；既有 v1 preview/capture/review/admission/amplitude/continuous-proof 语义保持冻结。

当前功能及入口以[功能与入口参考](docs/capability-reference.md)为准；尚未实现的能力、依赖和验收顺序见[后续开发路线](docs/development-roadmap.md)。

## 能做什么

- 从 `<workspace>/tmp/psd_audit/results/*/audit.json` 发现项目。
- 在统一画布坐标中查看参考合成图、独立图层与骨架覆盖。
- 检查空图层、未分类语义、低置信度关节和合成差异等 QA 信息。
- 覆盖图层语义、角色左右、setup 可见性、pivot 与 region 目标骨，并逐字段确认人工复核。
- 拖动或精确输入关节坐标，并恢复自动推断位置。
- 使用 optimistic concurrency 保存 override；过期 revision 不会覆盖新结果。
- 每次成功保存都写入 append-only revision 历史，并生成应用人工决定后的 resolved snapshot。
- 以独立 `Resolved Project v1` JSON Schema 和无第三方依赖的严格语义 validator 校验 snapshot 的内容哈希、候选/拆分 provenance、实体交叉引用与派生 QA；既有 r5/r7 历史哈希保持不变。
- 在界面加载内容寻址候选，比较画布标记、alpha 中轴线/接触证据，并记录 accept/adjust/reject/unobservable 决定。
- 候选决定绑定完整内容 SHA；算法输出变化不会把旧决定静默套用到新工件。
- 通过只读验证 API 检查画布、图层 ID、资产路径和骨架结构。
- 离线发布带 provenance 的关节候选、region-first Layer Manifest 与 region-only RigIR bundle。
- 把固定的 COCO17 检测转换为显式左右/镜像 provenance 的 canonical pose，并用人工复核四肢点生成诊断误差报告。
- 对 RigIR 执行跨引用、拓扑、权重、三角形及 timeline 语义验证；不支持特性会明确失败。
- 从精确 P3 bundle 编译四个 canonical 两骨 IK 手柄，固定弯曲方向、可达环和 setup-local 数值探针。
- 编译可复用的 setup-local MotionIR（内建 idle/wave 或显式映射 BVH），并从精确 P3/P4/Motion 地址生成带接触、运动学与 mesh 回归证据的不可变 MotionInstance bundle。
- 以 compiler 1.1.0 严格读取 Kimodo 双根 SOMA77 BVH，并让同一 MotionIR 穿过三 rig 与 Spine 4.2 bundle 兼容性门禁。
- 严格读取 Kimodo SOMA77 NPZ、独立 source sidecar 与显式 map，交叉验证矩阵 FK/关节位置，并发布可重建的五文件 MotionIR bundle。
- 在发布前零写入审计真实 NPZ、recorded sidecar、map、camera、checkpoint manifest 与 generation request 原件；报告只授予 P7/P8 编译准入，不认证 checkpoint 或动作质量。
- 从精确 P7 bundle 与显式静态正交相机生成保留深度、透视缩短和可观测性的 ProjectedMotionIR；候选尺度探针可复用于不同目标 rig，但不会静默生成 runtime scale 或 draw-order timeline。
- 从精确 P3/P5/P8 地址编译 foot-lock 和 depth-order 候选，经完整人工决定生成 reviewed policy、MotionInstance v2、Spine 4.2 v2 preview 与六文件不可变 P9 bundle；既有 v1 内容哈希不变。
- 当绑定或语义修正使 P3/P4/P5 身份变化时，使用 `prepare-motion-policy-review-draft` 交叉重放精确 P3–P8 链，并在新 namespace 中原子准备 Kimodo evidence、standalone Foot 候选和 pending Depth proposal。该草案不会批准 Depth policy、生成 Depth 候选、复用旧人工决定或发布 P9 adoption。
- 在 P9 页面自动发现与当前 Resolved + Manifest 双 SHA 匹配的 pending draft，显示角色和遮挡 pair；一次明确确认后由本机把 proposal 投影为正式人工批准的 Depth policy、生成 Depth candidates，并发布可由既有 P9 页面继续复核的 exact package。该“草案晋级”不决定 Foot/Depth candidates，也不发布 MotionInstance v2 或最终 P9 adoption。
- 在 P9 页面按项目发现并自动加载 exact review package，服务端重算 policy/Foot/Depth/candidate inventory 身份；时间轴辅助采用和“一键采用”只覆盖 `state=candidate`、证据完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot 建议，Depth、`rejected_*`、缺证、非有限值与超阈值项留给人工；一次最终 v1 human adoption 后由本机完成编译、内容寻址发布和 exact verify，review input 下载仅作备份。
- 从已采用的 P9 package 自动发现精确 Layer Manifest/P3/P5/P9 链，在“身体摆动设置”页面重放 idle 行为候选；普通操作者通过角色合成图、四骨示意和少量参数准备 P10.1 决定，无需选择 JSON 或填写 SHA。三个决定按钮都会先显示项目、动作、决定类型和后果；取消、按 Esc 或点击遮罩均零写入，只有在弹窗中确认提交才调用既有 mutation。草稿不具安全权，调整后仍由 P10.2 生成七项采样结构检查并保持发布阻塞。
- P10 package inventory 会保留可精确重放的历史 P9/P10 链供操作者显式查看或审计，但只有与当前 Resolved Project 身份匹配的链才可参与自动推荐；历史链不会因为仍可重放而成为当前推荐或继承旧 P10.1 head。候选准备可在同一服务进程内复用非权威 exact-chain 缓存；每次复用前仍读取全部受保护文件字节重算 seal，任一内容或 inventory 变化都会失效并执行完整 replay。P9 exact replay 采用按 key 的 single-flight，重复并发请求共享一次构建但各自仍取得相同 exact 结果。缓存不跨服务重启，也不缓存 P10.1 history、current head 或 CAS；冷启动始终执行完整 replay。
- P10.2 详情与 P10.2a→P10.1 草稿交接还共享一个有界、进程内的 derived cache。它的 key 同时绑定解析后的 state root、完整 exact package/address、P10.0 candidate SHA、P10.1 current revision/decision SHA，以及 probe、canvas adjustment、dynamic viewport 和 region rebind 四类 analyzer profile SHA；任一身份或算法 profile 变化都不会复用旧结果。缓存值包含可重建的 report、preview、幅度诊断、动态视口和换绑候选；每个请求仍在派生结果前后执行 exact replay 和 current-head 检查。该缓存不落盘、不跨进程、不授予 authority；服务冷启动与首次 package 发现仍可能较慢。
- P10.3c v2 另有可删除、非权威的持久 mount cache。completed job 会在封存后预写 Preview v2 挂载，旧 job 首次读取时自动回填；后续服务重启只重验 exact execution、所选项目的 Resolved/source-raster/算法身份、P3/P5/P9 内容地址、P10.1/CaptureFraming heads 和 Preview/artifact seals，不再枚举和重放无关项目或全部 adoption。snapshot v3 显式绑定 Preview 编译器摘要；摘要由静态依赖闭包生成，当前覆盖 292/755 个包内模块，所以相关算法变化必定失效，而无关页面/服务模块变化不再触发昂贵重建。current-chain 算法指纹以源码和稳定 callable 位置为准，跨 Python 3.12/3.14 一致，常规函数/类方法重绑定仍会失效。candidate 完整校验并预热全部 PNG 后，还会签发 120 秒、进程内、只读图片会话并返回同一快照的 history；页面以最多两张并发后台预载全部 43 帧，切换已载帧不再触发请求时重放。会话只绑定 job/candidate/case/PNG，不写决定、不续期且重启即失效；无会话 exact URL 保留严格 current 校验。人工 decision PUT 禁用持久 mount 与图片 session，实时复验 authority/current heads 后继续执行 head CAS；键控的进程内派生缓存仍可在逐次 current validator 通过时复用计算结果。因此会话期内发生的来源漂移也只能显示旧的内容寻址像素，不能提交旧决定。真实 43-case job 完整回填约 `74.61 s`；持久 mount 下旧 candidate 准备为 `6.00–6.15 s`。本次新进程真实验收中，含 current/history/全部 PNG 预热的 candidate 为 `6.15 s`；随后 43 张、共 13,139,764 bytes 的会话图片顺序读取合计 `334.1 ms`，P50 `6.7 ms`、P95 `11.4 ms`、最大 `23.4 ms`。
- P9/P10 的 current-chain 双快照不再为取得项目 ID 调用完整项目摘要；list/detail API 可用 `project_id` 将发现范围限制到当前项目。stored split revalidation 使用有界进程内缓存，key 绑定 source/preview/manifest 的全字节内容、Resolved/decision 身份与 runtime profile；Layer Manifest 派生缓存也继续绑定 exact Resolved SHA、所有源图层逐字节 SHA 与算法运行身份。任一内容、决定或运行身份变化都会失效，失败不缓存；两份 current-head/current-chain 快照仍完整保留，缓存既不授予 authority，也不以 TTL、mtime 或 `latest` 代替精确重验。实测全项目 warm list/detail 从约 `10.85 s` 降到约 `0.61 s`，A 的 `project_id` 范围 warm 请求约 `0.28 s`；服务冷启动仍需约 `18 s` 完整重放 A 的 P9 链。
- 在“身体摆动结构探针”页面实时分类 current P10.1 heads，仅当 `adjust/pending_probe` ready、与当前 Resolved Project 匹配的项恰好唯一时自动推荐；普通 P10.2 清单隐藏历史不匹配链，只有掌握其 exact package ID 的审计直达入口才能只读查看。详情随后执行编译前后双快照与 exact decision 读取，并把 P10.2 七项结果显示为五项自动结构卡、两项后续门禁卡和有界四骨采样见证；预览支持滚轮/按钮缩放、拖拽平移、重置和按完整动作包络适配，素材 `1024×1024` 只保留为 setup 坐标基准。若旧报告唯一自动拒绝项是 `sampled_canvas_containment` 且动态适配成功，公开 entry 标记为 `viewport_adjustment_available`，但内嵌 v1 report 与 release gate 不变。
- 同一 P10.2 exact schedule 只生成一次完整 pose/attachment geometry，并由此编译 `DynamicViewportFit v1` 及所有越界 region 的 `RegionRebindCandidates v1`。换绑候选只比较当前骨与同链一跳父/子骨，具有 `authority: none`；页面会把推荐带到绑定工作台，在独立建议卡中预览目标骨而不写入共享 Rig 表单。普通保存和 `Ctrl+S` 不能绕过专用采用入口；正式换绑仍需一次明确确认和一次 override 保存。保存会创建新 revision，并使依赖旧 Manifest/P3/P5/P9/P10 地址的产物进入历史链，必须按新身份重建。
- 在同一次 P10.2 详情编译中生成 `BodySwayCanvasAdjustmentCandidates v1`：沿已复核四骨幅度的统一 gain 网格 `0/8…8/8` 做采样画布/几何诊断。结果零权威、零写入；`0/8` 只能区分基础动作越界，不能成为 body-sway 候选。只有非零 gain 的 sampled canvas 和 sampled geometry 同时通过时，才会给出一个 `unvalidated_draft`；操作者仍须把它带回 P10.1、显式确认新 revision，然后重跑 P10.2。
- 冻结 v1：用操作者提供且已授权的官方 Spine 4.2.119 runtime 捕获固定 body-sway case，再由专业用户通过精确四段地址在独立 UI/CLI/API 中逐帧复核，并以 CAS 追加不可变 revision。
- package/job-centric v2：普通用户按项目/动作包准备 Preview v2，经许可与本次运行二次确认创建异步 official Runtime job；completed `job_id` 自动进入 P10.3c v2，普通用户不手填四段地址或 SHA。页面用 setup + 21 组 A/B 时间轴预填本地通过草稿，图片按 exact URL 单页复用、最多两张并发并后台预载全部帧，且真实加载后才计入浏览覆盖；只有完整浏览、剔除异常、current head 和最终声明后才提交人工决定，不会自动批准或解除发布门禁。
- P10.4a v2：从 completed `job_id` 自动解析 execution、current v2 candidate/revision/decision，并执行 `history A → exact replay → history B`；普通页面不选择文件或填写 SHA，结果仅在编译时开放后续分析准入。
- P10.4b v2：以同一 `job_id` 重新准入 P10.4a v2，并在独立 v2 哈希域中编译九档 coupled-gain 结构点和全部相邻 tick 的有界连续证明；独立低优先级子进程执行 CPU 工作，盒级心跳不会阻塞 HTTP 页面/API。`indeterminate` 是完整但未证明的结果，不是执行错误。只有 100% 点继承 sampled visual 审批，不能据此生成可发布安全范围。
- 冻结 v1：`BodySwayReviewAdmission v1` 继续只消费 v1 P10.3c head，不能消费 v2 head。
- 沿已复核四骨幅度向量的统一 gain 射线生成九个离散候选，并以有界区间细分覆盖每一对 sampled-linear preview key；只能授予预览数学模型的结构 claim，runtime、视觉范围、接缝和发布权仍保持阻塞。
- 从精确 Layer Manifest/P3 静态链编译六条四肢 attachment 接缝关系，输出 region/mesh locator 候选与完整算法 profile；只供人工比较，不自动选择锚点。
- 在 P10.5b 页面从 P9 `package_id` 自动闭合精确来源、绑定 current head，并用 `setup_canvas`、attachment `canvas_offset_xy` 与 `anchor_points` 合成父子 alpha、contact bbox 和编号锚点连线；原始 SHA、contact 数字、locator 表和单层图默认收进技术详情。
- 使用确定性的 advisory assist 形成可撤销草稿：唯一候选与不可观测关系自动填入，多候选只标出建议重点查看项，点击候选才形成 `accept` 草稿；建议、高亮和自动草稿都不是批准。一次最终确认才写 P10.5b revision；package 模式下若六关系 ready，会继续发布 P10.5c 并从精确上游读回复验。
- 把完整 P10.4b2 proof 与精确 P10.5c bundle 接入双层 current-head 检查，在全部相邻 tick 和统一 gain 上证明 reviewed-anchor point 的 `4 px²` 工程距离代理；attachment 边界、raster/视觉、runtime 与发布仍保持阻塞。
- 把认证的 P10.5d probe 与其内嵌精确 P9 bundle 重新闭合为 P10.6a 版本中立 setup-local timeline 消费准入，并在纯编译前后重查视觉与接缝 current head；冻结 v1 仍按文件读取，v2 只凭 P10.5d probe/bundle 双 SHA 自动读取 exact bundle 和 P9，不要求选择文件。两者都不发出 MotionInstance v3 或 Spine timeline。
- 将 P10.6a v1/v2 来源分别编译为 MotionInstance v3：冻结 v1 读取完整 wrapper；v2 只凭项目与 P10.5d probe/bundle 双 SHA 自动闭合 admission 和 P9，不选择文件。两条来源合同互不混用，payload 均保持 v3，只允许躯干四骨 rotation 覆盖并逐值保留 MIv2 root/marker/draw-order；三文件 bundle 可按 v3/bundle 双 SHA 历史复验，但不授予永久审批或 Spine 发布权。
- 用版本匹配的 P10.7a v1/v2 adapter 从各自 MotionInstance v3 来源重放 P9/P5/P3 和源 PNG，发布 JSON/atlas/PNG/run/report 五文件 bundle；v2 普通页面从 completed P10.6b 自动携带四个任务 ID，无项目、文件或 SHA 输入。两版 source contract、skeleton hash、run/report 与地址域隔离，compile/store 重查 current heads，历史 verify 不读取 current heads，且 run 只授予 adapter emitted。
- 冻结 P10.7b v1 可用操作者明确确认有权使用的官方 Spine Player 4.2.119，对精确 P10.7a v1 bundle 执行固定 case、完整 setup attachment isolate 的捕获和 sampled raster 指标；它不消费 P10.7a v2 地址。P10.7b v2 已增加版本隔离的 source bridge、严格 session set、bounded collector、loopback-only server 与 real browser runner；runner 只在显式 `license_acknowledged=true` 且 Windows 环境下，对精确 P10.7a v2 只读一次，锁定 Spine Player 4.2.119 runtime/浏览器 lease，并为每个 artifact 使用全新 profile 完成 loopback 采集。runner 结果现可封存为 `captured_unreviewed` evidence：固定五份 JSON 合同文件加声明的 PNG captures，使用独立 namespace/hash domain 原子发布，并由项目、P10.7a v2 skeleton SHA、P10.7a v2 bundle SHA 与 capture bundle SHA 四段地址精确回读。guarded v2 Runtime 授权、manager、执行与 HTTP API 已提交；尚无 v2 metrics、人工复核或发布权；机制测试没有真正启动经授权的官方 Runtime，冻结 v1 输出哈希保持不变。
- 用 strict canonical 请求只读审计两份真实样本从精确 Manifest/P3 到 P10.7b 的八个 checkpoint；readiness v1 已冻结，第八项仍固定为 missing。审计不扫描 `latest` 或 current review head，不自动运行外部阶段、官方 Runtime、发布或写入，也不代替人审。
- 用独立的 P10.7c 命令把精确 P10.7b capture 中唯一的 opaque setup 帧与既有 P6 官方 Runtime approved golden 做零写入 RGBA 对照；命令不启动 Runtime、不修改批准图，也不授予发布权。
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

启动后建议先打开[功能入口中心](http://127.0.0.1:8765/workflow-hub.html)。P10.2 可直接打开[身体摆动结构探针](http://127.0.0.1:8765/body-sway-probe.html)。入口中心可以搜索和筛选全部 Web/CLI/规划入口；CLI 卡片只复制 `python -B -m autospine_workbench <command> --help` 帮助命令，不会让浏览器或服务端直接执行。源码模式下应先在当前 PowerShell 设置 `$env:PYTHONPATH = (Resolve-Path .\src).Path`。卡片中的仓库文档通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开；查看器只读获取 `/docs/<文件名>.md`，并按纯文本显示，不解析其中的 HTML。主绑定复核页面仍是 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。默认配置为：

- workspace：工作台目录的父目录；
- state root：`autospine-workbench/workspace`；
- web root：`autospine-workbench/web`；
- 监听地址：`127.0.0.1:8765`。

覆盖默认值：

```powershell
.\run.ps1 `
  -PythonExe "<python.exe>" `
  -WorkspaceRoot "<workspace-root>" `
  -StateRoot "<state-root>" `
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

本节说明默认的图层/关节 authoring 页面。所有入口可从[功能入口中心](http://127.0.0.1:8765/workflow-hub.html)打开。P9 使用 [Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html)：页面会先发现 current pending draft；操作者确认 setup 遮挡关系后，系统生成正式 Depth policy/Depth candidates 和 exact package，再在同页进入候选复核。草案晋级和最终 P9 adoption 是两次不同的显式人工动作。P10.0–P10.1 使用 [身体摆动设置](http://127.0.0.1:8765/idle-behavior-review.html)，P10.2 使用[身体摆动结构探针](http://127.0.0.1:8765/body-sway-probe.html)；canvas-only 情形会在同页生成 P10.2b 自动取景候选并保存独立 decision。current framing `accept/adjust` 后，从 [P10.3 官方 Runtime 自动采集](http://127.0.0.1:8765/body-sway-runtime-capture.html)选择项目/动作包，检查固定环境，完成许可勾选与本次运行二次确认；完成的异步 job 会自动进入 P10.3c v2 复核。approved 回执继续打开 [P10.4a v2 自动准入](http://127.0.0.1:8765/body-sway-review-admission-v2.html)，准入成功后再以同一 `job_id` 进入 [P10.4b v2 自动安全分析](http://127.0.0.1:8765/body-sway-safety-analysis-v2.html)，全程不选择文件或填写 SHA。旧 [P10.3c v1 视觉复核台](http://127.0.0.1:8765/body-sway-review.html)仅保留历史/回归。静态接缝使用 [Seam Anchor 复核台](http://127.0.0.1:8765/seam-anchor-review.html)。具体流程见[复核并发布 Kimodo 动作策略](docs/how-to-review-kimodo-motion-policy.md)、[复核 idle 行为并运行 body-sway 结构探针](docs/how-to-review-idle-behaviors.md)、[运行 P10.3 官方 Runtime 自动采集](docs/how-to-capture-body-sway-runtime.md)、[复核 P10.3c 官方 Runtime 采样帧](docs/how-to-review-body-sway-runtime.md)、[自动准入 P10.3c v2 结果](docs/how-to-admit-body-sway-review-v2.md)、[分析 P10.4b v2 身体摆动安全性](docs/how-to-analyze-body-sway-safety-v2.md)和[复核静态接缝锚点](docs/how-to-review-seam-anchors.md)。

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
  "schema_version": "autospine-workbench.override/v3",
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
  "split_decisions": {
    "layer-012-sleeves": {
      "action": "accept",
      "split_artifact_sha256": "89abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234567"
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

`joint_overrides` 是与候选算法无关的绝对人工坐标；`joint_decisions` 表示 accept、adjust、reject 或 unobservable，同一关节不能同时出现在两者中。accept 坐标由服务端从内容寻址候选工件派生，客户端不能提交。`split_decisions` 只接受 `accept`/`reject` 和完整 split artifact SHA；服务端会绑定算法、operation config、review target 与 current/stale 状态。`side` 使用 `left`、`right`、`center`、`bilateral` 或 `unknown`，始终表示角色自身左右。`visible` 只定义 setup/复核预览可见性，不会改写 PNG。关节与 pivot 必须是有限数，并位于画布内。完整语义见 [候选关节与切分决定参考](docs/candidate-decisions-reference.md)。

JSON Schema 位于：

- `schemas/override-patch-v3.schema.json`：当前在线 API 的 candidate/split-aware canonical patch；v1/v2 仅用于历史兼容，不能携带 split decision；
- `schemas/resolved-project-v1.schema.json`：resolved authoring snapshot 的严格结构、provenance、候选/拆分决定、派生 QA 与 canonical 内容地址；完整语义仍须经过 Python validator；
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
- `schemas/kimodo-npz-source-v1.schema.json`、`schemas/kimodo-npz-map-v1.schema.json`、`schemas/kimodo-npz-motion-compile-run-v1.schema.json` 与 `schemas/kimodo-pilot-intake-report-v1.schema.json`：真实 pilot 准入报告、正式 P7 原始 NPZ 解释、投影映射与可重建编译 provenance；
- `schemas/camera-model-v1.schema.json`、`schemas/projected-motion-ir-v1.schema.json`、`schemas/projected-motion-compile-run-v1.schema.json` 与 `schemas/projected-scale-probes-v1.schema.json`：P8 相机、3D→2D 投影证据、编译 provenance 与目标 rig 候选尺度探针；
- `schemas/motion-instance-v2.schema.json`、`schemas/motion-policy-decision-v1.schema.json`、`schemas/reviewed-motion-policy-v1.schema.json` 与 `schemas/reviewed-motion-bundle-run-v1.schema.json`：P9 人工决定、root/draw-order overlay、v2 instance 与六文件 bundle provenance；
- `schemas/idle-behavior-candidates-v1.schema.json`、`schemas/idle-behavior-decision-v1.schema.json`、`schemas/body-sway-probe-report-v1.schema.json` 与 `schemas/body-sway-canvas-adjustment-candidates-v1.schema.json`：P10.0–P10.2a idle 候选、人工参数决定、只读采样结构诊断与零权威离散 gain 修正候选；
- `schemas/body-sway-runtime-capture-v1.schema.json`、`schemas/body-sway-visual-review-*.schema.json`、`schemas/body-sway-review-admission-v1.schema.json`、`schemas/body-sway-review-admission-v2.schema.json`、`schemas/body-sway-amplitude-envelope-candidate-v1.schema.json`、`schemas/body-sway-continuous-preview-proof-v1.schema.json`、`schemas/body-sway-amplitude-envelope-candidate-v2.schema.json` 与 `schemas/body-sway-continuous-preview-proof-v2.schema.json`：P10.3 runtime 证据、sampled visual revision、冻结 v1/P10.4a v2 当前审批头准入，以及互不混用的 v1/v2 幅度候选和连续证明；
- `schemas/seam-anchor-candidates-v1.schema.json`、`schemas/seam-anchor-review-decision-v1.schema.json`、`schemas/reviewed-seam-anchor-set-v1.schema.json` 与 `schemas/body-sway-dynamic-seam-probe-v1.schema.json`：P10.5a 六条静态接缝候选、P10.5b 候选/P3 绑定的人工 revision、P10.5c 固定六关系的已复核静态锚点集，以及 P10.5d 动态 reviewed-anchor proximity 工程代理；
- `schemas/body-sway-motion-consumer-admission-v1.schema.json` 与 `schemas/body-sway-motion-consumer-admission-v2.schema.json`：互不混用的 P10.6a v1/v2 source closure、unit-gain setup-local motion domain 与 compile-time 双 head seal；v2 固定绑定 P10.5d v2 三文件 bundle 和其中的 exact P9 地址；
- `schemas/motion-instance-v3.schema.json`、`schemas/motion-instance-v3-bundle-run-v1.schema.json` 与 `schemas/motion-instance-v3-bundle-run-v2.schema.json`：共用的 P10.6b setup-local v3 payload、版本隔离的三文件 bundle provenance、能力边界与固定 blocked release gate；
- `schemas/spine42-v3-export-run-v1.schema.json`、`schemas/spine42-v3-export-report-v1.schema.json`、`schemas/spine42-v3-export-run-v2.schema.json` 与 `schemas/spine42-v3-export-report-v2.schema.json`：P10.7a 版本隔离五文件 adapter bundle 的精确 P3/MIv3 来源、输出身份、能力边界与固定 blocked release gate；
- `schemas/spine42-v3-runtime-plan-v2.schema.json`、`schemas/spine42-v3-runtime-source-admission-v2.schema.json`、`schemas/spine42-v3-runtime-session-set-v2.schema.json`、`schemas/spine42-v3-runtime-reports-v2.schema.json` 与 `schemas/spine42-v3-runtime-capture-manifest-v2.schema.json`：P10.7b v2 固定 capture plan、精确 P10.7a v2 来源准入、session/report 身份、captured-unreviewed 五份 JSON + PNG inventory、资源上限、权限边界与 blocked release gate；
- `schemas/spine42-v3-readiness-request-v1.schema.json` 与 `schemas/spine42-v3-readiness-report-v1.schema.json`：冻结的 P10.7b-readiness exact-address 预检合同；其第八项保持 `p6_setup_golden_comparison_not_declared`；
- `schemas/spine42-v3-setup-regression-request-v1.schema.json` 与 `schemas/spine42-v3-setup-regression-report-v1.schema.json`：独立 P10.7c P3/P6/P10.7a/capture/approved-golden 来源闭合、冻结 comparison profile、RGBA 指标与 path-free 内容身份；
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

P3 profile-v1 的 mesh eligibility 是有意收窄的合同：只有精确语义 `body.leg`、左右明确、绑定 `thigh.<side>` 且存在直接子骨 `calf.<side>` 的 region 才能成为两骨 hinge。`body.arm.upper/lower` 与 `body.leg.upper/lower` 仍保留已审语义和目标骨绑定，但在 v1 中按 rigid region 输出；若手工伪造为 hinge，validator 会 fail closed。真正的分段手臂/腿 mesh、arm-aware 权重与 P5 mesh regression 必须另立 P3/P5 v2，不能静默扩写 v1。

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

P5 将动作与目标 rig 分开内容寻址。内建 `idle`/`wave.left`、显式 BVH map、正式 Kimodo NPZ、目标重定向及只读复验分别使用 `compile-builtin-motion`、`compile-bvh-motion`、`compile-kimodo-motion`、`compile-motion-retarget` 与对应 verify 命令。所有命令只接受精确 SHA，不解析 `latest`；通用合同、固定地址、A/B 示例和排障步骤见 [编译、重定向并复验 P5 动画](docs/how-to-compile-motion.md)。真实 Kimodo 在三输入 P7 边界之前，先按[真实 Pilot 输入审计](docs/how-to-audit-real-kimodo-pilot-intake.md)闭合六份输入。

正式 Kimodo NPZ 先用以下入口做零写入准入；它不会发布工件或回显输入路径：

```powershell
python -m autospine_workbench audit-kimodo-pilot-intake `
  <raw.npz> <sidecar.json> <map.json> <camera.json> `
  --checkpoint-manifest <checkpoint.manifest> `
  --generation-request <generation-request>
```

审计通过后才用以下入口发布与只读复验；编译命令不会搜索相邻 sidecar 或 map：

```powershell
python -m autospine_workbench compile-kimodo-motion `
  .\inputs\motion.npz .\inputs\motion.source.json .\inputs\motion.map.json `
  --state-root .\workspace

python -m autospine_workbench verify-kimodo-motion `
  --clip-sha256 <motion-ir-sha256> `
  --bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace
```

P8 从上述精确 P7 双 SHA 和一个显式 `camera.json` 发布三文件投影证据 bundle；验证命令会重放 P7 的原始 NPZ，再逐字节重建 P8。完整相机合同、固定地址、候选尺度探针和失败边界见 [编译并复验 P8 投影证据](docs/how-to-compile-projected-motion.md)。

```powershell
python -m autospine_workbench compile-projected-motion `
  .\inputs\camera.json `
  --motion-clip-sha256 <motion-ir-sha256> `
  --motion-bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace

python -m autospine_workbench verify-projected-motion `
  --projected-motion-sha256 <projected-motion-sha256> `
  --bundle-sha256 <projected-bundle-sha256> `
  --state-root .\workspace
```

P9 从精确 P3/P5/P8 身份发布候选，把人工决定编译为 reviewed root/draw-order policy，再生成 MotionInstance v2、Spine preview 和可独立复验的 bundle。当 P3/P4/P5 因新绑定或语义修正而改变时，`prepare-motion-policy-review-draft` 先交叉验证精确 P3/P4/P5/P7/P8，再将共享 Kimodo evidence、standalone Foot report、pending Depth proposal 和 draft manifest 原子写入一个新 review namespace。草案本身没有正式 `depth-pair-policy.json`、Depth candidates、decision 或 P9 bundle，不能沿用旧决定。P9 页面现通过独立 draft API 自动发现 current 草案；一次明确确认后，服务端再次检查 current chain，把 proposal 投影为正式 policy、生成 Depth candidates、原子发布三文件 exact review package 并读回复验。样本 A revision 6 与样本 B revision 16 已分别准备 `wave-left-v1-r6-draft`、`wave-left-v1-r16-draft`；具体身份与限制见 [pilot handoff](docs/pilots/kimodo-wave-left-v1.md)。草案晋级只让 package 进入下一段候选复核，绝不等同于最终 P9 adoption。CLI 草案准备回执仅返回 namespace、project、是否幂等复用及三份内容 SHA，不泄露本机目录。完整命令和边界见 [准备新的 Motion Policy 复核草案](docs/how-to-prepare-motion-policy-review-draft.md)。

复核页先从只读 package API 获取可用项目/动作，并按推荐或用户选择的 exact package 自动加载正式 policy、Foot 与 Depth；从绑定工作台进入时 URL 会携带当前 project，不会静默跳到另一角色。服务端不按 mtime 猜测 `latest`，package 身份绑定项目、动作、clip、三份报告 SHA 和 candidate inventory，并额外按当前 Resolved Project + Layer Manifest 双 SHA 标记 `current/historical`。历史 exact package 继续保留在 inventory 中供审计，但在页面中为禁用只读项，不得自动加载、预检或采用。随后 `POST /api/motion-policy/preflight` 再次重算完整 standalone 合同、source/policy 交叉绑定与候选 ID 清单摘要。页面在该快照上推导时间轴、足点 observation、重点窗口和连续证据段；拖动时间轴或一键操作只会为尚未决定、`state=candidate`、observations 完整有限且 correction ratio/residual 均不超过各自合同上限 80% 的 Foot candidates 写入带来源、可撤销的辅助草稿，不会覆盖已有人工决定。Depth、`rejected_*`、缺证、非有限值、超阈值和 `adjust` 不自动接受；重点窗口本身只是视觉提示，不影响安全判定。

最终结果仍按 candidate 展开为既有四字段 review input，并由操作者做一次明确 v1 human adoption。`POST /api/motion-policy/review-packages/{package_id}/adoptions` 使用 `motion-policy-adoption-v1` intent，在任何写入前执行 current-chain 快照 A、exact package/current 校验与快照 B 一致性检查；历史 package 返回明确的只读 409，且零写入。只有两份完整快照实际不同时才返回 `*_project_chain_changed` 409；ProjectStore、临时目录、图层 materialization 或 Manifest 重建不可用均返回 path-free `*_project_chain_unavailable` 500，不会被误写成并发漂移，也不会进入发布。通过后它调用既有 compiler/store/reader，原子发布六文件 P9 bundle，并按返回的双 SHA exact verify。Preflight、辅助草稿或 100% 覆盖都不是发布凭据；下载仅作备份，CLI 保留为独立专业复验。专业模式保留三文件/SHA 手工导入，用于审计和排障。完整操作见 [复核并发布 Kimodo 动作策略](docs/how-to-review-kimodo-motion-policy.md)。

P10.0–P10.2a 从精确 Layer Manifest/P3/P5/P9 链先编译 idle candidates，再把独立人工 review 编译为 decision，最后为唯一的 `body_sway / adjust / pending_probe` current head 生成结构探针。P10.1 的三个决定按钮保留二次确认和 candidate-bound CAS；P10.2 则是无人工 action 的只读诊断。详情同步生成零权威的统一 gain、动态视口和 region 换绑候选；同一 exact schedule 只生成一次完整 pose/attachment geometry。页面把 `1024×1024` 当成素材/setup 坐标而非 Rig 硬边界，支持自由缩放、平移、重置和完整动作包络适配。自动探针 API 在编译前后各读取一次 current head，exact decision、revision 或 candidate 漂移都会 fail closed。进程内缓存都不落盘、不授予 authority。A 的旧 P10.1 r2/report `4406289e…` 记录了产生 r6 换绑建议的历史链；revision 6 已采用建议，current P9/P10.1/P10.2 也已重建。当前新链仅保留 canvas-only 拒绝，CaptureFraming 已由操作者接受 revision 1；六次旧 runner 真实 job 均失败且无部分证据，runner 1.1.0 的后续 job 已完成 43/43，P10.3c revision 1 已批准全部 43 个 sampled cases。完整语义见 [复核 idle 行为并运行 body-sway 结构探针](docs/how-to-review-idle-behaviors.md)。

P10.3a–P10.3c 的 v1 合同已经冻结。当前 v2 链只接受 current CaptureFraming `accept/adjust`，并把 P10.1/P10.2、framing candidate/decision/revision、world viewport、Preview v2、projection、plan、source、runtime JS/CSS/package/LICENSE、Chrome、assets、timing、selection 与完整 cases 绑定到 exact session 和 execution bundle。普通页面按 package 自动闭合来源，要求显式许可勾选和每次运行二次确认，再创建可恢复查询的 append-only 异步 job。完成后由 `job_id` 自动解析四段 exact 地址并进入独立 P10.3c v2 candidate/history/decision 链；43 case 在 UI 中压缩为 setup + 21 组 A/B 时间点，默认通过只存在于浏览器草稿，人工判断绝不自动提交。execution v2 runner `1.1.0` 使用 `page_lifetime=collector-terminal`，移除会与异步 collector 竞争的 `--dump-dom`/`--virtual-time-budget`；只有 exact 截图已提交且主动 teardown 引发的 stdout reader 关闭异常可被容忍，提交前读取失败与输出超限仍 fail closed。样本 A 的六次失败 job 没有部分证据；runner 升级后的 job 已完成 43/43，操作者已提交 43/43 approve 的 P10.3c revision 1。release gate 继续 blocked。操作见 [运行 P10.3 官方 Runtime 自动采集](docs/how-to-capture-body-sway-runtime.md)与[复核 P10.3c 官方 Runtime 采样帧](docs/how-to-review-body-sway-runtime.md)。

冻结 v1 的 P10.4a 用 `compile-body-sway-review-admission` 重放 v1 P10/capture 链，不能消费 P10.3c v2 head。独立 P10.4a v2 已提供 job-centric HTTP 页面及 `compile/verify-body-sway-review-admission-v2`：它从 completed job 自动解析 exact execution 和 current v2 head，执行 `history A → exact decision/execution replay → history B`，输出 path-free、compile-time-only admission。成功仍不开放 release authority，并可把同一 `job_id` 交给 P10.4b v2。操作见 [自动准入 P10.3c v2 视觉复核结果](docs/how-to-admit-body-sway-review-v2.md)；[旧文档](docs/how-to-admit-body-sway-review.md)只适用于冻结 v1。

P10.4b v2 通过普通页面或 `compile-body-sway-safety-analysis-v2 <job_id>` 自动重放 current P10.4a v2 admission，在独立 v2 Schema、算法 profile 与哈希域内生成 `0/8…8/8` 九个 coupled-gain 结构点，并对每一对 Preview v2 相邻 tick 与统一 `λ∈[0,1]` 做有界区间证明。HTTP manager 把编译放入独立低优先级 worker 子进程，并用有界协议接收固定阶段和 `continuous_boxes` 心跳；子进程只写 staged 文档，父进程独立重读验证且是 append-only run history/`completed` 的唯一写入者。`indeterminate` 是合法完成结果；它表示预算内没有获得完整证明，而不是运行失败。失败 receipt 不可变，页面二次确认后才创建新 attempt，且不复用旧部分输出。只有 `8/8` 点继承官方 sampled visual 审批，其他幅度点和连续区间不具备人工视觉覆盖；可发布安全范围、seam、runtime 等价、MotionInstance v3 与 release authority 均保持 false/blocked。普通 HTTP 页面只显示两份结果的 path-free 内容地址回执；完整 canonical 文档仅由专业 CLI 本机输出。完整操作见 [分析 P10.4b v2 身体摆动安全性](docs/how-to-analyze-body-sway-safety-v2.md)。

冻结 v1 的 P10.4b1 用 `compile-body-sway-amplitude-envelope` 在已复核四骨幅度向量的统一 gain 射线上检查 `0/8…8/8` 九个离散 key 状态。`8/8` 必须逐字节重放 P10.2 evidence 与临时 preview rotation keys，分析完成后还会再次执行 current-head 双快照；其余 gain 明确为未视觉复核的 candidate。该命令不能消费 P10.4a v2 admission，也不推断点间区间、连续时间或安全范围。完整操作见 [编译 body-sway 幅度包络候选（冻结 v1）](docs/how-to-compile-body-sway-amplitude-envelope.md)。

冻结 v1 的 P10.4b2 用 `compile-body-sway-continuous-proof` 重放 v1 P10.4b1，并以向外舍入的有界区间细分覆盖 `λ∈[0,1]` 与每一对 sampled-linear preview key。该命令不能消费 P10.4a v2 admission。任何预算耗尽、异常、非有限值或未闭合边界都只产生 `indeterminate`；全段通过也只证明 preview-model 的 FK、画布、mesh 和共享索引结构，不证明平台 libm/runtime 等价、视觉范围、接缝或发布权。完整操作见 [编译 body-sway 连续预览模型证明（冻结 v1）](docs/how-to-compile-body-sway-continuous-proof.md)。

P10.5a 用 `compile-seam-anchor-candidates` 从一个精确 Layer Manifest SHA 和一个精确 P3 双 SHA 地址只读编译六条静态接缝关系。generator 绑定完整 canonical algorithm profile；candidate 只含 2–4 对 Q4096 region/Q65535 mesh locator，gap、mesh-mesh 和不可表示状态不会产生 fallback。完整参数、真实样本 golden 与人工边界见 [编译 P10.5a 静态接缝锚点候选](docs/how-to-compile-seam-anchor-candidates.md)。

P10.5b 在独立页面、CLI 与精确 REST API 上比较 P10.5a option，并把固定六关系的 `accept/adjust/reject/unobservable` 选择追加为 candidate-bound write-once revision。candidate 响应同时提供 `setup_canvas`、父子 attachment 的 `canvas_offset_xy`/`anchor_points` 和确定性 advisory assist；页面把 alpha、contact bbox、编号锚点与连线放在主视图，把 SHA、数值、locator 与单层图默认折叠。package 自动入口绑定 current head，并把唯一候选与不可观测项填成可撤销草稿；多候选只高亮建议重点查看项，点击才形成 `accept` 草稿。prepare/GET 与所有草稿均零写入，只有最后一次明确确认才以 base revision/head SHA 做严格 CAS。完整流程见 [复核 P10.5b 静态接缝锚点](docs/how-to-review-seam-anchors.md)。

P10.5c 用 `compile-reviewed-seam-anchor-set` 按 `history A → exact decision/P3/candidate replay → pure compile → history B` 确认指定 ready revision 仍是当前 head，再发布固定三文件、双 SHA 寻址的 ReviewedSeamAnchorSet bundle；`verify-reviewed-seam-anchor-set` 只按显式地址重放历史 bundle，不把历史复验冒充 current-head authority。package 模式的最后一次 P10.5b 确认会在 ready 时调用独立 `seam-publications` 写边界，服务端重放原 package/current decision、发布 P10.5c 并 exact verify，返回 path-free receipt；若 decision 已提交而 publication 失败，只重试 P10.5c。手工地址模式仍只提交 P10.5b，CLI 作为专业发布/复验入口。真实样本 A 已取得并精确复验这份静态锚点回执，固定身份记录在 [pilot handoff](docs/pilots/kimodo-wave-left-v1.md)；它不授予动态接缝或 Runtime 通过。完整命令、错误码、bundle inventory 与真实 A/B test-only gate 边界见 [编译并复验 P10.5c 静态接缝锚点集](docs/how-to-compile-reviewed-seam-anchor-set.md)。

冻结 P10.5d v1 用 `compile-body-sway-dynamic-seam-probe` 读取完整 P10.4b2 v1 proof 文件与一个精确 P10.5c 双 SHA bundle，在分析前后分别重查视觉和接缝 current head，并覆盖每一对相邻 tick、统一 `λ∈[0,1]` 和全部 reviewed anchor pairs。成功 stdout 已包含完整 path-free probe；命令零写入，退出 `0` 时 probe 仍可能为 `indeterminate`。`4 px² = 2 px` 只是一项 anchor-point 工程代理，不是 attachment 边界、raster/视觉或 runtime 结论。完整操作、双层快照、失败语义与真实 A/B blocked gate 见 [探测 P10.5d body-sway 动态接缝锚点](docs/how-to-probe-body-sway-dynamic-seams.md)。

P10.5d v2 已交付 `compile-body-sway-dynamic-seam-probe-v2`、`verify-body-sway-dynamic-seam-bundle-v2` 和 [自动分析页](http://127.0.0.1:8765/body-sway-dynamic-seam-v2.html)。P10.4b 完成态可一键携带 exact `job_id+safety_run_id` 进入；服务端自动解析 current P10.5c，以 append-only attempt 和独立 BelowNormal worker 编译，父进程再做 exact readback/current-head recheck。compile 发布 `source + probe + bundle-manifest` 固定三文件 bundle；历史 verify 不读取 current head，也不授予 current authority。失败回执不可变，新 attempt 需要二次确认。自动入口已经交付，但真实 A 仍须等待当前 P10.4b run 完成并重启服务后执行；overlap、raster、Runtime、视觉和 release 继续 blocked。操作见 [编译并复验 P10.5d v2 动态接缝结构证据](docs/how-to-compile-body-sway-dynamic-seam-v2.md)。

P10.6a 用 `compile-body-sway-motion-consumer-admission` 读取一个完整 canonical P10.5d probe 文件及其显式 SHA，从 probe source closure 中按精确 P9 MotionInstance v2/bundle 地址复验 reviewed-motion bundle，并在 pure core 编译前后重查视觉与接缝 current head。输出内嵌完整 probe、unit-gain setup-local rotation timeline domain 和 MIv2 原有 root/marker/draw-order channels；命令零写入，head scope 仅为 `compile_time`，不发出 MotionInstance v3、Spine adapter 或发布 timeline。操作与边界见 [编译 P10.6a body-sway 动作消费准入](docs/how-to-compile-body-sway-motion-consumer-admission.md)。

P10.6a v2 已交付 `compile-body-sway-motion-consumer-admission-v2`。公开输入只有项目 ID 与 P10.5d v2 probe/bundle 双 SHA；命令按精确地址读取固定三文件 bundle，从内嵌 source closure 自动重放 P9，并在 pure core 前后复查同一 visual-v2/seam-v1 current heads。它不接收文件路径、不扫描 `latest`、全程零写入；成功只产生 path-free、compile-time admission。冻结 v1 命令继续只接受 v1 probe，现有 P10.6b v1 也不会静默消费 v2 admission。操作见 [编译 P10.6a v2 动作消费准入](docs/how-to-compile-body-sway-motion-consumer-admission-v2.md)。

P10.6b v1 用 `compile-body-sway-motion-instance-v3` 严格读取 P10.6a v1 的完整成功 stdout 与显式 admission SHA，按内嵌地址复验 P9，在纯编译前后重新观察 visual/seam current heads，然后原子发布 `admission + MotionInstance v3 + run` 三文件 bundle。`verify-body-sway-motion-instance-v3` 只按精确 v3/bundle 双 SHA 历史重放，不读取 current head。source `sampled-linear` 被明确编译为 target `linear`；MIv2 基础 channels 不变，rotation 只允许覆盖躯干四骨。该冻结入口不能消费 P10.6a v2；完整命令、错误与权限边界见 [编译并复验 P10.6b MotionInstance v3](docs/how-to-compile-motion-instance-v3.md)。

P10.6b v2 已交付 `compile-body-sway-motion-instance-v3-v2` 与 `verify-body-sway-motion-instance-v3-v2`。compile 公开输入只有项目和 P10.5d v2 probe/bundle 双 SHA；它自动读取 exact P10.5d、P9，生成并 detached-replay P10.6a v2 admission，在 current-head 门禁下发布 `admission-v2 + MotionInstance v3 + run-v2`。verify 只收项目与 MIv3/bundle 双 SHA，不选择文件或读取 current heads。payload 继续是 `format_version=3`，但 source、bundle 地址域和 run contract 是 v2；冻结 v1 reader 不接受它。完整操作见 [编译并复验 P10.6b v2 MotionInstance v3](docs/how-to-compile-motion-instance-v3-v2.md)。

非专业用户应从 certified 的 P10.5d v2 完成页点击“继续生成 MotionInstance v3”：该[自动页面](http://127.0.0.1:8765/motion-instance-v3-v2.html)会沿精确任务地址生成并读回三文件 bundle，无需选择项目、文件或填写 SHA。完成后可继续进入 P10.7a v2 自动 adapter 页面。

冻结 P10.7a v1 用 `compile-body-sway-spine42-v3` 从 v1-source MIv3 双 SHA完整重放 P9/P5/P3、RigIR 与源 PNG，并以独立 adapter profile 发布 `skeleton.json/.atlas/.png/run/report` 五文件 bundle。`verify-body-sway-spine42-v3` 只按 skeleton/bundle 双 SHA 历史重放，不读取 current head。未知 timeline/attachment/constraint 会 fail loud；成功只声明 adapter emitted，不声明官方 Runtime、raster、永久 head、publishable timeline 或 release authority。该来源合同不能直接读取 P10.6b v2 bundle。冻结入口操作见 [编译并复验 P10.7a Spine 4.2 v3](docs/how-to-compile-spine42-v3.md)。

P10.7a v2 已交付独立 source contract、adapter profile、skeleton hash、run/report 合同、`spine42-v3-v2/<skeleton-sha>/<bundle-sha>` 地址域、五文件原子 store 与 exact reader。普通用户从 completed P10.6b v2 页面继续，[自动页面](http://127.0.0.1:8765/spine42-v3-v2.html)携带 `job_id+safety_run_id+dynamic_run_id+motion_run_id`，自动 inspect/start/poll/readback，无需选择项目、文件或填写 SHA；失败重试保留旧 attempt 并要求确认。专业 CLI 为 `compile-body-sway-spine42-v3-v2` 与 `verify-body-sway-spine42-v3-v2`。成功仍只授予 `spine_adapter_emitted=true`；五文件 exact readback 不证明 overlap、动态接缝、完整边界、官方 Runtime、Runtime 等价、raster 视觉、永久 head、可发布 timeline 或 release。操作见 [自动生成并复验 P10.7a v2 Spine 4.2 v3 Adapter](docs/how-to-compile-spine42-v3-v2.md)。

P10.7b v2 已在只读 `VerifiedSpine42V3RuntimeSourceBridgeV2` 后交付严格 session 与 real browser runner。bridge 只按项目、P10.7a v2 skeleton SHA 和 bundle SHA exact replay 五文件 adapter，并在独立 v2 哈希域中生成 blocked plan/admission；session set 逐 artifact 绑定 admission、plan、Runtime 包字节、adapter 资产和预期 observables。bounded collector 只接受每个 artifact 一次终态结果，loopback-only server 严格校验 Host/Origin、路径、内容类型与输入交叉绑定。`run_spine42_v3_runtime_capture_v2` 要求显式许可确认和 Windows，对 P10.7a v2 bundle 只执行一次 exact read，持有固定 Spine Player 4.2.119 runtime 与 browser executable lease，每个 artifact 使用独立临时 browser profile 经 loopback 采集，并在结束前重验 Runtime 与浏览器身份。runner-issued 结果现可编译为 `captured_unreviewed` evidence/bundle；库存固定以 `capture-manifest-v2.json`、plan、admission、session set、runtime reports 五份 JSON 开头，再按 plan 顺序附带 PNG captures。`Spine42V3RuntimeStoreV2` 在独立 `spine42-v3-runtime-v2` namespace 和 v2 bundle hash domain 下原子发布，`VerifiedSpine42V3RuntimeReaderV2` 只接受项目+skeleton+P10.7a bundle+capture bundle 四段显式地址并完整重放。guarded v2 Runtime 授权、manager、执行与 HTTP API 已提交；当前没有 v2 metrics、人工复核或发布权；机制测试使用模拟边界，没有真正启动经授权的官方 Runtime。冻结 P10.7b v1 的 source/session、合同和输出哈希均未改变。产品开发转向项目级 PipelineRun 与异常复核，不再扩展新的 P10.x 纵向阶段。

P10.7b v1 既有 `capture-body-sway-spine42-v3-runtime`、`verify-body-sway-spine42-v3-runtime`、`prepare-body-sway-spine42-v3-raster-review` 与 `submit-body-sway-spine42-v3-raster-review` 继续只消费 P10.7a v1 地址，不能接受 P10.7a v2 skeleton/bundle SHA。P10.7a v2 页面不会启动外部 Runtime，也不能把 v2 SHA 交给这些冻结入口。两份真实 See-through 样本的官方 Runtime 捕获和逐项人工验收仍待完成。v1 操作见 [捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](docs/how-to-capture-spine42-v3-runtime.md)。

P10.7b-readiness 用 `audit-body-sway-spine42-v3-readiness --manifest ... --state-root .\workspace [--document-only]` 对请求中显式声明的真实地址做零写入预检。readiness v1 的 Schema、哈希与八项 checkpoint 语义已经冻结，第八项仍固定报告 `p6_setup_golden_comparison_not_declared`；新增 P10.7c 不会反向改写它。仓库中的 canonical baseline 示例仍只固定两份已审计 Manifest/P3 地址，后续字段为 `null`，所以直接运行它仍报告 P9 未声明；这不代表当前工作区没有 current 工件。A revision 6 已完成 current P9/P10，并以 candidate `ea1c0211…`、decision `9db91b9a…`、reviewed set `00de666e…`、bundle `e23e3792…` 闭合 P10.5b/P10.5c 静态接缝；B revision 16 仍须完成自己的 P9/P10/seam 链。冻结请求中的 `null` 只表示地址未声明，不能抹去或替代这些 current 事实。操作见 [审计两份真实样本的 Spine 4.2 v3 就绪状态](docs/how-to-audit-spine42-v3-readiness.md)。

P10.7c 已交付独立 `compare-body-sway-spine42-v3-setup-golden` 命令。它读取 strict canonical 请求、两份操作者选定的 P6 批准合同和精确 P10.7a/P10.7b 地址，只读重放证据后比较 capture 中唯一的 `setup + opaque_composite` 与对应 approved PNG；报告自哈希只是内容身份，不替代证据重放。命令不会启动官方 Runtime、扫描 mutable head、写入 state 或修改 golden，标准输出仍是临时、不可寻址结果。共享 `wave-left-v1` 已形成 P7/P8、绑定到 A/B 的 P5 及已复验 P9 exact 地址；A/B 仍受 seam、P10.7a/capture 等前置阻塞，因而尚未执行或通过这项真实样本对照。请求制作、命令和结果解释见 [对照 P10.7c Spine 4.2 v3 Setup Golden](docs/how-to-compare-spine42-v3-setup-golden.md)。

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
| `GET` | `/api/motion-policy/review-drafts` | 发现内容封存的 pending P9 草案，按当前 Resolved + Manifest 双 SHA 分类，只推荐唯一 current draft |
| `GET` | `/api/motion-policy/review-drafts/{draft_id}` | 按完整草案 ID 读取 proposal SHA 与 path-free 遮挡语义摘要；不返回 proposal 自由文本，历史草案只读 |
| `POST` | `/api/motion-policy/review-drafts/{draft_id}/policy-adoptions` | 以 `depth-policy-draft-adoption-v1` intent 和显式确认晋级 current 草案，生成正式 Depth policy/Depth candidates 与 exact review package；不提交最终 P9 adoption |
| `GET` | `/api/motion-policy/review-packages` | 列出本地 P9 exact review package，并给出确定性的推荐 package ID |
| `GET` | `/api/motion-policy/review-packages/{package_id}` | 读取并重验精确 package 的正式 policy、Foot/Depth reports 与 candidate inventory；响应不暴露本地路径 |
| `GET` | `/api/motion-policy/review-packages/{package_id}/seam-review-entry` | 零写入重放 exact package 与共享 P3 来源，复验 P3 bundle，并返回 path-free Seam 地址、candidate 身份、可观测性摘要与 blocker |
| `POST` | `/api/motion-policy/review-packages/{package_id}/seam-publications` | 以独立 intent 从已提交的 current ready P10.5b revision 发布 P10.5c，并返回 exact-readback path-free receipt |
| `POST` | `/api/motion-policy/preflight` | 以 `motion-policy-preflight-v1` intent 运行 loopback-only、zero-write Python policy identity 或 candidate inventory 预检 |
| `POST` | `/api/motion-policy/review-packages/{package_id}/adoptions` | 以 `motion-policy-adoption-v1` intent 接收严格 human review input，重读 exact package，编译并发布 P9 六文件 bundle，再按双 SHA 精确复验 |
| `GET` | `/api/idle-behavior/review-packages` | 发现已 adopted 的 P9 exact chain；可用 `project_id` 限定范围；P9 replay 按 key single-flight，缓存命中仍全字节 seal 重验，零写入且不读取 P10.1 history |
| `GET` | `/api/idle-behavior/review-packages/{package_id}` | 准备 P10.0 候选与角色预览；可带匹配的 `project_id` 限定范围；exact-chain/split 缓存非权威，history/current head 与双快照始终实时读取 |
| `POST` | `/api/idle-behavior/review-packages/{package_id}/decisions` | 仅在二次确认后以 intent 和 current-head CAS 追加 P10.1 revision；缓存不参与 CAS |
| `GET` | `/api/idle-behavior/structural-probes` | 实时分类 P10.1 current heads，并只列出、推荐与当前 Resolved Project 匹配的 `adjust/pending_probe` package；历史不匹配链仅能凭 exact package ID 走只读审计详情；零写入 |
| `GET` | `/api/idle-behavior/structural-probes/{package_id}` | exact decision 与双 head 快照下编译 P10.2 七项诊断和有界可视投影；有界 derived cache 命中也不跳过前后 exact replay/current-head 检查；零写入 |
| `POST` | `/api/idle-behavior/structural-probes/{package_id}/rebind-adoptions/{candidate_sha256}` | 以 `region-rebind-adoption-v1` intent 采用一次明确确认的自动换绑建议；服务端重放 exact 候选、当前 chain/来源骨/P10.1 head，并在共享事务锁与 override CAS 下保存带 provenance 的新 revision |
| `POST` | `/api/idle-behavior/structural-probes/{package_id}/capture-framing-decisions` | 以 `capture-framing-human-review-v1` intent 和显式确认保存 P10.2b 取景 revision；服务端重建候选、双检查 current P10.1/project chain，并以 candidate-bound CAS 追加历史 |
| `GET` | `/api/idle-behavior/review-packages/{package_id}/canvas-adjustment-drafts/{candidate_sha256}` | 以同一有界 derived cache 重放 P10.2a，并按完整 package/candidate/current revision/decision 身份准备零权威 P10.1 草稿；不写 revision |
| `GET` | `/api/p10/runtime-capture/packages/{package_id}` | 自动重放 current P10.1/CaptureFraming、准备 Preview v2 并校验固定 Runtime/Chrome 环境；零写入 |
| `POST` | `/api/p10/runtime-capture/jobs` | 在许可勾选与本次运行二次确认后创建 append-only official Runtime job；失败/中断不自动重试 |
| `GET` | `/api/p10/runtime-capture/jobs/{job_id}` | 读取异步进度、事件、path-free 精确失败码、终态和 completed execution 地址；刷新不重新提交 |
| `GET` | `/api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/candidate` | 从 completed job 解析四段 exact execution 地址，准备 P10.3c v2 candidate、current history 与短期只读图片会话 |
| `GET` | `.../visual-review-v2/candidates/{candidate}/cases/{case}/image/{png}` | 无会话时严格重验 current 后读取 PNG；页面短期会话只读取 candidate 已预热的精确字节 |
| `GET` | `.../visual-review-v2/candidates/{candidate}/history` | 读取 v2 连续 revision 和 head；不自动决定 |
| `GET` | `.../visual-review-v2/candidates/{candidate}/history/{revision}/{decision}` | 读取精确 v2 decision |
| `PUT` | `.../visual-review-v2/candidates/{candidate}/decisions` | 通过独立 v2 intent 与 CAS 追加覆盖全部 case 的人工 revision |
| `GET` | `/api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/admission` | P10.4a v2 自动重放 completed execution、current approved v2 head 与双 history 快照；零写入，release gate 保持 blocked |
| `GET` | `/api/p10/runtime-capture/jobs/{job_id}/visual-review-v2/safety-analysis-v2` | P10.4b v2 job-only 快速入口；只恢复 active run，否则返回 ready 以重新编译 current admission，不复用历史 terminal run |
| `POST` | `.../safety-analysis-v2/runs` | 以空 JSON 和独立 intent 创建/复用异步安全分析 run；CPU 编译在低优先级子进程执行，不接受客户端文件或 SHA |
| `GET` | `.../safety-analysis-v2/runs/{run_id}` | 查询 append-only run 的阶段、`continuous_boxes` 盒级心跳与有界进度；失败状态区分可重试与终止 |
| `GET` | `.../safety-analysis-v2/runs/{run_id}/result` | 返回九档幅度、连续段、claims、blocked release gate 与两份 path-free 内容地址回执；不返回完整 canonical 文档 |
| `GET` | `/api/projects/{id}/body-sway-runtime-captures/{preview}/{bundle}/{artifact}/visual-review/candidate` | 从精确四段地址只读编译 P10.3c candidate |
| `GET` | `.../visual-review/candidates/{candidate}/cases/{case}/image/{png}` | 读取 candidate 绑定且重新验真的 PNG |
| `GET` | `.../visual-review/candidates/{candidate}/history` | 读取连续 revision 和 head，不自动选择基线 |
| `GET` | `.../visual-review/candidates/{candidate}/history/{revision}/{decision}` | 读取精确 SHA 绑定的历史 decision |
| `PUT` | `.../visual-review/candidates/{candidate}/decisions` | 通过同源 intent 校验与 CAS 追加完整人工复核 revision |
| `GET` | `/api/projects/{id}/seam-anchor-reviews/{manifest}/{p3_rig}/{p3_bundle}/candidate` | 从精确三 SHA 静态链只读编译 P10.5b candidate |
| `GET` | `.../candidates/{candidate}/options/{option}/attachments/{attachment}/images/{png}` | 读取 option 绑定且重新验真的原始 attachment PNG |
| `GET` | `.../candidates/{candidate}/history` | 读取 seam review 连续 revision 和 head |
| `GET` | `.../candidates/{candidate}/history/{revision}/{decision}` | 读取精确 seam decision |
| `POST` | `.../candidates/{candidate}/decisions` | 通过同源 intent 校验与 CAS 追加六关系人工决定 |

API 响应带 `Cache-Control: no-store`。只接受 loopback Host；CORS 也只回显同 authority 的 loopback origin。分析工件端点会重新验证 strict JSON、内容地址和项目语义；损坏工件不会进入 UI。Motion-policy draft/package 端点都返回 path-free 内容，推荐项也只是确定性的界面起点，不授予审批权。草案晋级 POST 只接受完整 draft ID、封存的 manifest/proposal SHA、`explicit_confirmation=true` 和独立 intent；它执行准备前与同进程同项目锁内发布前的 current-chain 双快照，并把本服务内的 override 保存与晋级串行化。生成的只是正式 policy、Foot/Depth candidates 三文件 review package；这不是跨进程文件事务或发布后的第三次快照。Motion-policy preflight 虽使用 `POST` 承载有界原始 JSON 文本，但它零写入、不读取或返回本地路径、不创建 revision，也不发布或批准任何状态；请求还必须提供 `Content-Type: application/json` 与 `X-Autospine-Intent: motion-policy-preflight-v1`。外层请求上限为 48 MiB，内层 policy/foot/depth 原文分别限制为 1/16/16 MiB。

Motion-policy 草案晋级与最终 adoption 是两个独立写边界。前者只生成 current exact review package；后者只接受完整 package ID、严格 human review input 和 `X-Autospine-Intent: motion-policy-adoption-v1`，才会编译 decision/reviewed policy、发布 MotionInstance v2 bundle 并 exact verify。二者都不接受任意路径、shell 命令或客户端声明的上游地址，返回结果也不含本地路径。相同 canonical 输入按内容地址幂等复用；任一 draft/package 漂移、决定不完整、跨链错误或发布后 exact verify 失败都会拒绝成功。P10.5c seam publication 使用另一个 `reviewed-seam-anchor-set-publication-v1` intent，只接受已提交 current ready decision 的 package/candidate/revision/decision 身份，并在发布后 exact readback。HTTP 写操作因此包括 `PUT overrides`、Depth-policy 草案晋级、最终 P9 adoption、P10.1 idle/body-sway decision revision、精确 body-sway visual-review decision CAS、精确 seam-anchor review decision CAS 与 P10.5c 内容寻址发布。各 mutation 要求自己的 intent，并拒绝跨 authority origin。`/docs/<文件名>.md` 只读映射只允许仓库 `docs/` 目录内的 Markdown，不是写接口；功能入口中心不会直接导航到 `.md`，而是让安全文档查看器 fetch 该路由并按纯文本显示，不解析 HTML。

## 运行测试

完整 schema 测试需要可选的 `jsonschema`：

```powershell
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

P9/P10 独立复核页面使用零依赖 Node test runner；修改 `web/motion-policy-review.*`、`web/modules/motion-policy-*.js`、`web/body-sway-review.*` 或其他复核页面后还应运行：

```powershell
npm test --prefix web
```

真实 runtime capture 另有两个 opt-in smoke：不含官方 runtime 的 Chrome smoke 只检查进程与 PNG 通路；只有在提供已授权 `@esotericsoftware/spine-player@4.2.119` 并显式确认许可时，licensed smoke 才检查实际 runtime。缺少这些外部前置条件会跳过相应测试，不能用 stub 结果冒充官方 runtime 证据。

如需 Pillow/NumPy 图像比较加速，可安装 `python -m pip install -e ".[analysis]"`；不安装时仍有标准库 PNG 解码路径。

未安装 `jsonschema` 时，标准库运行与大部分测试仍可执行，完整 Draft 2020-12 实例校验会标记为 skipped。若仓库中存在两份真实 See-through audit，测试还会固定表示层差异和真实可见差异的区分：透明 RGB 与扁平背景造成的巨大 raw RGBA MAE 不会直接判为视觉失败；背景匹配后的可见颜色差异仍会失败。第 5 channel、空且隐藏图层、左右语义歧义与缺失部位仍需人工复核。

Resolved Project v1 的 Python 语义测试不依赖 `jsonschema`；可选依赖只决定 Draft 2020-12 实例测试是否执行。合同字段、公开 validator、r5/r7 历史回归和版本升级规则见 [Resolved Project v1 参考](docs/resolved-snapshot-reference.md)。

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

## 已完成的通用合同与结构能力：P0、P2 region RigIR 至 P9 reviewed motion，以及 P10.0–P10.7c setup regression 基础设施

P0 合同加固、P1 四肢候选与 P2 region-only RigIR 已贯通：`stage-scoped analysis → immutable geometry/candidates → candidate-bound revision → deterministic resolved snapshot → reviewed Layer Manifest → RigIR/setup bundle`。P2 没有提前引入 mesh：

P0 的 Resolved Project v1 已有独立 Draft 2020-12 Schema 与严格语义 validator。validator 会重算 snapshot SHA、候选 inventory/run identity、current/stale split provenance、实体交叉引用和全部 QA 列表；两个真实历史 revision 的既有哈希由回归测试固定，不因补充公开合同而改写。v1 的字段与解释已冻结，未来任何改变 resolved 生成或 QA/provenance 语义的算法升级都必须发布 `autospine.resolved-project/v2`，不能沿用 v1 token 或让旧决定静默获得新含义。

1. 从已复核 Layer Manifest 与 resolved joints 编译 region-only RigIR，固定规范骨角色、pivot、父子关系、slot 和 draw order。
2. 用独立 FK setup probe 重建每个 region 的 world transform，并与 audit 合成基线比较。
3. 对未知语义、缺失 pivot、非法父子关系或 draw order 歧义 fail closed，不用 bbox fallback 冒充人工确认。
4. bilateral split v1.2 会优先整块分配可靠的双连通域，融合层才回退像素最近规则；算法升级使旧决定 stale，三个真实决定均已重新目视批准。
5. 两份真实样本均以严格模式重复编译为相同内容地址；setup 精确重建，pivot/父子关系/draw order 与固定 visual golden 全部通过。

P2 验收证据：A 为 27 层/25 region，B 为 22 层/20 region；两者各 17 根骨骼，setup differing pixels/channels 均为 0、MAE 为 0。固定批准合同位于 `tests/goldens/p2-setup/`。

P3 在该精确 P2 基线上增加可独立验证的 alpha mesh 与参数化两骨 LBS；profile-v1 只把精确 `body.leg` region 视为 `thigh/calf` hinge：

1. 仅把通过 eligibility 合同的 alpha attachment 转为 mesh；分段手臂/腿语义在 v1 保持 rigid region，不满足条件的样本发布带原因和完整输入身份的 `reviewed-noop`，不伪造空 mesh。
2. 参数化权重绑定明确的 proximal/distal 骨，权重和、索引、三角形 winding、面积、setup 重建与有限数均有不变量测试。
3. 动作探针按方向搜索连续安全角，拒绝翻三角和明显裂缝，并发布 setup、最宽安全姿势和权重热图三类 PNG。
4. bundle 以 P3 rig SHA 与 bundle SHA 双重寻址；严格 reader 会重建全部上游/下游内容，并保证验证前后状态树完全不变。
5. 既有真实 golden 中，A 转换 2 个 `body.leg` hinge，共 739 顶点/1212 三角形，历史 B 稳定为 reviewed no-op。B revision 16 的合并袖臂另经 exact verify：它保留 `body.arm.upper → upper-arm.left` 绑定但按 rigid region 输出，新 P3 同样得到可信的 `reviewed-noop`；这不会把新地址冒充旧 golden。

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

P7a 已完成 Kimodo SOMA77 BVH 结构兼容 smoke：严格支持零包装 `Root` 下的 6DOF `Hips`，保留原始 BVH 内容地址，并通过三套 rig 的 P5/P6 bundle 门禁。测试输入是合成的 Kimodo-shaped fixture，不代表真实模型动作质量，也尚未进入官方 Spine Player 截图 golden。生成、映射、编译与限制见 [编译 Kimodo SOMA77 BVH](docs/how-to-compile-kimodo-bvh.md)。

正式 P7 合同与合成门禁已完成：严格的 Kimodo SOMA77 NPZ、独立 source sidecar 和显式 map 被编译为五文件内容寻址 MotionIR bundle；同一个合成 MotionIR 已通过三套不同 rig 的 P5 重定向和 P6 adapter/bundle reader。测试输入由标准库确定性生成，不是 Kimodo checkpoint 输出，也尚未进入该动作的官方 Spine Player 截图 golden。完整操作、失败边界和模板见 [编译 Kimodo SOMA77 NPZ](docs/how-to-compile-kimodo-npz.md)。

P8 相机感知投影与候选尺度门禁已完成：`CameraModel v1` 和 `ProjectedMotionIR v1` 保留逐段二维向量、L2/L3、深度余弦、root-relative depth、透视缩短比和 collapsed/observable 状态，并发布为精确重放 P7 的三文件不可变 bundle。legacy bridge 必须逐字节重建 P7 MotionIR；同一投影证据已经在三套不同目标 rig 上产生 setup-relative 长度候选，并再次通过 P5/P6，目标 profile 与 Spine 输出没有新增 scale timeline。P8 深度只作为证据，不决定前后遮挡；候选报告也不会自动成为动画。操作与边界见 [编译并复验 P8 投影证据](docs/how-to-compile-projected-motion.md)。

真实运行的 `wave-left-v1` 已通过六输入 intake，并按 exact 地址完成 P7/P8、A/B 目标 P5 与各自 P9 reviewed-motion bundle 的 reader 复验；唯一身份、P5 QA、正式 depth policy、候选身份和 P9 双 SHA 见 [Kimodo `wave-left-v1` Pilot Handoff](docs/pilots/kimodo-wave-left-v1.md)。这关闭的是单一输入、当前两个目标和当前候选集的结构链，不认证 checkpoint，也不替代广泛作品质量、seam 或官方 Runtime 门禁。

P9 reviewed motion 结构闭环已完成：foot-lock/depth-order evidence 与 candidate 不是决定；决定必须覆盖精确候选集，然后才能编译 reviewed policy、MotionInstance v2 与独立 Spine 4.2 v2 preview。复核页的 loopback-only Python preflight 覆盖 policy canonical identity、三份 standalone 合同、声明 SHA 重算、source/schedule 与 policy/depth 交叉绑定；其 `passed` 只准许页面显示候选，不授予人工或发布权限。一次明确 human adoption 才允许服务端按 package ID 重读证据、编译 decision/policy、发布固定六文件 inventory 并 exact verify；CLI 保留同一合同的专业复验路径。MotionInstance v1/P8 哈希保持不变；heading/scale 仍是 evidence-only，attachment switch 尚未实现。P9 成功只关闭 reviewed-motion 内容地址，不等于 seam、官方 runtime、raster truth 或真实作品质量通过。

P10.0/P10.1 已建立 candidate/decision 分离的 idle 行为合同；当前只有完整 canonical 躯干链可产生 `body_sway` candidate，眨眼、口型和头发仍明确保持不可观测或不支持。P10.2 会把人工给出的周期、四骨幅度和相位叠加到 exact MotionInstance v2，在固定离散 schedule 上检查 loop、FK、mesh、画布和共享索引，并把接缝与视觉质量保留为不可观测。报告只可能是 `structural_rejected` 或 `manual_visual_required`，release gate 始终 blocked。P10.2a 使用同一输入和 schedule 对 `0/8…8/8` 统一 gain 做零权威采样诊断；非零采样点即使通过，也只能产生要求新 P10.1 revision 的 `unvalidated_draft`。这两个阶段都不生成 MotionInstance v3 或 runtime timeline，也不证明连续时间、安全范围、接缝或视觉质量。

P10.3 的 package-centric v2 核心已交付：Preview v2、exact session/runner、固定 Spine Player 4.2.119/Chrome 环境校验、显式许可与单次运行确认、append-only 异步 job、official Runtime execution v2 内容寻址封存，以及自动进入 P10.3c v2 的 job-centric 四段地址。v2 candidate、history、decision 与 store 独立；43 case 由单时间轴呈现，只有人工最终提交才能形成 sampled visual decision，系统绝不自动批准。样本 A framing 已接受 revision 1；六次失败 execution 作为不可变 job 保留且没有部分 evidence，runner 1.1.0 的后续 job 已 completed，P10.3c revision 1 已由操作者以 43/43 approve 提交。v1 链冻结；无论 v1/v2，release gate 始终 blocked。

P10.4a 已增加 `BodySwayReviewAdmission v1`：从精确 P10/capture/visual 地址先后读取两次 authoritative history，并在中间重放精确 decision；旧 approved revision、reject/unobservable head、读取期间 head 漂移和任一跨链输入都会 fail closed。admission 只声明 sampled visual 已批准且 head 在编译时被观察，五项发布相关 claims 固定为 false；它不发布 MotionInstance v3，也不能在后续 revision 产生后继续冒充 current-head authority。

P10.4a v2 已增加独立 `BodySwayReviewAdmission v2` Schema、pure compiler、current consumer、job-centric compile/verify CLI、只读 GET 和普通用户页面。页面只接收 completed `job_id`，自动选择该 job 的 current v2 candidate/revision/decision；缺 ID 时不会猜 `latest`。编译器在两次 history 快照之间重放 exact decision、Preview v2、official execution 与 captures，reject/unobservable、head/source 漂移或交叉接线均 fail closed。成功只授予 compile-time safety-analysis admission；连续时间、safe range、reviewed seam、publishable timeline 与 release authority 仍为 false/blocked。

P10.4b v2 已增加独立的 amplitude-envelope/continuous-proof v2 Schema、job-only combined compiler、异步 HTTP run 与普通用户结果页。九个离散点与所有相邻时间段分为两条证据轨；`8/8` 是唯一具备 sampled visual review 的幅度点，连续证明只约束 Preview v2 结构模型。任何预算耗尽或不能闭合的段保持 `indeterminate`；页面不会把它显示为执行错误，也不会合成可发布安全范围。CPU 密集证明已隔离到可终止的低优先级子进程，盒级心跳和父端 staged-result 复验不改变证据 Schema/hash 或 strict replay；sealed JSON 数组表示与实际剩余共享盒预算另有回归覆盖。冻结 v1 的 P10.4b1/P10.4b2 字节与命令语义不变。

P10.4b1 已增加 `BodySwayAmplitudeEnvelopeCandidate v1`：只沿 reviewed amplitude vector 的统一 gain 射线生成九个 sampled structural probes，不构造四维独立幅度盒，也不假设单调性。reviewed gain 必须与 P10.2 stream/checks 和实际 sampled-linear preview keys 完全一致；命令在分析后再次按 `history → exact decision → history` 复核 head。所有范围、连续时间、视觉范围、seam、MotionInstance v3 与发布 claims 仍固定为 false。

P10.4b2 已增加 `BodySwayContinuousPreviewProof v1`：完整内嵌并重算 amplitude candidate、RigIR、target profile、MotionInstance v2、temporary preview manifest 与 preview projection，在统一 gain `λ∈[0,1]` 和全部相邻 preview tick 上执行有界区间证明。所有段通过时只开放两项 preview-model structural claims；预算耗尽、异常、非有限数或后端证明对象不一致均 fail closed 为 `indeterminate`。平台 libm/runtime 等价、raster 视觉范围、reviewed seam anchors、MotionInstance v3、可发布 timeline 与 release authority 仍固定为 false/blocked。

P10.5a 已增加 `SeamAnchorCandidates v1`：从精确 Layer Manifest/P3 静态链建立 torso-arm、pelvis-leg、leg-foot 左右六条关系，比较 setup alpha contact lobe，并生成可回看的 region/mesh attachment-local locator。候选与人工决定严格分离，generator `1.1.0` 的算法 profile SHA 会随实际行为常量变化；两份真实样本分别稳定得到 9 个/36 对与 2 个/8 对 candidate。human decision、reviewed anchor set、动态 seam、runtime/视觉质量和发布权仍固定为 false/blocked。

P10.5b 已增加 `SeamAnchorReviewDecision v1`：相同四段精确地址会重编 candidate，人工提交必须逐行绑定 relationship/option evidence SHA，并以 candidate SHA 隔离最多 64 项的不可变线性历史。页面已增加 setup-canvas 合成证据、确定性 advisory assist、自动 current-head 基线和一次最终确认；自动填充、高亮或 100% 草稿覆盖均不写 state。相同并发提交收敛到一个 revision，不同提交只有一个 CAS winner；历史 slot、content-address 文件、candidate 或 P3 任一篡改都会 fail closed。六行全部 accept/adjust 只得到 `reviewed_anchor_set_ready_for_compile`；package 模式可在同一次确认后继续 P10.5c publication/exact readback，但 release gate 始终 blocked。A 旧链 revision 2 仍可精确复验；revision 6 current 链另有 candidate `ea1c0211…`、decision `9db91b9a…`、review revision 1、`6/6 accept` 与 `24` 个 anchor pairs，二者不能混用。B revision 16 的 current candidate 只有两条关系可复核、四条 `unobservable`，仍无可发布 P10.5c。

P10.5c 已增加 `ReviewedSeamAnchorSet v1`：只有 current ready head 可被投影，set 固定六关系顺序、2–8 对 materialized anchors 和六项 source 身份，不重新选择 option 或生成 locator fallback。三文件 bundle 在写前重编并以 set/bundle 双 SHA 寻址；历史精确地址可复验但不拥有永久 current-head authority。A 旧链的 set `d801bdd2…`、bundle `66318839…` 保留历史价值；revision 6 current 链的 set `00de666e…`、bundle `e23e3792…` 已由 `verify-reviewed-seam-anchor-set` 精确复验，并绑定 Manifest `81bc00cb…` 与 P3 rig/bundle `309e4ef1…`/`92b398a8…`。它仍不证明动态 seam；`dynamic_seam_safety_unproven`、`runtime_equivalence_unproven` 与 `visual_seam_quality_unproven` 继续使 release gate 保持 blocked。

P10.5d 已增加 `BodySwayDynamicSeamProbe v1`：它完整重放 P10.4b2 与 P10.5c source closure，用 region 刚性投影或 mesh 重心/LBS 投影检查固定六关系的全部 reviewed anchor pairs，并以有界区间覆盖相邻 tick 与统一 gain。命令在 pure analysis 外再包一层 before/after current-head 检查，每次观察内部又执行视觉与接缝双快照；scope 只在 compile time 有效。只有上游结构证明和全部 seam segment 同时认证才开放 proximity 工程 claim；`dynamic_seam_safety`、边界连续、raster/视觉、runtime、timeline 与 release authority 始终为 false/blocked。

P10.6a 已增加 `BodySwayMotionConsumerAdmission v1`：只有认证的 P10.5d probe 可以进入，source 内嵌其完整 canonical 文档，并重新绑定/复验精确 P9 MotionInstance v2 六文件 bundle。pure core 选定 reviewed unit gain，把 sampled-linear rotation keys 与 MIv2 原有 root translation、markers、stepped draw order 组织为版本中立 setup-local motion domain；seal 在前后两次 current-head observation 完全一致后才开放 `setup_local_timeline_compilation_admitted`。所有 observation scope 仅为 `compile_time`；该 admission 本身不发出 MotionInstance v3、Spine adapter 或发布权。

P10.6a v2 在独立 format/profile/hash domain 中重建相同窄能力，并把上游改为精确 P10.5d v2 bundle。public CLI 只收项目和 probe/bundle 双 SHA；reader 复验固定三文件 inventory 后，从 source closure 自动读取精确 P9。source 继续绑定 Manifest/P3/target/timing/Preview v2，detached validator 从两份 exact bundle 重编 core；任一跨线、篡改或 head 漂移均 fail closed。v2 不改变 MotionInstance payload 语义，也不授予 overlap、完整边界、raster/视觉、Runtime、timeline 或 release authority。

P10.6b v1/v2 均已增加严格 `MotionInstance v3` Schema、pure compiler、三文件内容寻址 bundle、原子 store、exact reader，以及版本匹配的 compile/verify CLI。v2 prepared pipeline 自动从 reader-issued P10.5d/P9 生成并 detached-replay P10.6a v2；公开命令和 store 都在待发布值构造前后重新观察 current heads，任何 identity/bytes 漂移均零发布，成功写入后按精确地址读回。payload 保持 format v3，v1/v2 admission、source、bundle/run 地址域互不混用。run 只授予 `motion_instance_v3_emitted`，其余 Spine adapter、attachment overlap/完整边界、raster/视觉、官方 Runtime、永久 head authority、publishable timeline 与 release authority 均为 false/blocked；历史 verify 不观察 current heads。

P10.7a v1/v2 均已增加版本匹配的 Spine 4.2 adapter v3 capability、MIv3→P9→P5/P3 完整精确重放、五文件内容寻址 bundle、current-head 门禁、原子 store、exact reader 与 compile/verify CLI。v2 另有无项目/文件/SHA 的自动页面，并以独立 source contract、skeleton hash、run/report 与 `spine42-v3-v2` 地址域隔离；旧 P6 和冻结 v1 profile/adapter/golden 哈希不变。run 唯一授予 `spine_adapter_emitted`，其余 overlap、动态接缝、完整边界、官方 Runtime、Runtime 等价、raster、永久 head、publishable timeline 与 release 均为 false/blocked。

P10.7b v1 已增加固定 runtime/capture profile、确定性 case plan、官方 Spine Player/浏览器精确身份封存、opaque/transparent composite 与完整 setup attachment isolate 捕获、sampled alpha/raster 指标、不可变 capture store/exact reader，以及 candidate/人工 decision 分离的四个 CLI。它的 source/session 与输出哈希均已冻结为 v1，不能消费 v2。P10.7b v2 已交付只读 source bridge、严格 session set、bounded collector、loopback server、内存 harness、Windows real browser runner，以及 `captured_unreviewed` evidence/bundle/store/exact reader；版本/地址交叉绑定、显式许可真值、P10.7a v2 单次 exact read、固定 Runtime/浏览器 lease、逐 artifact 全新 profile、固定五份 JSON 加 PNG captures、独立 namespace/hash domain、原子发布和四段显式地址均 fail closed。guarded v2 Runtime 授权、manager、执行与 HTTP API 已提交；当前尚无 v2 raster metrics、人工复核或发布权；机制测试没有真正启动经授权的官方 Runtime。官方 Runtime 始终是需明确授权的外部边界；后续产品工作按自动化路线推进。

P10.7b-readiness 已增加 strict canonical request 与 exact-address、zero-write 审计 CLI。它只重放请求明确声明的 Manifest/P3 和后续地址，并报告 P3 seam、P9、P10.5c、P10.6b、P10.7a、runtime capture、raster review 与 P6 setup comparison 八个 checkpoint。v1 已冻结且第八项仍固定为 missing；独立 P10.7c 命令不会改变其 Schema、哈希或报告含义。当前示例未声明两个项目的 P9 地址；A 也未声明 P10.5c 地址，B 的精确 P3 candidate 则证明左右 pelvis-leg/leg-foot 四关系不可观测。任何 readiness 结果都不授予 publish/release authority。

P10.7c 已增加 strict canonical setup-regression request/report、冻结 comparison profile、P6 批准合同精确字节绑定、P6/P10.7a 同 P3 与 atlas/texture 来源闭合、P10.7b setup capture 只读提取、RGBA 指标，以及由 exact evidence 在函数内部重新计算 sample 的 replay binding。该能力已交付不等于真实双样本通过：共享的 `wave-left-v1` 已到达 P7/P8、A/B P5 与各自 exact replay 通过的 P9；仍须关闭 seam 并提供 P10.7a 与官方 capture 地址，之后才能运行对应真实请求。当前只能验证机制与既有 P6 基线，没有真实 P10.7c 通过结论。临时报告尚不是 readiness admission；readiness v2 前必须增加可寻址、不可变且可重放的 comparison bundle。

姿态 runner 与真实标注评估集仍是独立质量轨，不阻塞版本中立 P2 编译；诊断 setup prior 不能替代真实模型基线。

面部锚点、头发弹簧和实时追踪映射可以作为独立模块接到同一规范骨角色上；四肢扩展的关键不是增加更多屏幕坐标映射，而是建立 bind pose、父子骨、权重和重定向空间。

## 非目标与已知边界

当前版本不负责：

- 运行 See-through 推理、选择 seed、编辑 PSD 或自动清理图层；
- 下载或运行具体姿态模型；`import-pose` 只转换经过哈希固定且已还原到原画布的 COCO17 输出；
- 自动解决 `head-obj`、`objects`、合并肢体等歧义语义；
- 证明遮挡补全符合解剖或在大幅动作下不会露馅；
- 自动生成自由形变 deform 或运行时 IK constraint；动态 draw order 只来自 P9 人工批准的 slot-pair policy，不做 raster-truth 推断；
- 无人复核地把 Kimodo heading、depth、scale 或 attachment switch 写入 runtime；P9 的辅助规则只覆盖 `state=candidate`、证据完整有限且两项指标不超过合同上限 80% 的 Foot candidates，Depth、`rejected_*`、缺证、非有限值与超阈值项仍须人工处理，heading/scale 仍是 evidence-only；
- 把 package 自动选择、motion-policy preflight 的 `passed`、辅助 Foot 草稿、Python canonical SHA 或 candidate inventory 计数当成最终 human adoption、成功 adoption 响应中的 exact verified P9 地址或 release authority；
- 把合成 P7 门禁当作真实 Kimodo checkpoint、真实动作质量或该 clip 的官方 Spine Player 截图验收；
- 把 loader-isomorphic audit 当作官方 runtime 或 raster truth；P9 动态官方 runtime screenshot 与真实 Kimodo reviewed asset 门禁仍需单独关闭；
- 把 P10 `completed_diagnostic`、离散结构采样通过、sampled still 全部批准、review 输入的 0–10 度语法包络或 P10.4b2 preview-model 区间证明当成 MotionInstance v3、runtime 等价、可发布 Spine timeline、接缝安全或人工视觉安全范围；
- 把 P10.5a 静态候选、contact overlap 或 locator evidence 当成人工决定、reviewed seam anchor set 或动态动作域接缝安全；
- 把 P10.5b 的 advisory highlight、自动填充草稿、自动 current-head 基线或页面显示 6/6 当成人工 revision 或 P10.5c 凭据；
- 把 P10.5c 的静态 ReviewedSeamAnchorSet、历史 bundle 可复验或 compile-time current-head 观察当成永久审批权、动态 seam 证明、runtime/视觉质量或发布许可；
- 把 P10.5d 的 `4 px²` reviewed-anchor point 代理、`compiled` 命令状态或保存的 stdout 当成完整 attachment 边界连续、raster/视觉接缝通过、runtime 等价、永久 current-head authority 或发布许可；
- 把 P10.6a v1/v2 的 setup-local timeline compilation admission 当成 MotionInstance v3/Spine adapter 已发出、完整边界或 raster 视觉通过、runtime 等价、永久 head authority、publishable timeline 或 release authority；
- 把 P10.6b 的 MotionInstance v3、历史 bundle 可重放或发布前 head 双观察当成 Spine adapter 已编译、官方 runtime/raster 通过、永久 head authority、publishable Spine timeline 或 release authority；
- 把 P10.7a adapter、P10.7b sampled capture/指标或一次人工 decision 当成连续时间 raster 安全、永久审批、可发布 timeline 或 release authority；
- 把冻结的 P10.7b-readiness v1 报告当成外部阶段执行记录、current review head 发现、人工决定、P10.7c setup golden 对照或发布授权；
- 把 P10.7c 单帧 setup RGBA 对照当成动画 case 人审、连续时间 raster 安全、真实双样本已验收或发布授权；
- 在未提供并确认授权的官方 Spine 4.2.119 runtime 时，用 test-only player stub、进程 smoke 或任意相邻截图冒充真实 capture；
- 生成眨眼/口型素材、实时追踪映射或运行时物理；
- 捆绑或再分发官方 Spine runtime、判断任意未知 Spine 版本、生成 Spine Editor 工程，或覆盖固定 P6 profile 之外的特性；
- 代替输入素材、训练数据或模型权重的许可证与商业使用审查；
- 多用户权限、远程协作或生产部署。

这些边界并非都应一次性并入当前阶段。历史 `wave-left-v1` 的六输入审计、P7/P8、A/B 旧 P5、P9 发布与 exact verify 都已完成；P10.2/P10.2a、动态视口和 region 换绑候选也已交付。A 已确认动作证据换绑并保存 override revision 6，current P9/P10.2、CaptureFraming、P10.3c v2 和 P10.5b/P10.5c 静态接缝均已闭合；B revision 16 必须沿自己的 current chain 继续。P10.4a/P10.4b v2、P10.5d v2 自动入口、P10.6a/P10.6b v2、P10.7a v2 adapter/automatic UI，以及 P10.7b v2 source/session/runner/evidence/store/exact-reader 机制均已交付，但真实 A 尚未因此自动获得 P10.5d–P10.7a v2 凭据，机制测试也没有真正启动经授权的官方 Runtime。guarded v2 Runtime 授权、manager、执行与 HTTP API 已提交。项目级 region 预览、异步工作台入口和结构异常队列已交付，后续按自动化路线推进语义/关节、通用 Mesh/Weight 与动作质量；真实 Runtime/raster 和人工视觉仍需独立验证。overlap、完整边界、raster、Runtime 等价和 release 仍 blocked。完整计划见[后续开发路线](docs/development-roadmap.md)。

项目中显示的骨架来自 bbox/语义启发式，`requires_review=true`。只有在语义、左右、pivot、层级、合成回归和动作探针均通过后，才能把人工确认结果交给后续 RigIR/导出阶段。

代码职责、依赖方向、文件长度预算和阶段完成门禁见 [docs/architecture.md](docs/architecture.md)。
