# AutoSpine Workbench 架构与质量门禁

R3-S官方帧缓冲捕获使用独立 `capture-sleeve-runtime.mjs` / `sleeve-framebuffer.js`，由外置spine-webgl执行解析、FK和渲染。报告严格区分探针覆盖、自重叠与发布权，Python复核器核对来源及图像摘要；不修改历史候选。

`cloth_interface_root.py`消费exact helper、服装权重、候选和草稿，提取cloth↔sleeve/cuff共享边；连通性与边长根部测量分离，多段交界不采用统一根部。单段试验只重算helper本地坐标和FK，权重数值/网格不变，以129点全轨回归决定候选保留。新`sleeve-interface-root/v1`单独寻址。

`cloth_root_transition.py`使用三角邻接Dijkstra距离生成helper保留比例，并将根部剩余权重给forearm。独立helper profile重跑完整分支FK门禁，失败则同时回退权重/轨道并重算setup与隔离误差；旧helper profile输出保持不变。

`sleeve_helpers.py`使用parent驱动的分支FK构造`sleeve-helper/v1`，避免串行链求值错误地让手骨驱动其同级服装骨。独立保存候选helper与重新计算的local权重，不修改正式骨架。均匀角度129点QA、33点固定预览和手旋转隔离误差分别记录，尚无正式Runtime或物理Bake。

`sleeve_boundary.py`仅生成固定64轮邻接图手骨保留系数；调用者`sleeve_weights.py`在独立可选profile下以129点/轨道比较内部权重候选与平滑候选。手与unknown固定、服装内部和混合边界分别处理，整区域回退。未修改既有默认profile输出，也不授予发布权。

`asset/planning/sleeve_regions.py`生成腕带几何提示与初始unknown三角归属，严格验证返回草稿的来源、清单、类别和预填来源；`sleeve_region_review.py`校验源PNG后嵌入独立`sleeve-region-review.js`编辑器。候选/草稿分别寻址，不修改旧Mesh合同或权重。像素归属与服装语义仍须单独验证。

袖子不能仅按整层三骨链建模：[通用袖子方案](sleeve-rigging-plan.md)定义袖段/袖口/手/垂布的不同驱动。当前新增的`component_axial_solver.py`与`component_axial_correction.py`只提供独立局部几何实验及129点逐关键姿态门禁，历史圆形solver、权重、UV和拓扑不变；`component-axial-correction/v1`引用精确回退候选与骨架，不授予服装语义或生产权。

`asset/planning/component_distal_guard.py` 是独立的整区域候选组合核心：校验新旧权重、修正、骨架的内容地址和区域/轨道/几何清单，重算129点FK，不信任旧QA统计。每个区域只能选择完整的新权重+新修正或旧权重+旧修正，不能逐帧切权重。`component-distal-guard/v1` 经16MiB内容寻址store读回；不进入生产授权，不修改历史profile。

中央布局由独立 `workbench-layout.js` 管理，仅重新挂载已有表单与队列，保留控制器、草稿和 API 身份。
规划响应的 `rig-plan-readiness/v1` 是独立 profile 的来源绑定诊断，不修改历史 RigPlan 工件或绑定决定。

## 主工作台动画候选编排

`automation/animated_inputs.py` 登记精确来源与作者 checkpoint，`animated_input_index.py` 提供快速可调度状态，
`animated_joint_review.py` 保存明确的辅助关节复核并重建骨架/绑定候选。快速索引不代表 QA 通过；新构建仍完整重放来源。
`animated_compile.py`、`animated_partitions.py`、`animated_motion.py` 与 `targets/spine43/workbench_preview.py` 分别负责
网格候选、区域扩展、15°/30°有限动作和目标编码。`animated_package.py` 保存纹理、QA 与 CPU 采样，
`animated_store.py` 隔离大体积文件和小型任务日志；`animated_run.py` 的独立身份不改变历史 region PipelineRun。
Application、jobs、routes 和 Web 小模块提供异步构建、取消、复核续跑及可验证下载。

作者编辑或源图像变化使登记失效。主页面提供显式“同步已保存校正并重建”：将已保存的同名关节增量迁移到辅助标注，新 v2 登记保存作者修订和前序来源，v1 历史不变；不支持的图层编辑仍阻塞。几何变化后的旧 bind 只作为迁移建议，不能批准新骨架。
新包保留 `authority:none`、`production_authorized:false`；CPU 诊断播放和另行运行的官方 Runtime 证据分开记录。
普通操作见[动画候选指南](how-to-build-animated-spine-preview.md)。新增模块优先不超过 300 行、硬上限 400 行；历史单体 ratchet 不扩大。

## 已有独立编译与诊断模块

`targets/spine43/merge_limb_tracks.py`纯合并显式附件与轨道；benchmark集成CLI精确重放历史Bake、
按ownership显式归属排列slots并检查原有121帧坐标不变。新包独立身份，不覆盖旧候选或复核决定。

`targets/spine43/mixed_character.py`纯组合已选刚性四边形与既有分区；benchmark CLI负责精确来源、
2px透明padding纹理页、同骨架setup重建、内容寻址和确定性ZIP。缺项与原接缝证据不因组合自动通过。

`benchmark/character_context_*`独立处理原图上下文和候选分区的显示：atlas显式映射替换源层、
同骨架setup校验、源顺序叠加。复用现有WebGL网格绘制器，静态层不获得动画绑定权。

`targets/spine43/seam_roi_context.py`仅分析原／候选alpha栅格，benchmark CLI负责PNG身份、坐标方向、精确回放和SVG标记。
4／8邻接敏感性与全角色拓扑分开；不把局部裁剪边缘连通直接解释为外轮廓或生产通过。

`benchmark/seam_boundary_probes/comparison`负责reference独立采样及Runtime对照精确reader，
复用数值归约核心但用独立来源、schema和coverage；集合入口只在候选身份匹配后展示补充结果。

`benchmark/seam_candidate_hub*`以逐关系exact reader校验已有候选集合，将文件字节冻结到只读HTTP白名单，
复用外部官方Runtime播放器并确定性重建下载ZIP；UI独立模块不扩展历史播放器或生产授权。
启动配置不是资产身份，候选身份及未评估覆盖仍来自原报告，见[入口说明](how-to-seam-candidate-hub.md)。

`targets/spine43/ownership_preview.py`提供隔离纹理页的独立诊断Adapter：整页UV→region UV、加权坐标反射、Editor图片。
对应CLI精确回放来源；`tools/ownership-runtime*`加载外部官方Runtime，固定时刻对照单纹理与共享页。
测试证据独立保存，不改写旧导出回执的Runtime状态；诊断profile不扩展正式生产准入。

`ownership_atlas.py`把ownership像素编译到隔离纹理区域并映射整页UV，CLI负责来源精确重建与确定性ZIP。
源分区、geometry和weights不变；页面UV与Spine附件region UV必须显式转换，不允许直接混用。
当前采样证据仅覆盖linear无mipmap，详见[工作流](how-to-ownership-atlas.md)。

`shared_partitions.py`提供源纹理、ownership和区域权重的纯组合校验，
`shared_partition_cli/view`提供精确重建、确定性包和复核页。旧分区、骨架与权重身份不变。
共享源图UV不自带遮罩能力，目标Adapter必须先证明采样隔离，详见[工作流](how-to-shared-partitions.md)。

`asset/joints/distal_width.py` 测量局部alpha横向支撑并重新分配远端权重；独立CLI保存全部预设策略，
通过精确来源重建验证结果。顶点、骨架与旧profile不变，不写批准决定，见[工作流](how-to-distal-width.md)。

`asset/joints/distal_grid.py` 是独立的远端横纵支撑线实验，复用主组件、alpha覆盖与拓扑门禁。
`benchmark/distal_grid_cli.py` 通过精确来源闭包重建旧网格，再生成加密网格和同预算corrective对照；
报告使用现有16MiB存储，CLI独立运行以避免继续扩大主入口。旧profile与已批准绑定不变，
失败实验不进入RigIR或目标Adapter，详见[工作流](how-to-distal-grid.md)。

`joint_plane_weights.py`、`mesh_refinement.py` 新增独立权重过渡与来源绑定结果，
`mesh_refinement_cli/view` 负责精确回放和变形网格对照。原距离权重和网格编译器不变。

`asset/joints/mesh_candidate.py` 组合既有alpha grid与新 `mesh_weights.py` 三骨LBS实验算法。
CLI/view/store分模块，mesh_storage限定16MiB并重用安全路径验证，旧128KiB报告读写不变。
QA失败保留候选几何且status blocked，不写生产RigIR。

`asset/joints/chain_coverage.py` 独立实现4连通RLE/并查集及骨段alpha采样，
不改既有8连通AlphaGeometry；CLI重放v2绑定源，view标识草稿选择但不改变测量身份。

`asset/joints/layer_binding.py` 为独立v2候选，复用v1刚性计算而不修改旧合同。
`benchmark/layer_binding_{draft,cli,controls,view}.py` 分别负责草稿、源闭包、编辑及骨链叠图。
选项mode区分rigid/mesh_chain，草稿只保存option_id；多骨选项不包含伪造的setup权重。

`benchmark/region_binding_draft.py` 验证独立草稿合同，controls模块提供内嵌浏览器编辑和恢复校验。
region binding CLI新增草稿读写，保持原候选文档内容不变；真实源重放仍在写入前执行。

`asset/joints/region_binding.py` 生成独立保守region绑定选项，单语义建议与成对骨选项都保持待复核。
`benchmark/region_binding_cli.py` 重放骨架及全部上游源；view只呈现图层位置与选项。
新profile不改旧RigIR，source traversal仅用于列表顺序，不作为Spine draw order。

`asset/joints/reviewed_skeleton.py` 从辅助复核坐标构建独立 `assisted-canonical-v1` 候选。
`benchmark/assisted_skeleton_cli.py` 重放标注、Pose、基线和素材闭包，view模块只读叠图。
不伪造 JointOptimization 输入或修改旧骨架编译器；中央点原样保留，末端延伸显式追踪。

`assisted_joint_draft.py` 与 `assisted_joint_cli.py` 单独保存模型辅助标注和源闭包，
复用 `joint_view.py` 的画布拖动及批量编辑。普通草稿v1不增加字段，辅助envelope不能静默降级成独立GT。

R2-B Reference的纯合同与CLI位于 `joint_reference*.py`，保留显式独立标注声明、
原草稿和请求，scope仅benchmark。`pose_accuracy.py` 只做共同参考点数值分析；
`pose_accuracy_cli.py` 重放完整源闭包，`pose_accuracy_view.py` 只读呈现缺GT与覆盖率。
旧草稿、生产权威和候选来源不改变。

真实 Pose 入口独立位于 `runners/pose`：固定模型profile、惰性加载ONNX的producer、
数值codec、WholeBody→COCO适配和原始张量exact reader分别成小模块。
CLI在隔离venv执行，按Benchmark解析真实ID；推理张量、规范观测和优化候选分别寻址。
原始非概率分数保留，区间编码策略显式记录；未知visibility不升级为可见。
详见 [R2-B 输入与边界](how-to-real-pose.md)。

PSD 局部语义候选在 `benchmark/semantic_candidates.py` 中按固定名称规则纯生成，
`semantic_cli.py` 核验真实 audit/图层文件并封存输入闭包，`semantic_draft.py` 与
`semantic_view.py` 分别约束未批准标注和离线显示，不修改旧 Layer Manifest 语义。

`annotation_cli.py` 复用语义输入闭包，分别存储 joint-drafts 和 semantic-decisions。
关节草稿与语义决定各自绑定原候选；语义决定还绑定明确的草稿和人工请求，
不将未标注、不可观测或未决定项转换为生产许可。

Benchmark 映射候选在独立 `benchmark/mapping.py` 中计算和验证；文件核验、CLI 与
离线页面分别位于 `mapping_cli.py`、`mapping_view.py`。它绑定原图、PSD、冻结数据集和
合成证据，复用不可变报告 store。坐标草稿无批准权，不进入旧 Resolved/P9/P10 身份闭包。

锚点输入与校准报告使用独立合同。`mapping_anchors.py` 负责纯拟合和重算验证，
`mapping_calibration_store.py` 重放其原始候选/锚点闭包，页面录点和误差展示各自分模块。

映射复核请求与决定独立于原候选。`mapping_decision.py` 纯编译显式请求，
CLI 先验证源文件并要求操作者确认，store reader 重放候选/请求后才能生成 pending 标注模板。
没有隐式 current 或撤销推断，不跨越 Benchmark 进入历史生产授权域。

2026-09 自动化转向见 [当前状态](current-state-2026-09.md)。[Pipeline Profile v1](adr-pipeline-profiles-v1.md) 已接入独立的 [PipelineRun region 预览执行器](adr/pipeline-run-v1.md)；其运行记录、预览输出和历史认证内容地址保持独立。

本文约束的是持续开发方式，不是一次性重写计划。任何新功能都先进入版本中立合同和可复现工件，再接 UI 或特定 Spine 版本适配器。

## 不变量

- PSD、See-through audit 和导出的 PNG 是不可变输入；工作台只写自己的 state、analysis 和 build 目录。
- 每个自动分析结果记录输入哈希、算法版本、配置和产物哈希。HTTP 请求只读取已完成工件，不在线运行重型分析。
- 人工决定与模型证据分开保存。人工可以接受、调整或拒绝候选，但不能改写模型置信度。
- setup pose 先通过 region attachment 验证。只有 region 无法满足连续弯曲时才引入 mesh、weight 和 deform。
- RigIR 是版本中立边界。目标 Spine 版本只存在于 adapter 内；未知 attachment、constraint 或 timeline 必须明确失败。
- 保存使用 optimistic concurrency；每个成功 revision 都可追溯，不覆盖历史证据。

## 模块边界

依赖方向保持单向：

```text
contracts / value objects
        ↓
audit repository ── analysis artifacts ── override history
        └───────────────┬──────────────────┘
                        ↓
       resolved project snapshot v1
           + strict semantic validator
                        ↓
             manifest / RigIR compilers
                        ↓
        semantic validators / probe runners
                        ↓
              target-version adapters

builtin | BVH + map | Kimodo NPZ + sidecar + map
                         ↓
             source-specific strict compiler
                         ↓
                       MotionIR
                         ↓
                 P5 retarget → P6 adapter

verified Kimodo P7 + explicit CameraModel
                         ↓
       target-independent ProjectedMotionIR evidence
                  ┌──────┴──────┐
                  ↓             ↓
        exact legacy bridge   target-rig candidates
                  ↓             ↓
           unchanged P5/P6   reviewed P9 policy
                                      ↓
                        MotionInstance v2 → Spine v2 preview
                                      ↓
                         six-document reviewed bundle

exact Layer Manifest + exact P3/P5/P9 reviewed chain
                                      ↓
                         P10.0 idle candidates
                                      ↓
                         P10.1 human decision
                                      ↓ adjust + pending_probe
       P10.2 report + P10.2a zero-authority gain diagnostics
                    ├── no non-zero passing draft ──→ repair upstream structure
                    ├── non-zero passing draft ──→ explicit new P10.1 revision
                    │                                      ↓ rerun P10.2
                    └── canvas-only ──→ CaptureFraming human revision
                                      ↓ current accept / adjust
                    package-centric Preview v2 + exact session
                                      ↓ explicit license + run confirmation
                 append-only async official Runtime execution job
                                      ↓ completed job_id → exact four-part address
                     P10.3c v2 human case decisions
                                      ↓ completed job_id
                 P10.4a v2 compile-time admission
                                      ↓ job-only replay
                 P10.4b v2 amplitude + continuous proof
                                      ↓ next: current-chain seam
                           blocked release

exact Layer Manifest + exact P3 static bundle
                                      ↓
                P10.5a static seam candidates
                                      ↓
          P10.5b decision → P10.5c reviewed set
                                      ↓
            P10.5d v1/v2 dynamic seam evidence
                                       ↓
          P10.6a version-isolated consumer admission
                                        ↓
        P10.6b version-matched MotionInstance v3 bundle
                                       ↓
        P10.7a version-matched Spine 4.2 v3 bundle
                                       ↓
 P10.7b v2 runtime source + runner + evidence store（已交付）
                                       ↓
                  guarded automatic authorization（4254151 已交付）
                                       ↓
                    [external] Runtime/raster gate
                                       ↓
       exact-address, zero-write readiness v1 audit
                (frozen; checkpoint 8 remains missing)
                                       │
P6 approved golden + exact P10.7a/P10.7b capture
                                       ↓
          P10.7c zero-write setup regression
                                       ↓
                            blocked release

server → application services only
web    → HTTP contracts only
```

- `project_store.py` 只保留发现项目和协调 application service 的 façade 职责，不再承载分析算法、持久化实现或 Rig 编译。
- Resolved Project v1 的 builder 与 public validator 分离：builder 保持历史字节，validator 独立重算 canonical SHA、实体/候选/拆分 provenance 和派生 QA；Project API 输出、Layer Manifest 构建与 region RigIR 编译共用这个 validator。candidate/split 原始 artifact 的字节重放仍由已有 binder 负责，避免 resolved validator 反向读取外部目录。
- `server.py` 负责 HTTP、输入大小、loopback 安全和错误映射，不实现领域规则。
- 前端分为 API、authoring state、保存事务和各 stage view；view state 不得污染 revision draft。P9 页面可以读取本地文件与承载人工表单，但不得自行成为 canonical identity 或完整合同 validator 的权威。
- 外部姿态模型只能通过 canonical pose observations 进入；alpha 几何只读取 resolved layer 与固定 PNG，融合结果必须保留原始 pose 和未标定分数语义。
- COCO17 raw 输入、adapter、canonical pose、人工评估和候选工件分开内容寻址；坐标反镜像、左右标签交换、视角和镜像声明不得合并成一个隐式开关。
- 离线命令按 stage 边界拆分：P1 输入/候选、P2 manifest/RigIR、P3 mesh、P4 IK、P5 MotionIR、P6 目标版本 adapter、P7 Kimodo source adapter、P8 camera/projected evidence、P9 reviewed motion/bundle，以及 P10 idle probe/`compile-body-sway-preview`/runtime capture/visual review/review admission 分别拥有显式入口；命令之间只传递精确内容地址，不解析 `latest`。
- P9 草案准备是独立的非权威边界。`prepare-motion-policy-review-draft` 只读并交叉验证显式 P3/P4/P5/P7/P8 双 SHA，然后在一个新 namespace 中原子发布 Kimodo evidence、standalone Foot candidate 和 `pending_human_review` Depth proposal。该 inventory 故意不包含正式 `depth-pair-policy.json`、Depth candidates、decision 或 adoption；package 发现器不得把它升级为可采用 P9 package，也不得从旧 namespace 复制人工权威。CLI 回执不暴露 state-root 下的本机目录。
- P9 UI 的读取与采纳边界分离。`POST /api/motion-policy/preflight` 仍是 zero-write Python application service：既有文件请求携带 `File.text()` 原文字符串，不先经 JavaScript parse/stringify；proposal 投影出的正式 policy 只序列化一次。`policy_identity` 对完整正式 policy 运行 inner strict decoder、validator 与 canonical SHA，`candidate_inventory` 对 standalone report 或正常 CLI envelope 解包后重算 policy/foot/depth 三 SHA、完整 candidate inventory 及 source/schedule/policy 交叉绑定，并把排序后 candidate ID 字符串清单的 canonical SHA 返回页面。页面只在身份、计数和该清单摘要全部一致时渲染表单。
- 一次最终 human adoption 通过 `POST /api/motion-policy/review-packages/{package_id}/adoptions` 进入写边界，并要求 `X-Autospine-Intent: motion-policy-adoption-v1`。Application service 只接受完整 package ID 与严格四字段 review input；它重新加载 exact package，不接受任意文件路径、shell 命令、客户端 P3/P5 地址或候选文档，随后复用既有 decision/policy compiler、ReviewedMotionBundleStore 与 exact reader。发布是内容寻址且可幂等复用；成功响应 path-free，并同时证明刚返回的 P9 双 SHA 已读回复验。HTTP adapter 继续负责 loopback/same-origin、JSON、大小、intent 与错误映射。下载 review input 只是备份，不参与服务端 authority；P9 adoption 也不授予 seam、Runtime、raster 或 release authority。
- P9/P10 current authoring gate 把“快照不可重建”和“两个完整快照实际不同”建模为独立异常。ProjectStore、OSError、split materialization 或 Layer Manifest 构建失败统一 fail closed 为 path-free 500 unavailable；只有成功取得的 before/after inventory 不同才成为 409 changed。写路由在 unavailable/changed 两类结果下都不进入 mutation，读路由也不返回混合时点 inventory。
- P9→P10.5b 使用只读 `GET /api/motion-policy/review-packages/{package_id}/seam-review-entry`。Application service 从 package ID 重新加载 Foot/Depth exact package，验证共享 P3 来源，再由 VerifiedMeshBundleReader 重放 P3，并准备固定六关系 Seam candidate；客户端不能提交 Manifest/P3 SHA。响应只含 path-free 地址、candidate 身份、摘要和 blocker。handoff 本身不写 revision、不选择 locator；页面随后从独立 candidate/history 资源加载精确证据、自动绑定 current head，并把服务端 advisory assist 投影为可撤销草稿。手工四段地址只保留为专业审计 fallback。
- P10.0–P10.2a 共享 exact-chain loader 只读取七个完整 SHA 所选的 Layer Manifest/P3/P5/P9 工件。Candidate、人工 review、decision、probe report 和 P10.2a 诊断候选保持独立；普通 P10.0–P10.1 service 只把已采用 P9 bundle 作为待 exact replay 的 entry，并在最后显式确认时把标准 decision 追加到 candidate-bound CAS history；浏览器不提交上游地址或 `human` 字段。P10.2a 的统一 gain 与动态视口都只输出零权威诊断；只有独立 CaptureFraming `accept/adjust` revision 可以进入 Preview v2。所有进程内缓存都只保存可重建结果，命中仍执行 exact replay/current-head 检查，不落盘、不授予 authority。
- P10.3 v2 以 package 为普通用户入口。Preflight 从 current package 重放 P10.1、P10.2、CaptureFraming、world viewport、Preview v2、projection、plan 和 source，再校验固定 Spine Player 4.2.119 JS/CSS/package/LICENSE 与 Chrome。浏览器只提交服务端给出的 current identities、显式许可确认和本次运行确认；不提交文件路径或自选 SHA。
- capture job request 和事件链 append-only 保存。状态查询可跨页面刷新恢复；失败和进程/服务中断都不会自动重试，当前没有用户主动取消 API。execution v2 runner `1.1.0` 只有在 exact session 与环境 snapshot 一致时才捕获，以 `page_lifetime=collector-terminal` 等待 exact callback 提交；它不使用冻结 v1 的 `--dump-dom`/`--virtual-time-budget`。collector 同时校验 v1 或 v2 session 而不改变冻结 v1 字节。成功结果以 project/Preview v2/execution bundle/artifact set 四段地址发布，partial output 不进入正式 execution；失败事件保存 path-free 精确 failure code。
- P10.3c v2 HTTP/UI 以 completed `job_id` 为外部地址。服务端从不可变 job 解析内部四段地址，重放 execution 并双检查 current P10.1/CaptureFraming；candidate、history、decision 与 store 使用独立 v2 namespace。读取零写入，只有覆盖完整 cases、通过 head CAS 的人工提交才追加 revision；系统不自动生成或批准视觉决定。v1 capture/review namespace 与 CLI 冻结且不与 v2 混用。
- P10.4a v2 以同一 completed `job_id` 为唯一外部输入。读取路由重放 official Runtime execution，再对 current P10.3c v2 history 做编译前后双快照，并精确读回当前 `sampled_visual_approved` decision。只有 exact job、execution、candidate、revision 和 decision 在同一编译窗口内保持一致，才返回 `admitted_for_safety_analysis`。admission 是 path-free 的 canonical 投影，其 head observation 仅在 compile time 有效，不声称永久 current-head authority，也不写入新的人工决定。
- P10.4b v2 继续只接受同一 completed `job_id`，在编译前后重放 P10.4a v2 current admission，并生成两个独立、可寻址的 canonical 文档。amplitude 文档覆盖 `0/8…8/8` 九个 coupled-gain 结构点；continuous 文档覆盖 Preview v2 的每一对相邻 tick 与统一 `λ∈[0,1]`。入口读取不做精确重放，只快速恢复 active run 或返回 ready；terminal/no run 的新访问会在独立、低优先级 worker 子进程中重新编译 current admission，绝不把历史 completed run 静默当作当前结果。CPU 子进程通过有界 canonical JSONL 只报告固定阶段、单调进度与终态，`continuous_boxes` 为长区间证明提供盒级心跳；HTTP 服务进程因此可以继续处理页面轮询和其它 API。
- P10.4b v2 的父进程是 append-only run 事件日志和完成态的唯一写入者。子进程不得追加事件或发布 `completed`，只可在 active run 下写入严格绑定 request/admission/head 的 staged amplitude/continuous 工件；父进程从磁盘独立读取、重算内容地址和合同绑定，并与子进程回传文档逐字比较后，才能追加 `sealing → completed`。取消、进程异常或服务关闭会终止所拥有的 worker 进程树；staged 工件没有事件链 authority，不能作为部分成功复用。失败状态按来源变化、来源不可用、输入无效、分析校验、分析执行和 worker 进程故障分别归类，旧 failure receipt 保持不可变；新 attempt 需要页面二次确认。
- P10.4b v2 异步 run 不接收客户端路径、文件或 SHA。HTTP 结果只投影九档/连续段摘要与 `{format, format_version, sha256, size_bytes}` 技术回执，不传输可能含逻辑资源字段的完整 canonical 文档；普通页面把 `indeterminate` 作为合法完成态显示。sealed replay 把 JSON 数组字段规范为同一合同表示，并按逐段实际剩余量校验共享盒预算；tuple/list 载体差异或提前 global fallback 都不能伪造失败或通过。
- P9/P10 current-chain inventory 的项目 ID 使用轻量 audit discovery，不触发 override/Resolved 构建。双快照中的 Layer Manifest 派生可复用 8 项进程内 LRU/single-flight 缓存；key 包含 exact Resolved SHA、全部源 raster 内容 SHA 及 15 个相关模块的源码/live callable 算法身份，warm hit 前仍执行 `get_project` 并逐字节重算素材 SHA，compile 后再次核对相同 key。失败、输入漂移和算法变化均不驻留或命中。缓存不落盘、不参与 package/current 判定本身，也没有绕过 before/after 比较；Resolved/override 目前故意不缓存。
- 冻结 v1 的 P10.4a admission、P10.4b1 amplitude-envelope 与 P10.4b2 continuous-proof 仍只能消费 v1 visual-review head。新 P10.4a/P10.4b v2 已建立独立合同、算法 profile、哈希域和 namespace；不得把 v2 admission 静默传入冻结 v1 编译器，也不得把 v1 proof 冒充 current v2 动作域。下一边界是把 current-chain seam 凭据显式连接到 v2 proof，而不是修改任一既有 identity。
- P10.5a seam candidate command 只读取精确 Layer Manifest/P3 静态地址，固定输出六条左右关系和可回看的 attachment-local locator。candidate generator 内嵌从实际行为常量重建的 canonical algorithm profile；candidate、human decision、reviewed set 和动态 probe 是四个独立合同，任何一层都不能改写上一层 evidence hash。
- P10.5b candidate HTTP projection 把 `setup_canvas` 与每个 option/role 的 exact image、`canvas_offset_xy`、同序 `anchor_points` 分开返回；浏览器只用这些字段合成 SVG alpha、contact bbox 和编号锚点，不从 raster 反推 locator。SHA、数值、locator 与单层图默认折叠只影响展示，不改变 canonical evidence。
- P10.5b advisory assist 是独立、确定性、candidate-SHA 绑定的只读合同。`single_option` 和 `blocked_unobservable` 可形成可撤销草稿；`compare_options` 只给 `highlight_option_id`，明确不构成批准。自动草稿、current-head 基线和 option 点击都只修改浏览器 state；只有最终显式确认才进入 decision CAS。
- P10.5b/P10.5c 把人工 revision 与静态 ReviewedSet 分离；package 模式在 ready decision 后通过独立 `POST .../{package_id}/seam-publications` 重放 package/current head，发布 P10.5c 并 exact readback。decision 已提交而 publication 失败时，控制器锁定 decision identity，只允许重试 publication。历史 bundle 可以精确复验，但只有 current ready head 能进入后续编译。P10.5d 不从 candidate 重新选 locator，也不把历史可读性升级为 current authority。
- 冻结 P10.5d v1 command 继续只接受 v1 proof。P10.5d v2 已交付 path-free source、analyzer/compiler/validator、CLI/store/exact reader，以及 exact `job_id+safety_run_id` 自动闭合 current P10.5c 的 server/job/UI 入口。自动任务使用独立 BelowNormal worker 与 append-only attempts；父进程独占最终 exact readback/current-head recheck 和完成态写入。真实 A 尚待当前 P10.4b run 完成并重启服务后执行。
- P10.5d v2 compile 在分析前、发布前、发布后共三次观察 current visual/seam heads，并要求三份 canonical observation 精确一致。只有通过这三次门禁才发布固定 `body-sway-dynamic-seam-source-v2.json`、`body-sway-dynamic-seam-probe-v2.json`、`bundle-manifest.json` inventory，随后按 probe/bundle 双 SHA exact-readback。历史 verify 只重放这三份 exact bytes 和语义 validator；manifest 的 authority scope 固定为 `historical_exact_bytes_only`，不读取或授予 current-head authority。
- P10.5d analyzer 对六关系全部 reviewed pairs 覆盖相邻 tick 与统一 gain，只认证 `4 px²` reviewed-anchor point proximity 工程代理。region–region、region–mesh、mesh–region 有固定投影；mesh–mesh、预算耗尽、非有限包络、backend 自相矛盾和任何 head 漂移都 fail closed。attachment 边界、raster/视觉、runtime、timeline 和发布明确排除。
- P10.6a v1 已冻结，只接受 v1 probe 文件。P10.6a v2 使用独立 format/profile/hash domain，公开输入只有项目与 P10.5d v2 probe/bundle 双 SHA；exact reader 读取固定三文件 inventory，并从其 source closure 自动取得 P9 双地址和完整复验数据，不扫描 `latest` 或要求选择文件。
- P10.6a v2 source 显式绑定 P10.5d source/probe/bundle、P9、Manifest/P3/target/timing 与 Preview v2。pure core 只构造 unit-gain、setup-local、版本中立 motion domain；detached validator 由两份 exact bundle 重编，seal 前后重新观察 visual-v2 与 seam-v1 current heads。
- P10.6a v1/v2 都不发出 MotionInstance v3、adapter 或 Spine timeline。其内部与 CLI 外层 head observation scope 都固定为 `compile_time`；完整 attachment overlap/边界、raster/视觉、runtime、publishable timeline 和 release authority 保持 blocked。冻结 P10.6b v1 只消费 v1 wrapper；已交付 P10.6b v2 只凭项目与 P10.5d probe/bundle 双 SHA 自动生成、复验 v2 admission 和 P9，不选择文件。
- P10.6b v2 prepared pipeline 在同一 reader-issued P10.5d/P9 上生成 core、seal admission、detached replay 并编译 payload；ordinary direct construction 与 `dataclasses.replace` 不能发放 prepared provenance。payload 继续是 MotionInstance format v3，只有 admission/source、bundle address domain 和 run contract 升级到 v2。固定 inventory 为 `body-sway-motion-consumer-admission-v2.json`、`motion-instance-v3.json`、`run-manifest-v2.json`；v1/v2 reader 互不接受对方地址。
- P10.7a v2 只消费 reader-issued P10.6b v2 地址，以独立 source contract、adapter profile、skeleton hash、run/report 合同和 `spine42-v3-v2` filesystem namespace 隔离冻结 v1。固定五文件 exact reader 会重建 `skeleton.json`、`skeleton.atlas`、`skeleton.png`、`run-manifest.json` 与 `export-report.json`；compile 观察 current heads，历史 verify 不观察或授予 current authority。
- Kimodo 的 raw NPZ、source sidecar 与 map 是三个独立输入。sidecar 解释数组/FPS/producer，map 决定投影/角色/contact；两者都不得根据文件名、数组数量或相邻目录隐式发现。
- 所有同卷目录发布统一经 `atomic_staging.create_same_parent_staging` 创建 staging。POSIX 保留 owner-only `mkdtemp`；Windows 不传 `0o700`，以不可预测名称和原子 `mkdir()` 继承 publication parent 的 DACL，再由同卷 rename 发布。这样不会把 Python 3.14 `mkdtemp` 的 protected creator-only DACL 带到最终 bundle；碰撞、失败清理、并发收敛、固定 inventory 与发布后 exact readback 语义保持不变。历史受限 ACL 只允许通过另行授权、精确地址、前后字节/哈希不变的窄范围迁移处理，禁止对整个 state tree 递归重置权限。

## 文件长度预算

生产源码的硬上限为 400 个物理行。新文件超过 300 行时就应评估按职责拆分；函数通常不超过 60 行，超过 100 行必须先拆解或在评审中记录理由。P10 的 MotionInstance v3 测试模块另设 400 行硬门禁，防止安全与攻击用例持续堆入单文件。

当前三个历史单体采用 ratchet：只允许缩短，不允许超过测试中记录的当前上限。

| 文件 | 当前上限 | 拆分目标 |
| --- | ---: | ---: |
| `web/styles.css` | 1713 | 每个主题/布局文件 ≤ 400 |
| `web/app.js` | 1182 | façade ≤ 250，模块 ≤ 400 |
| `src/autospine_workbench/project_store.py` | 838 | façade ≤ 300 |

`tests/test_quality.py` 自动执行上述硬上限与 ratchet；P10 新增生产模块与 visual-review JS test 文件另有 300 行硬门禁。JSON Schema、文档和生成工件不套用源码行数上限，但仍应按版本和领域拆分，禁止手工复制生成文件来规避检查。

## 变更与提交

1. 先写失败测试或可重现 fixture。
2. 一次提交只完成一个可回滚能力；合同迁移与消费方更新可以同提交，但不要夹带格式化全库。
3. 每阶段运行完整单元测试；涉及图像或动画时额外保存固定视角、固定时间点的数值报告和代表性截图。
4. schema 通过只证明结构合法；跨引用、权重和骨架拓扑必须再经过语义验证器。
5. 任何迁移先读旧格式并产出新格式，经过至少一个发布周期后再讨论删除兼容路径。

## 阶段门禁

P0 Resolved Project v1 合同门禁已经完成：独立 Draft 2020-12 Schema 固定完整结构，严格 Python validator 在无 `jsonschema` 时仍可执行语义检查；trusted project 边界必须同时提供确切 override，并固定 project/revision/base/override 身份。候选 inventory 与 joint decision 的 provider/run identity 必须闭合；current split 必须绑定当前 split spec，stale split 不能进入 accepted QA；全部 QA 列表和总状态从实体重新派生。P0 正式冻结前修正了撤销 split authoring 后 stale QA 消失的问题；真实样本 r5/r7 的既有 snapshot SHA 由条件式历史回归确认未受影响。此冻结点之后，v1 生成、QA 或 provenance 语义若需改变，必须新增 `autospine.resolved-project/v2`，不能复用 v1 hash domain。字段和调用入口见 [Resolved Project v1 参考](resolved-snapshot-reference.md)。

P1 已完成并冻结以下边界：

- pose、alpha path/contact geometry 和 joint candidates 分别内容寻址，候选 fragment 在首次发布前绑定真实 geometry SHA 与目标。
- 比较 UI 可以接受、调整、拒绝或标记不可观测，并按固定 SHA 回看几何证据；算法变化不会静默复用旧决定。
- 两份 See-through 样本可用 diagnostic setup prior 重复发布相同工件链；该 smoke 明确不代表模型精度。
- candidate/geometry API 在读取时重新验证 strict JSON、内容地址、project 和领域合同，损坏输入 fail closed。

P2 门禁已经完成：reviewed Layer Manifest → region-only RigIR；FK setup 精确重建，pivot、父子关系、draw order、完整 bundle inventory 与两份真实视觉 golden 均已通过。P2 不生成 mesh 或权重。

图层复核按字段记录 provenance；`visible`、语义、side、pivot、disposition 与目标骨互不代替。RigIR bundle 地址固定为 `builds/<project-id>/rig-ir/<rig-sha256>/<bundle-sha256>/`，第二层哈希同时绑定 RigIR、编译 run manifest、probe report 与 setup-render 合同，runner/renderer/encoder 变化不会改写旧证据。完整 verifier 还校验 region PNG 原始字节、规范路径和 exact inventory。`allow_manual_required` 只用于诊断，不能关闭阶段门禁。

P3 profile-v1 门禁已经完成：只有精确 `body.leg`、左右明确、绑定 `thigh.<side>` 且存在直接子骨 `calf.<side>` 的 region 可以进入确定性 alpha mesh 与参数化两骨权重；其权重、拓扑、setup 和极值动作探针均已关闭。`body.arm.upper/lower` 与 `body.leg.upper/lower` 在 v1 中保留语义和骨绑定，但输出为 rigid region；手工伪造的 arm/segmented-limb hinge 会 fail closed。安全角与代表性 PNG 进入不可变 bundle；没有合格 v1 target 时显式发布 `reviewed-noop`，不伪造 mesh。P3 工件保持版本中立。生产与复验入口分别为 `compile-mesh-rig`、`verify-mesh-bundle`；主工作台底部的“P3 Mesh 证据”只读回看精确双 SHA bundle。分段手臂/腿 mesh 必须使用新的 P3/P5 v2 合同、arm-aware 权重与独立 goldens，不能扩写 v1。

P4 门禁已经完成：从精确 P3 双 SHA 地址生成左右臂腿四个 canonical 两骨手柄；analytic IK 覆盖 reachable、unreachable、镜像、目标重合和退化输入，弯曲方向来自 setup 几何，结果表示为 additive setup-local 旋转。profile/probes 使用双 SHA 地址，严格 reader 重建完整 P3 身份链和数值证据。`kinematic_reach` 只表示数学可达环，P3 mesh 安全角仍是视觉限制。

P5 门禁已经完成：setup-local MotionIR、deterministic idle/wave 和显式 BVH map 均进入不可变 bundle；retarget 五文档合同绑定完整 P3/P4/Motion 来源，并重算有限数、loop、IK、接触与 mesh regression。同一 clip 在三个不同 setup rig 上通过，A/B 两份真实样本的四组输出拥有固定 golden 和只读 state-tree 回归。

P6 门禁已经完成：adapter profile 固定为 Spine 4.2 JSON，五文件内容地址和显式 compile/verify 边界从精确 P3/P5 来源重建；A/B 两份真实样本的 setup、`idle`、`wave.left` 六个 bundle 均由 `@esotericsoftware/spine-player@4.2.119` 成功加载。固定 640×640、DPR 1 的第二轮截图比较在六例中均为零像素差、零 MAE 和零最大通道差，完整地址、语义指标、PNG SHA 与只读 state-tree 回归固定在 `tests/goldens/p6-spine42/`。版本或不支持特性不得静默降级，官方 runtime 由操作者在版本库之外单独安装并完成许可确认。操作入口见 [P6 Spine 4.2 导出与 runtime 检查](how-to-export-spine42.md)。

P7a 兼容性门禁已经完成：BVH compiler 1.1.0 在保留旧单 ROOT 输入的同时，严格接受 Kimodo `Root(6DOF zero wrapper) → Hips(6DOF) → SOMA77`。原始 BVH 不经重写进入内容地址；稀疏角色通过 canonical 最近祖先折叠，`Hips` 旋转不会在目标 thigh 重复叠加。同一个合成 Kimodo-shaped MotionIR 已穿过三套不同 rig、P5 报告/mesh 门禁和 Spine 4.2 bundle reader。该门禁不等于正式 NPZ 合同，也不代表真实 checkpoint 动作质量或官方 Spine Player 截图验收。

正式 P7 合成门禁已经完成：

```text
raw NPZ + source sidecar + explicit map
        ↓
bounded ZIP/NPY snapshot
        ↓
SOMA77 local-matrix FK + global/position cross-check
        ↓
explicit signed-basis 2D projection + root/contact MotionIR
        ↓
five-file immutable bundle + exact-address rebuild
        ↓
three distinct P5 rigs → P6 adapter/bundle reader
```

原始 NPZ 原样保存，sidecar/map/run/MotionIR 使用 canonical JSON；固定 inventory 不接受额外文件。compiler ID、版本、数值容差和算法 profile 都进入 run manifest。`verify-kimodo-motion` 只能从两个明确 SHA 读取、重编译和逐字节复验，不解析 `latest`、不搜索替代 bundle、也不写 state。

producer provenance 的 `recorded` 与 `unavailable` 是不同的显式状态。P7 bundle 只保存外部 manifest/request 的 SHA；M1.0 `audit-kimodo-pilot-intake` 补充发布前的六输入边界：安全读取 raw NPZ、sidecar、map、camera 和两份 opaque provenance 原件，逐字节固定 NPZ/两份原件、以 canonical JSON 固定三份文档，并要求原件 SHA 与 recorded sidecar 闭合；随后在内存重跑 P7 结构编译并验证 camera/map。它不写 state、不发布 P7/P8，报告不含路径，且固定声明 checkpoint authenticity、动作质量、P8 projection、P9 review 与 release authority 均未获得。操作者仍须保留原件及许可记录。

完整 NPZ 只把 `smooth_root_pos` 当有限数证据、把 `global_root_heading` 当单位方向证据，当前不用它们改写 MotionIR。contact 采用半开 `annotation_only` marker，不等于 foot lock。

正式测试证明确定性合成 NPZ 的 root、代表性肢体旋转和 contact 可通过三个 rig 的 P5/P6 结构门禁；M1.0 另证明同一六输入可得到确定性 path-free intake report，且其 P7 preview 身份可与后续正式编译对齐。真实运行的 `wave-left-v1` 已通过 intake，并完成 P7/P8、A/B P5 与各自 P9 reviewed-motion bundle 的 exact replay；身份集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)。A revision 6 另有 current P10.5c set `00de666e…`/bundle `e23e3792…`。P10.5d v2 自动入口已交付，但 A 仍待当前 P10.4b run 完成并重启服务后真实执行；在此之前不能声称动态遮挡/接缝、official Runtime 或视觉通过。

P8 相机感知投影门禁已经完成：

```text
exact P7 Kimodo bundle + explicit static CameraModel
                         ↓
matrix-FK replay → signed orthographic projection
                         ↓
2D vector + L3/L2 + depth cosine/root-relative depth
                         ↓
three-file immutable ProjectedMotionIR bundle
                  ┌──────┴──────┐
                  ↓             ↓
       exact P7 legacy bridge   target-rig scale candidates
                  ↓             ↓
          unchanged P5/P6      no runtime timeline
```

Camera basis 与 reference length 必须和 P7 map 完全一致。ProjectedMotionIR 保留相机、P7 raw/source/map/run 的完整身份，并由严格 reader 从原始 NPZ 逐字节重建。depth 是 target-independent 证据，不等于 draw order；foreshortening report 是与 P5 target profile 交叉绑定的 candidate，不等于已批准 scale 动画。任一 collapsed sample 在 v1 bundle/legacy/scale probe 边界 fail closed。

P8 的零回归门要求 legacy MotionIR SHA 与 P7 完全相同，同一投影证据可用于三套不同目标 rig，并且 P5 MotionInstance 与 P6 Spine 4.2 仍只输出 rotation/translation。P9 已以新候选/决定合同、MotionInstance v2 和独立 adapter v2 消费经批准的 contact/depth；它不修改 P8 证据或静默扩展 MotionInstance v1。

P9 reviewed motion 结构门禁已完成：

```text
exact P3/P4/P5 target chain + exact P7/P8 evidence
                         ↓
    fresh non-authoritative namespace preparation
                         ↓
       Kimodo evidence + Foot candidates
            + pending Depth proposal
                         ↓ explicit policy approval
             formal Depth pair policy
                         ↓
              depth-order candidates
                         ↓
       loopback-only zero-write Python preflight
                         ↓
             exhaustive human policy decision
                         ↓
       explicit human adoption + exact package reload
                         ↓
           reviewed policy + MotionInstance v2
                         ↓
       six-document immutable bundle → exact verify
```

Evidence 保留源事实，candidate 把证据绑定到一个精确目标 rig。草案准备仅将当前 slot 绑定、canonical bone role 和 setup draw order 投影为可复核的 Depth proposal；`pending_human_review` 不是正式 policy，也不能触发 Depth candidate 或 runtime draw order。进入人工表单前，Python preflight 先为已明确批准的正式 policy 返回 canonical identity，再重算 policy/foot/depth 三份 identity 与完整 candidate inventory；声明 SHA、P8/P5/P3 source、tick schedule、hysteresis、pair/slot/setup-front 任一不闭合都会 fail closed。Preflight 的 `passed` 只说明这组内存文档可进入当前页面，不是 decision、revision、reviewed policy 或 bundle 地址。Decision 仍必须由人对候选集逐项批准、拒绝或标记不可观测。Reviewed policy 才是 runtime 意图：foot root correction 显式编码 release/loop-reset，draw order 在全部帧上给出完整 slot permutation。Heading 和 scale 仍仅作 evidence，attachment switch 尚未实现。

MotionInstance v2 和 Spine adapter v2 是新能力边界；v1 instance、P8 evidence 及既有 P6 bundle 的内容哈希保持不变。Reviewed bundle 固定六文件 inventory，地址显式包含 project、MotionInstance v2 SHA 和 bundle SHA。严格 reader 从 run manifest 重放 exact P3/P5 上游，不使用 `latest`、目录扫描或替代 bundle 回退。

绑定 revision 改变后，旧 P9 adoption 仍可按历史地址复验，但不再是新链的 authority。样本 B revision 16 已重新生成 Manifest、P2–P5 并准备 `wave-left-v1-r16-draft`；该 namespace 只有 Foot candidates、pending Depth proposal 与 draft manifest，不含正式 Depth policy、Depth candidates 或 adoption。其 `ankle.left=unobservable` 只关闭 authoring 决定，不会清除旧启发式坐标；P4 与 Foot v1 仍可在数值上使用该坐标。因此 P4/P5 finite/IK/marker 通过不能证明解剖脚踝、鞋口代理、真实接触或左腿 foot-lock，任何涉及左脚 root correction 的 P9 候选都必须保持人工阻塞，直到另立显式 proxy-effector/observability 合同。

P9 磁盘 package 及其内容身份继续使用 v1。Loopback API 对 list/detail 返回独立的 HTTP projection v2，在原只读字段外增加 `authoring_alignment`；只有这个展示投影参与 current/historical 选择，字段不会写回磁盘、进入 package ID 或改变历史 exact reader。

这一门禁关闭的是合同、provenance、内容寻址发布与 exact reader 重放的结构闭环，不是官方 runtime 或 raster truth。Preflight 只把候选展示边界收窄到 loopback Python 语义；最终 adoption 才调用服务端 decision/policy 编译、不可变 store 和 exact reader。CLI 使用相同领域边界，保留为专业复验与无浏览器流程，不再是普通页面确认后的手工交接步骤。P9 动态官方 runtime screenshot、seam 和真实作品质量门禁仍未关闭，不得由 preflight、adoption 成功、合成 fixture 或结构 audit 代替。操作入口见 [复核并发布 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

P10.0–P10.2a 已完成 idle 行为候选、candidate-bound 人工决定、body-sway 采样结构诊断和统一 gain 调整诊断边界：

```text
exact Layer Manifest + exact P3 mesh + exact P5 retarget + exact P9 bundle
                                  ↓ replay
                four-feature idle evidence inventory
                                  ↓
                candidate-only report (P10.0)
                                  ↓ exhaustive human decision
                adjust + pending_probe (P10.1)
                                  ↓
        fixed-schedule setup-local body-sway overlay
                                  ↓
 loop / FK / mesh / canvas / shared-index checks (P10.2)
                    ┌─────────────┴─────────────┐
                    ↓                           ↓
       structural_rejected          manual_visual_required
                    ↓                           ↓
 sampled canvas + geometry          official Runtime preparation
 at uniform gain 0/8…8/8 (P10.2a)
        ├─ non-zero passing point → unvalidated draft
        │                           → explicit P10.1 revision
        │                           → rerun P10.2
        └─ no non-zero passing point → repair upstream structure
                                  ↓
                   release gate always blocked
```

P10 exact loader 接受 Layer Manifest、P3 rig/bundle、P5 MotionInstance/bundle 与 P9 MotionInstance v2/bundle 七个完整 SHA，重放 P9 合同，不扫描目录或回退到 `latest`。Candidate compiler 固定列出 blink、body sway、hair spring、mouth；当前只有完整 canonical 躯干链能产生 body-sway candidate。Decision 必须绑定 exact candidate，且 body-sway 只有带人工参数的 `adjust` 才能保持 `pending_probe` 并进入探针。

普通 P10.0–P10.1 入口不把七个 SHA 或本地文件交给浏览器。服务端以 motion-policy package 的 foot/depth 身份匹配内容寻址 P9 adoption；匹配只形成待重放 entry，随后仍由 exact reader 闭合 P3/P5/P9 并重编 candidate。零匹配会报告前置缺失；同一 project/clip 多匹配不会按 mtime 或 `latest` 猜测。entry ID 绑定 package 与精确 P9 adoption，candidate SHA 另行绑定算法输出，因此算法变化会进入新的 decision namespace。进程内 replay cache 的 key 同时绑定 state root、project、MotionInstance v2 SHA 与 reviewed bundle SHA；它只复用通过 exact reader 的 immutable chain，并以每次请求的全字节 seal 重验作为命中条件。P10.2 derived cache 的 key 更进一步绑定完整 exact address、candidate SHA、current revision/decision SHA 与 probe/canvas profile SHA，只用于消除相同 current head 的重复派生计算。两类缓存条目都不落盘、不跨进程，也不授予 candidate、decision 或 current-head authority；P10.2 请求仍做前后 exact replay/head 检查。

页面的 composite、四骨 FK 示意、播放时间轴和低幅参数只属于 `unvalidated_draft`，全部安全、Runtime、raster、seam 与 release claim 都为 false。拖动或播放不产生人工 authority。保存参数、拒绝和不可判断三个入口统一经过原生二次确认：弹窗以文本列出项目、动作、决定类型及其后果；取消按钮、Esc 和遮罩点击都在 mutation 之前返回，因此不发 POST、不写 revision。只有“确认并提交”才携带 intent 和 `explicit_confirmation=true`；服务端再次重编 candidate、读取 history/current head、检查 base revision/head，再自行构造 `human / completed` 字段。P10.1 历史在 candidate SHA 下使用内容寻址 decision 与连续 revision slot，字节相同的重试幂等复用，不同并发输入只能有一个 CAS winner。CLI 的 candidate/decision/probe 仍保持零写入，供专业复验。

`BodySwayProbeReport v1` 固定检查 `loop_closure`、`fk_finite`、`sampled_mesh_deformation`、`sampled_canvas_containment`、`shared_index_internal_continuity`、`inter_attachment_seams` 与 `visual_quality`。前五项是采样结构证据；无 mesh 或非 loop 会显式 `not_applicable`。接缝缺少 reviewed anchors，视觉质量需要官方 runtime 人工预览，因此后两项保持 `unobservable`，顶层 release gate 无条件 blocked。

`BodySwayCanvasAdjustmentCandidates v1` 与 report 使用同一 exact 输入和 schedule，但不继承人工或发布权。它只缩放四骨幅度，保留周期与相位；固定网格中的每个点都是离散诊断，不是连续安全区间。只有非零 gain 的 sampled canvas 与 sampled geometry 同时通过时，才输出一个可带回 P10.1 的 `unvalidated_draft`。任何 draft 都必须经过新的显式 P10.1 确认，并由新的 current head 重跑 P10.2；服务端不会把诊断直接升级为 decision。

真实样本 B 说明了这一区分的必要性：reviewed gain `8/8` 有 `334/334` 个 canvas 失败 tick，零增益 `0/8` 仍有 `333/334` 个失败 tick，涉及 `layer-006-objects`、`layer-000-back-hair` 与 `layer-008-hand-r`。所以该样本没有纯统一 gain 修复，必须调整画布/attachment/骨绑定或上游动作，P10.3 保持 fail closed。

代表性 `sample_sha256` 包含 tick；loop 端点比较使用不含 tick 的独立 pose-state domain，再封入 loop check evidence。Bulk evidence digest 是 compiler seal，不是独立重放载荷。该边界不产生 MotionInstance v3 或 runtime timeline，也不声明连续时间、幅度安全范围、接缝、raster truth 或视觉通过。操作入口见 [复核 idle 行为并运行 body-sway 结构探针](how-to-review-idle-behaviors.md)。

P10.3 v2 在结构探针和独立 CaptureFraming 决定之后增加官方 Runtime sampled-still 证据与人工 revision，但仍不跨越 release 边界：

```text
current package + P10.1 + P10.2 + accepted CaptureFraming
                                  ↓ package-centric exact replay
           Preview v2 + projection + plan + world viewport
                                  ↓ fixed Runtime/Chrome validation
                    explicit license acknowledgement
                                  ↓ per-run second confirmation
                     append-only asynchronous job
      ↓ runner 1.1.0 / collector-terminal official 4.2.119 execution
            immutable execution JSON + payload v2 + PNGs
                                  ↓ completed job_id
          v2 candidate + setup/21-pair timeline projection
               ↓ default approve browser draft only
                 exhaustive human case decisions
                                  ↓ candidate-bound history/CAS
       sampled_visual_approved | sampled_visual_rejected
                                  ↓
                  release gate always blocked
```

真实 capture 的外部信任前置条件是操作者提供并确认有权使用官方 `@esotericsoftware/spine-player@4.2.119`。仓库不下载、再分发或从 `LICENSE` 文件推断授权；test-only `SpinePlayer` stub 只覆盖 Chrome 进程、loopback 与 PNG 通路，不能进入真实视觉证据链。environment snapshot 固定绑定 Runtime JS/CSS/package/LICENSE、Chrome executable/version 和 capture profile。每次执行还要求独立的许可勾选与本次运行二次确认。

job request 与 event history 采用 append-only store；页面可以按 job ID 恢复查询，但 manager 不自动重试失败/中断 job。失败终态保留 path-free 精确 `failure_code`，不暴露原始异常、路径或命令行。成功后 store 按 `builds/{project}/body-sway-runtime-executions/{preview-v2-sha}/{bundle-sha}` 发布固定 execution JSON、payload v2 JSON 和 captures；exact reader 使用 project/preview/bundle/artifact 四段地址读回。completed job 是普通 UI 的唯一 handoff，页面 URL 只携带完整 `job_id`。

六次历史样本 A job 分别在不固定 case 处失败；这些 job 与事件链不可变，没有发布部分 execution。
根因包括旧 execution v2 驱动携带 `--dump-dom`/`--virtual-time-budget` 与异步 collector-terminal
完成条件冲突，以及 exact 截图提交后的主动 teardown 与 stdout reader 退出竞争。v2 runner `1.1.0`
把 page lifetime 固定为 collector terminal，并且仅在 capture 已提交、异常由主动 teardown 引发时
容忍 stdout reader 关闭错误。提交前读取失败、输出超限、reader 未退出或 pipe 无法关闭仍 fail
closed。该 runner 与 profile 是新 v2 身份；不会改写冻结 v1 或六个历史失败 job。runner 1.1.0
的后续 job 已完成 43/43，并发布完整 execution；对应 P10.3c v2 revision 1 已通过全部 43 个 sampled still。

P10.3c v2 从 completed job 解析内部四段地址，并绑定 current Preview v2、framing、P10.1、report 与 world viewport。43 个不可变 case 必须严格是一个 setup 和 21 个同 tick 的 `p10.base/p10.body-sway` pair，UI 才会建立 22 位置时间轴；错序、缺帧、重复或 tick 不一致都失败关闭。默认 approve 只初始化浏览器内存草稿，只有图片已加载且当前组真实显示才增加浏览覆盖；完整浏览门禁、current-head 基线、复核人、最终声明和确认全部满足后，首次人工提交才会发布 exact candidate，并在 candidate SHA 命名空间下写入内容寻址 decision 与连续 revision slot。CAS 拒绝 stale head、跳号和并发抢占；字节相同的安全重试可复用。HTTP 投影不返回本地路径，图片只能经 job/candidate/case/PNG identity 读取。

图片展示采用四级非权威加速。浏览器以完整 exact URL 强引用唯一图片节点，限制两张并发并后台预载全部 43 帧；服务端按 job/package/四段 execution/candidate 身份维护有界 single-flight 图片快照 LRU。candidate 在完整 current 校验并验证全部 PNG 后签发一个随机、进程内、固定 120 秒到期的只读会话，同时返回同一快照的 history；会话精确绑定 job/candidate/case/PNG，不能读取 history、提交 decision 或授予 authority。会话有效期内图片 GET 不重复重放 current source；源/head 随后变化时仍只能返回签发时已验证的内容寻址旧像素，而新的 candidate 和最终 PUT 会完整重验并失败关闭。无会话 exact URL 保留原逐请求 current 校验。

另有按 completed job 隔离的持久 Preview v2 mount snapshot：新 job 完成后预写，旧 job 首次读取时懒回填；快照只包含可重建的 candidate/framing/Preview bytes，不包含 history、decision、current head 或 CAS authority。snapshot v3 显式绑定 Preview 编译器摘要；摘要按包内静态 import 闭包生成，当前为 292/755 个模块，相关依赖变化会失效而无关 UI/服务模块不会。重启命中仍 exact-read execution，逐字节重算所选项目的 Resolved/source-raster/算法身份，并校验 P3/P5/P9 内容地址、P10.1/CaptureFraming heads 和 Preview/artifact seals；无关项目与其他 adoption 不再进入该 mount 的依赖闭包。GET 可使用 verified mount token 避免第二次 Preview 重编。PUT 明确禁用持久 mount 与图片 session，实时复验 authority/current heads 后执行 CAS；键控的进程内 Preview/current-chain 派生缓存仍可在各自 current validator 通过时复用结果。响应保持 `Cache-Control: no-store`，图片 ETag 继续绑定 PNG SHA；访问日志会隐藏规范及等价编码的会话参数值。详细操作见[运行 P10.3 官方 Runtime 自动采集](how-to-capture-body-sway-runtime.md)和[复核 P10.3c 官方 Runtime 采样帧](how-to-review-body-sway-runtime.md)。

`sampled_visual_approved` 只表示固定 still inventory 全部获人工批准。它不声明离散帧之间的连续时间、reviewed seam anchors、安全幅度、未采样姿势或可发布 timeline，因此 release gate 仍固定为 blocked；reject/unobservable 还会增加明确的 sampled rejection reason。P10.4a v2 不扩大这个结论，只证明该 approved head 与 completed execution 在本次编译时闭合，可以进入后续 safety analysis。

冻结 v1 的 P10.4a–P10.4b2 把 v1 current visual head 准入、离散 gain candidates 和连续预览模型证明拆成三层只读合同：

```text
sampled_visual_approved current head
                    ↓ double snapshot
       BodySwayReviewAdmission v1
                    ↓ exact replay
 nine coupled-gain sampled candidates
                    ↓ full source closure
 every adjacent tick × λ∈[0,1]
                    ↓ bounded interval subdivision
 certified preview structure | indeterminate
                    ↓
          release gate always blocked
```

该图不能用于 v2 head。v2 链使用新的 P10.4a admission 与 P10.4b v2 双证明：

```text
completed official Runtime job + current approved P10.3c v2 head
                                  ↓ exact replay + double snapshot
                   BodySwayReviewAdmission v2
                                  ↓
                  admitted_for_safety_analysis
                                  ↓
          nine coupled-gain structural points (v2)
                                  ↓
       every adjacent Preview v2 tick × λ∈[0,1]
                                  ↓ bounded interval subdivision
        certified preview structure | indeterminate
                                  ↓
                       release gate blocked
```

v2 admission 不改写决定、不声称永久 head authority，也不能静默落入 v1 admission。当 v2 current head 或 execution 源发生变化时，consumer 必须重新编译 admission，不能继续信任旧文档。amplitude 与 continuous proof 使用独立自哈希和 profile identity；只有 `8/8` 点继承官方 sampled visual 审批，其余八点和全部区间都没有新增人工视觉覆盖。全段结构认证也不产生可发布安全范围。

连续证明内嵌并重算 candidate、RigIR、target profile、MotionInstance v2、temporary preview manifest 与 preview projection。固定后端包围数学三角函数、Q9 图层与 Q4096 顶点量化误差，并检查 FK、画布、mesh area/edge 与共享索引内部连续性；它不把 point samples 当作区间证明。输入和结果都有显式 byte/box/depth 上限，任何未证明状态都不能升级为通过。v2 操作入口见[分析 P10.4b v2 身体摆动安全性](how-to-analyze-body-sway-safety-v2.md)；[冻结 v1 连续证明](how-to-compile-body-sway-continuous-proof.md)仅用于历史链。

该结论只适用于固定 preview 数学模型，不代表目标平台 `libm`、官方 Spine runtime 或 raster truth；attachment 间 seam 仍缺少 reviewed anchors。静态 seam candidate、人工 decision 和 reviewed anchor set 应作为独立上游合同，之后才能在相同动作域上追加 seam 证明，不能修改本阶段既有 hash 语义。

P10.5a 已实现上述第一层静态合同：

```text
exact manifest + exact P3 rig/bundle + exact attachment PNG set
                              ↓
       fixed semantic relationship inventory (6 rows)
                              ↓
       bounded alpha contact/lobe candidate comparison
                              ↓
     sealed option evidence + sealed relationship evidence
                              ↓
       human decision missing; release remains blocked
```

region locator 使用 Q4096 attachment-local 坐标；mesh locator 使用 Q65535 重心坐标并在量化后重新规范到最小包含三角形。candidate 只有 2–4 对分别严格有序、连接线不相交也不相触的锚点。独立 validator 会重算完整 reason/status/contact/sampling/type 矩阵与 evidence seal；算法 profile 覆盖关系/角色、contact/lobe、采样、资源、locator 与 pair policy。操作入口见[编译 P10.5a 静态接缝锚点候选](how-to-compile-seam-anchor-candidates.md)。

P10.5a 没有写路径，也没有 candidate 历史。P10.5b 已在独立 namespace 中完成 candidate SHA/option evidence SHA 绑定的 `accept/adjust/reject/unobservable` revision：

```text
fresh exact candidate + history A + explicit base/head
                          ↓
      fixed six-row human decision materialization
                          ↓
 candidate-bound validation against exact P3 topology
                          ↓
 write-once content + linear revision slot + readback
```

prepare 和 GET 只读重编 candidate；candidate envelope 额外投影 setup canvas、attachment image offset/anchor point 与确定性 assist，但这些字段不进入人工 authority。页面自动绑定 package current head，把唯一候选和不可观测项写成可撤销草稿，多候选只高亮建议项；点击 option 才形成 `accept` 草稿。提交前不会发布 candidate 或 decision，提交时才把 exact candidate 与 decision 写入各自内容地址。decision 历史以 candidate SHA 隔离，不提供 `latest`，同一输入的并发重试收敛，不同输入只允许一个 CAS winner。HTTP 图片证据还要求 candidate option、attachment 与 exact P3 source PNG SHA 同时匹配。操作入口见[复核 P10.5b 静态接缝锚点](how-to-review-seam-anchors.md)。

即使六条关系全部 accept/adjust，P10.5b 也只给出 `reviewed_anchor_set_ready_for_compile`。P10.5c 必须用双历史快照确认指定 decision 仍是当前 head，再编译独立 reviewed set；P10.5d 必须重放该 set 与 P10.4b2 动作域后才能产生动态 seam claim。

P10.5c 已把这条静态边界实现为独立的 `ReviewedSeamAnchorSet v1`：

```text
exact address + history A + exact ready decision
                         ↓
       exact P3/candidate replay + pure six-row projection
                         ↓
                    history B
                         ↓
 fixed three-document bundle at reviewed-set SHA / bundle SHA
```

set 的 source 固定 manifest、P3 rig/bundle、candidate、review revision 和 decision
六项身份；顶层 project 组成完整七段来源。compiler profile、静态语义、claims 和 release
gate 都进入内容哈希。bundle 只含 exact candidate、exact decision 和 compiled set，writer
在首个写入前重编，reader 按双 SHA 重放，不扫描或选择 `latest`。历史 bundle 在新 revision
出现后仍可精确复验，但 compile-time 双快照不提供永久 current-head authority；P10.5d
消费前仍须重新检查 review head。命令、失败语义与测试构造/真实人工批准的边界见
[编译并复验 P10.5c 静态接缝锚点集](how-to-compile-reviewed-seam-anchor-set.md)。

普通 package 页面通过 `reviewed-seam-anchor-set-publication-v1` intent 只提交
package/candidate/revision/decision 身份；服务端重新生成 P9→P3→candidate closure、确认 ready
current head，再复用同一 compiler/store/reader 返回 path-free exact receipt。该便利入口没有把
P10.5b 与 P10.5c 合并成一个合同：revision 已经落盘后 publication 失败，重试不会再次写 decision。
当前真实 A 已由操作者确认 P10.5b revision 2（`6/6 accept`、`24` 个 anchor pairs），该 revision
明确 supersede revision 1；新的 P10.5c set/bundle 也已 exact verify。B 的四条不可观测关系仍在
ready gate 前 fail closed。A 的静态凭据不能跨过尚缺的 P10.1 动作参数、P10.2/P10.3 与
P10.4b2，直接冒充 P10.5d 动态接缝证明；动态接缝、Runtime 等价和视觉接缝质量仍为 blocked。

P10.5d 在不修改 P10.4b2 或 P10.5c hash 语义的前提下合并两条链：

```text
exact BodySwayContinuousPreviewProof v1
                         +
exact ReviewedSeamAnchorSet bundle (set SHA / bundle SHA)
                         ↓ full replay + cross-binding
       outer before current-head observation
       ├─ visual history A → decision → history B
       └─ seam history A → decision/replay → history B
                         ↓
 six relationships × every reviewed pair
 × every adjacent preview tick × uniform λ∈[0,1]
                         ↓ bounded outward interval subdivision
     anchor proximity certified | indeterminate
                         ↓
       outer after current-head observation
                         ↓ exact before/after comparison
              BodySwayDynamicSeamProbe v1
                         ↓
                 release remains blocked
```

region locator 使用 Q4096 attachment-local 点与 slot bone 刚性投影；mesh locator 使用
Q65535 重心坐标和动态 LBS 三角形顶点。共同 root translation 在距离计算前代数消去，
距离使用无平方根的平方上界。`4 px²` 等价于 anchor point 距离 `2 px`，但它只是一项
版本化工程容差，不是完整 attachment 边界或视觉标定阈值。v1 对 mesh–mesh 明确
fail closed，不会退回 setup 点或最近顶点。

每段结果固定包含六关系、全部 pair 的最大平方距离上界、box/terminal/depth 计数、
scope、exclusions 与独立 evidence seal。每段最多 32,768 box、深度 14，全部段共享
32,768 box；全局预算耗尽后的段仍输出完整 indeterminate inventory。backend evidence
必须满足完整二叉树计数以及 upper/reason 一致性，异常或伪造对象不会变成通过。

顶层认证还要求上游 P10.4b2 已是
`continuous_preview_model_structural_certified`。即使 proximity 通过，外层和内层
head observation 的 scope 都固定为 `compile_time`，保存 stdout 或重复验证 hash 不会
获得永久 authority。操作、退出码与真实 A/B test-only/blocked 边界见
[探测 P10.5d body-sway 动态接缝锚点](how-to-probe-body-sway-dynamic-seams.md)。

冻结 P10.6a v1 在不改变 P9、P10.4b2、P10.5c 或 P10.5d v1 hash 语义的前提下建立消费入口：

```text
certified BodySwayDynamicSeamProbe v1（完整内嵌）
                         +
 exact P9 MotionInstance v2 / reviewed bundle
                         ↓ full replay + byte identity
       before current-head observation
                         ↓
                 pure core compiler
  unit gain sampled-linear rotations + exact MIv2 base channels
                         ↓
       after current-head observation
                         ↓ exact identity + canonical bytes
        BodySwayMotionConsumerAdmission v1
                         ↓
                 release remains blocked
```

`motion_domain` 只组织后续编译器可以消费的版本中立 setup-local 数据：P10 preview 的
sample ticks/rotation keys，以及 MIv2 原有 root translation、contact markers 和 stepped
draw order。它有独立 source、base-channel、motion-domain 与 head-observation seal，公开
validator 仍从内嵌 probe 和外部精确 P9 bundle 重编 pure core，不能只信任这些摘要。

准入 status `setup_local_timeline_compilation_admitted` 只说明下一个 timeline compiler
可以开始工作。它不含 MotionInstance v3、adapter 或 Spine export；before/after observation
及 CLI 的外层 observation 都只在 `compile_time` 有效。操作入口见
[编译 P10.6a body-sway 动作消费准入](how-to-compile-body-sway-motion-consumer-admission.md)。

P10.6a v2 保持这项窄语义，但把上游明确升级为 P10.5d v2 固定三文件 bundle，并使用独立
format/profile/hash domain。CLI 不再读取操作者选择的 probe 文件；它只接收项目与 probe/bundle
双 SHA，由 exact reader 复验 source/probe/manifest 后，从 source closure 自动读取 P9。v2 source
还固定 P10.4b v2 continuous proof、P10.5c v1 ReviewedSet、Manifest/P3、target profile、Preview v2
和 timing。detached replay 必须从 P10.5d v2 与 P9 两份 exact bundle 重编同一 core。操作入口见
[编译 P10.6a v2 动作消费准入](how-to-compile-body-sway-motion-consumer-admission-v2.md)。

P10.5d v2 reader-issued 对象是进程内 provenance 约定，不是对同进程恶意 Python 反射或
monkeypatch 的密码学沙箱。发放 receipt 保存在 reader 类型闭包中，不作为模块 API 暴露；真正的
数据完整性边界仍是公开 CLI 强制执行的 exact filesystem address、固定 inventory、完整 probe
语义重放与 P9 重放。后续轻量 byte/address 复查只用于避免在同一次已验证调用链内重复执行耗时
区间证明，不能单独把任意内存对象提升为可信凭据。

版本升级只改变来源合同，不改变 setup-local track payload 语义，因此没有创建 MotionInstance v4。
P10.6b v2 已用独立 admission source、bundle/run 地址域、filesystem namespace 和 exact reader
关闭这项版本边界，冻结 v1 consumer 不会静默接受 v2 admission 或 bundle。

P10.6b v1/v2 都在实际消费时重新检查 visual/seam current head，并把上述 motion domain 编译为
可严格重放的 MotionInstance v3/timeline bundle。固定库存均为 admission、v3 与 run；发布使用
v3/bundle 双 SHA，无 `latest`。MIv2 root translation、markers 与 stepped draw order 原样保留，
rotation overlay 只允许躯干四骨。v2 compile 的公开输入只有项目与 P10.5d probe/bundle 双 SHA；
verify 的公开输入只有项目与 MIv3/bundle 双 SHA。历史 reader 不观察 current head，因此只证明
当时发布的字节可重放。store 在创建 publication parent 前独立执行 before → contract → after
门禁，公开命令发布后再按精确地址读回；run 的 authority 只开放 MotionInstance v3 emitted，
attachment overlap/完整边界、raster/视觉、Runtime、永久 head、Spine adapter、publishable timeline
和 release authority 均固定 false/blocked。v2 操作入口见
[编译并复验 P10.6b v2 MotionInstance v3](how-to-compile-motion-instance-v3-v2.md)。

冻结 P10.7a v1 以 project 与 v1-source MIv3 双 SHA 作为公开输入，严格重放 MIv3→P9→P5/P3→RigIR/源 PNG，
再用独立 adapter profile `3.0.0` 生成固定 Spine 4.2 JSON、atlas 与 PNG。五文件 bundle 使用
独立 `spine42-v3/<skeleton-sha>/<bundle-sha>` 地址空间；store 和公开命令均执行 current-head
门禁，发布后 exact reader 会从完整上游逐字节重建。旧 P6 profile/hash 不变，未知能力 fail
loud。run 只开放 adapter emitted，官方 Runtime/raster、永久 head、publishable timeline 和
release authority 均保持 blocked。它不能静默读取 P10.6b v2 source contract。

P10.7a v2 已用新的 source contract 显式绑定 P10.6b v2 的 MotionInstance、bundle、admission、
P10.5d/P9、目标 profile、base retarget、P3 与 RigIR 身份。Spine skeleton 内容继续由同一受限
adapter shape 生成，但 skeleton hash、run/report format v2、bundle identity 和
`spine42-v3-v2/<skeleton-sha>/<bundle-sha>` 地址空间均独立。固定 inventory 为
`skeleton.json`、`skeleton.atlas`、`skeleton.png`、`run-manifest.json` 和
`export-report.json`；发布后 exact readback 与历史重放会逐字节重建全部五项。普通页面只从
completed P10.6b URL 接受 `job_id+safety_run_id+dynamic_run_id+motion_run_id`，自动执行
inspect/start/poll/result，不接收项目、文件或 SHA。append-only failure attempt 只有在确认后才会
重试。专业 compile 只收项目与 MIv3/bundle 双 SHA，verify 只收项目与 skeleton/bundle 双 SHA。
完整入口见[自动生成并复验 P10.7a v2 Spine 4.2 v3 Adapter](how-to-compile-spine42-v3-v2.md)。

v2 run 的十项 authority 中只有 `spine_adapter_emitted=true`；attachment overlap、dynamic seam
safety、完整边界、官方 Runtime、Runtime 等价、raster 视觉、永久 head、publishable timeline
和 release authority 都固定 false/blocked。P10.7b v2 只读 runtime-source bridge 现已接通上述
版本隔离地址：公开 Python bridge 只接收项目与 P10.7a v2 skeleton/bundle 双 SHA，经 exact
reader 历史重放五文件 bundle，不观察 current heads，再确定性生成
`official-runtime-capture-plan-v2.json` 和 `official-runtime-source-admission-v2.json`。source
contract、runtime profile、plan 与 admission 各有独立 v2 哈希域；v1 source 不会被强制转换为
v2，跨版本、篡改或重封装输入均 fail closed。

该 admission 只把 `p10_7a_v2_exact_replayed` 与 `bounded_capture_plan_emitted` 设为 true；
官方 Runtime、runtime 等价、raster 指标/视觉、人审、永久 head、可发布 timeline 与 release
authority 全部为 false，`release_gate` 固定 blocked。

在 bridge 之后，P10.7b v2 已新增严格 session set、bounded in-memory collector、loopback-only
HTTP server 与 Windows real browser runner。每个 session 都按 capture-plan artifact 顺序绑定同一
admission、plan、Runtime JS/CSS 字节身份、P10.7a v2 skeleton/atlas/texture 与预期
attachment observables；跨版本对象、runtime/asset/plan/admission 篡改或 collector/session 串线
均 fail closed。collector 对每个 artifact 只接受一次 capture/error 终态，限制单项与总 PNG
字节，并只在全部 artifact 终态时形成内存 snapshot。server 复用 transport-only core，限制
loopback 地址，校验 Host、Origin、路径、方法、内容类型和 session 身份。

real runner 的信任顺序是固定的：`license_acknowledged` 必须严格为 `true`，并在任何
I/O 之前确认 Windows；随后只读一次精确 P10.7a v2 bundle，锁定 Spine Player 4.2.119
Runtime 包和 browser executable lease，为每个 artifact 创建全新的临时 browser profile，经本次
loopback server 捕获，并在执行期间反复检查 browser 身份、结束前重读 Runtime 包。任何顺序、
身份、lease 健康度或完整性偏差都不会产生部分成功。

runner-issued 结果现可封装为 path-free `captured_unreviewed` evidence。其固定前缀库存为
`capture-manifest-v2.json`、capture plan、source admission、runtime session set 与 runtime reports
五份 canonical JSON，后接 plan 声明顺序中的 PNG captures。manifest 只授予 official runtime
loaded、capture completed 和 isolated attachment raster captured；metrics、人工视觉和 release
仍为 false/blocked。

bundle 使用独立 `autospine.spine42-v3-runtime-bundle/v2` 哈希域与
`spine42-v3-runtime-v2` namespace。原子 store 在完整 detached replay 后发布，并在落盘后重新
校验；exact reader 只接受项目、P10.7a v2 skeleton SHA、P10.7a v2 bundle SHA、capture bundle SHA
四段地址，单次读取上游与每个声明文件，不观察 current heads。缺失、额外、错大小写、alias、
篡改或跨地址内容均 fail closed。

当前仍无 P10.7b v2 完整 CLI/UI、raster metrics、人工复核或发布权；guarded 授权内核已交付，执行/API 为接续工作区改动。机制测试使用模拟边界，
没有真正启动经授权的官方 Runtime；P10.7a 页面也不会自动启动它。guarded v2 runtime authorization 已于 4254151 交付；后续优先推进 PipelineRun 与一键 Spine，
实际 Runtime 执行始终是操作者明确授权后的外部边界；冻结 v1 字节与哈希保持不变。

P10.7b v1 用固定官方 Runtime/浏览器身份、case plan、完整 setup attachment isolate 与 sampled
raster 指标形成不可变 capture；candidate 和完整 human decision 保持分离。其后的 readiness
v1 不是新的发布编译阶段：strict canonical request 只声明 Manifest/P3 与可选 P9、P10.5c、
P10.6b、P10.7a、capture 和 decision 精确地址，reader 按声明调用现有只读 pure replay
compiler/validator 重建并验证 exact artifacts，再输出八个固定 checkpoint。这条冻结链只接受
P10.7a v1，不能把 P10.7a v2 skeleton/bundle SHA 送入。v1 Schema、哈希和
checkpoint 语义已经冻结，第八项仍固定为 missing；P10.7c 不反向扩写它。`null` 地址只产生
未声明原因；尤其 A 的空 P10.5c 地址不能被解释为 review head 为空。B 的四条不可观测关系则
来自精确 P3 candidate 的 replay evidence。

P10.7c 是独立的 exact-address、zero-write 比较边界。它用自己的 strict canonical request
同时锁定 comparison profile、显式 P3、P6 export/runtime golden 文件字节、P6 setup-only 双 SHA、
P10.7a 双 SHA 和 P10.7b capture 双 SHA；reader 必须证明两代 adapter 绑定同一 P3 且
atlas/texture 不变，再从 capture plan 中选出唯一 `animation=null/tick=0` 的 opaque setup PNG，
与 approved PNG 计算 RGBA 指标。report validator 只证明结构、派生字段与内容身份；gate binding
在内部从 exact P6/P10/capture/PNG 重新计算 sample 后才接受报告，调用者不能提供报告自己的
sample 冒充 replay。命令不启动 Runtime、不扫描 mutable head、不写 state、不修改 golden，
临时 stdout 只授予 bounded setup-frame equivalence，release gate 固定 blocked；readiness v2
之前还必须把 request/report、批准合同与批准 PNG 封存成可寻址、可重放的 immutable comparison
bundle。共享的 `wave-left-v1` 已到达 P7/P8、真实 A/B 各自的 P5、正式 depth policy、
depth candidates 与各自 exact replay 通过的历史 P9 reviewed-motion bundle。A revision 6 current chain 已重建到 P10.2，接受 CaptureFraming revision 1，完成 43/43 execution 与 P10.3c v2 revision 1，并闭合 current P10.5b/P10.5c 静态集；P10.4a v2 可将该 current visual head 准入后续安全分析。旧静态地址仍只供历史复验，current set/bundle 为 `00de666e…`/`e23e3792…`。B revision 16 必须沿自己的 current chain 重建；当前四条下肢关系 `unobservable` 不能自动降级完整合同。操作入口见
[P10.7c Setup Golden How-to](how-to-compare-spine42-v3-setup-golden.md)、
[就绪状态审计 How-to](how-to-audit-spine42-v3-readiness.md)和[后续开发路线](development-roadmap.md)。

后续 timeline/runtime 阶段继续遵守：

- motion contract：MotionInstance v3 的公开 compile 路径与 store trust boundary 都在待发布值构造前后重新检查两个 current head，不直接信任历史 admission/stdout；发布后按内容地址读回，历史 verify 不反向声明 current authority。
- setup：画布、原点、side 语义、draw order 和 region 合成回归通过。
- visual：除锚点代理外，完整 attachment 边界在固定动作与极值帧通过 raster/人工回归。
- runtime：目标 adapter 的能力矩阵明确，未支持特性 fail loud；产物不依赖伪造版本字段。
- provenance：输入、analysis、override revision、manifest、RigIR 和 probe 报告均能由哈希串联。
