# AutoSpine Workbench 架构与质量门禁

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
              resolved project snapshot
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
                    P10.2 sampled body-sway report
                                      ↓
                 deterministic Spine 4.2 preview
                                      ↓ licensed official runtime
                     P10.3 immutable still capture
                                      ↓ exact-address human CAS
                    sampled visual decision history
                                      ↓
                P10.4a double-snapshot admission
                                      ↓
              P10.4b1 sampled gain candidates
                                      ↓
          P10.4b2 bounded continuous interval proof
                                      ↓
                           blocked release

server → application services only
web    → HTTP contracts only
```

- `project_store.py` 只保留发现项目和协调 application service 的 façade 职责，不再承载分析算法、持久化实现或 Rig 编译。
- `server.py` 负责 HTTP、输入大小、loopback 安全和错误映射，不实现领域规则。
- 前端分为 API、authoring state、保存事务和各 stage view；view state 不得污染 revision draft。
- 外部姿态模型只能通过 canonical pose observations 进入；alpha 几何只读取 resolved layer 与固定 PNG，融合结果必须保留原始 pose 和未标定分数语义。
- COCO17 raw 输入、adapter、canonical pose、人工评估和候选工件分开内容寻址；坐标反镜像、左右标签交换、视角和镜像声明不得合并成一个隐式开关。
- 离线命令按 stage 边界拆分：P1 输入/候选、P2 manifest/RigIR、P3 mesh、P4 IK、P5 MotionIR、P6 目标版本 adapter、P7 Kimodo source adapter、P8 camera/projected evidence、P9 reviewed motion/bundle，以及 P10 idle probe/runtime capture/visual review/review admission 分别拥有显式入口；命令之间只传递精确内容地址，不解析 `latest`。
- P10.0–P10.2 application service 只通过共享 exact-chain loader 读取七个完整 SHA 所选的 Layer Manifest/P3/P5/P9 工件。Candidate、人工 review input、decision 和 probe report 保持独立；三条 CLI 都不发布工件或修改 state tree。P10.3 visual-review service 改从 project/preview/bundle/artifact 四段地址重放 capture；prepare 零写入，只有通过 CAS 的 submit 才追加 candidate-bound revision。
- P10.4a admission command 重新编译 exact preview、重验 capture，并按 `history A → exact decision → history B` 观察当前 approved head。输出仅是 path-free compile-time 准入合同；它不持久化、不授予永久 authority，未来发布消费方必须重新读取当前 head。
- P10.4b1 amplitude-envelope command 只沿 reviewed 四骨幅度向量的统一 gain 射线重放九个 sampled key 状态；reviewed gain 必须精确匹配 P10.2 和临时 preview，分析结束后再次双快照 current head。候选不得包含 tracks/keys/animations，也不得声明连续时间、安全范围、seam 或发布 authority。
- P10.4b2 continuous-proof command 完整重放 P10.4b1 source closure，以向外舍入区间同时覆盖 `time_fraction × λ`；每一对相邻 preview tick 都必须进入共享有界预算。后端异常、预算耗尽、非有限数或证明对象不满足内部计数/边界不变量时 fail closed 为 `indeterminate`。全段通过只授予 preview-model structural claims，平台 libm/runtime、raster、seam、MotionInstance v3 与发布仍明确排除。
- Kimodo 的 raw NPZ、source sidecar 与 map 是三个独立输入。sidecar 解释数组/FPS/producer，map 决定投影/角色/contact；两者都不得根据文件名、数组数量或相邻目录隐式发现。

## 文件长度预算

生产源码的硬上限为 400 个物理行。新文件超过 300 行时就应评估按职责拆分；函数通常不超过 60 行，超过 100 行必须先拆解或在评审中记录理由。

当前四个历史单体采用 ratchet：只允许缩短，不允许超过测试中记录的当前上限。

| 文件 | 当前上限 | 拆分目标 |
| --- | ---: | ---: |
| `web/styles.css` | 1713 | 每个主题/布局文件 ≤ 400 |
| `web/app.js` | 1293 | façade ≤ 250，模块 ≤ 400 |
| `src/autospine_workbench/project_store.py` | 838 | façade ≤ 300 |

`tests/test_quality.py` 自动执行上述硬上限与 ratchet；P10 新增生产模块与 visual-review JS test 文件另有 300 行硬门禁。JSON Schema、文档和生成工件不套用源码行数上限，但仍应按版本和领域拆分，禁止手工复制生成文件来规避检查。

## 变更与提交

1. 先写失败测试或可重现 fixture。
2. 一次提交只完成一个可回滚能力；合同迁移与消费方更新可以同提交，但不要夹带格式化全库。
3. 每阶段运行完整单元测试；涉及图像或动画时额外保存固定视角、固定时间点的数值报告和代表性截图。
4. schema 通过只证明结构合法；跨引用、权重和骨架拓扑必须再经过语义验证器。
5. 任何迁移先读旧格式并产出新格式，经过至少一个发布周期后再讨论删除兼容路径。

## 阶段门禁

P1 已完成并冻结以下边界：

- pose、alpha path/contact geometry 和 joint candidates 分别内容寻址，候选 fragment 在首次发布前绑定真实 geometry SHA 与目标。
- 比较 UI 可以接受、调整、拒绝或标记不可观测，并按固定 SHA 回看几何证据；算法变化不会静默复用旧决定。
- 两份 See-through 样本可用 diagnostic setup prior 重复发布相同工件链；该 smoke 明确不代表模型精度。
- candidate/geometry API 在读取时重新验证 strict JSON、内容地址、project 和领域合同，损坏输入 fail closed。

P2 门禁已经完成：reviewed Layer Manifest → region-only RigIR；FK setup 精确重建，pivot、父子关系、draw order、完整 bundle inventory 与两份真实视觉 golden 均已通过。P2 不生成 mesh 或权重。

图层复核按字段记录 provenance；`visible`、语义、side、pivot、disposition 与目标骨互不代替。RigIR bundle 地址固定为 `builds/<project-id>/rig-ir/<rig-sha256>/<bundle-sha256>/`，第二层哈希同时绑定 RigIR、编译 run manifest、probe report 与 setup-render 合同，runner/renderer/encoder 变化不会改写旧证据。完整 verifier 还校验 region PNG 原始字节、规范路径和 exact inventory。`allow_manual_required` 只用于诊断，不能关闭阶段门禁。

P3 门禁已经完成：四肢 attachment 的确定性 alpha mesh 与参数化两骨权重通过权重、拓扑、setup 和极值动作探针。安全角与代表性 PNG 进入不可变 bundle；不合格输入显式发布 `reviewed-noop`，不伪造 mesh。P3 工件保持版本中立。

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

producer provenance 的 `recorded` 与 `unavailable` 是不同的显式状态。即使记录了外部 manifest/request 的 SHA，本仓库也只绑定 metadata，不认证 checkpoint 或生成请求本身；操作者必须另行保留原件。完整 NPZ 只把 `smooth_root_pos` 当有限数证据、把 `global_root_heading` 当单位方向证据，当前不用它们改写 MotionIR。contact 采用半开 `annotation_only` marker，不等于 foot lock。

正式测试证明确定性合成 NPZ 的 root、代表性肢体旋转和 contact 可通过三个 rig 的 P5/P6 结构门禁；它尚未证明真实 Kimodo checkpoint 的动作质量、深度/遮挡效果或该 clip 的官方 Spine Player 截图。关闭真实资产门禁还需要 recorded provenance、干净 state 重编译、目标角色视觉对照与固定 runtime golden。

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
exact P8 evidence + exact P5 target + exact P3 mesh
                         ↓
             foot-lock/depth-order candidates
                         ↓
             exhaustive human policy decision
                         ↓
                  reviewed motion policy
                         ↓
          MotionInstance v2 → Spine 4.2 v2 preview
                         ↓
        six-document immutable reviewed-motion bundle
```

Evidence 保留源事实，candidate 把证据绑定到一个精确目标 rig，decision 必须对候选集逐项批准、拒绝或标记不可观测。Reviewed policy 才是 runtime 意图：foot root correction 显式编码 release/loop-reset，draw order 在全部帧上给出完整 slot permutation。Heading 和 scale 仍仅作 evidence，attachment switch 尚未实现。

MotionInstance v2 和 Spine adapter v2 是新能力边界；v1 instance、P8 evidence 及既有 P6 bundle 的内容哈希保持不变。Reviewed bundle 固定六文件 inventory，地址显式包含 project、MotionInstance v2 SHA 和 bundle SHA。严格 reader 从 run manifest 重放 exact P3/P5 上游，不使用 `latest`、目录扫描或替代 bundle 回退。

这一门禁关闭的是合同、provenance、发布与 loader-isomorphic audit 的结构闭环，不是官方 runtime 或 raster truth。P9 动态官方 runtime screenshot 和真实 Kimodo reviewed asset fixture 门禁仍未关闭，不得由合成 fixture 或结构 audit 代替。操作入口见 [复核并发布 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

P10.0–P10.2 已完成只读 idle 行为候选、人工决定和 body-sway 采样结构诊断边界：

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
                                  ↓
       structural_rejected | manual_visual_required
                                  ↓
                  release gate always blocked
```

P10 exact loader 接受 Layer Manifest、P3 rig/bundle、P5 MotionInstance/bundle 与 P9 MotionInstance v2/bundle 七个完整 SHA，重放 P9 合同，不扫描目录或回退到 `latest`。Candidate compiler 固定列出 blink、body sway、hair spring、mouth；当前只有完整 canonical 躯干链能产生 body-sway candidate。Decision 必须绑定 exact candidate，且 body-sway 只有带人工参数的 `adjust` 才能保持 `pending_probe` 并进入探针。

`BodySwayProbeReport v1` 固定检查 `loop_closure`、`fk_finite`、`sampled_mesh_deformation`、`sampled_canvas_containment`、`shared_index_internal_continuity`、`inter_attachment_seams` 与 `visual_quality`。前五项是采样结构证据；无 mesh 或非 loop 会显式 `not_applicable`。接缝缺少 reviewed anchors，视觉质量需要官方 runtime 人工预览，因此后两项保持 `unobservable`，顶层 release gate 无条件 blocked。

代表性 `sample_sha256` 包含 tick；loop 端点比较使用不含 tick 的独立 pose-state domain，再封入 loop check evidence。Bulk evidence digest 是 compiler seal，不是独立重放载荷。该边界不产生 MotionInstance v3 或 runtime timeline，也不声明连续时间、幅度安全范围、接缝、raster truth 或视觉通过。操作入口见 [复核 idle 行为并运行 body-sway 结构探针](how-to-review-idle-behaviors.md)。

P10.3a–P10.3c 在结构探针之后增加官方 runtime sampled-still 证据与人工 revision，但仍不跨越 release 边界：

```text
exact P10 candidate + decision + manual_visual_required probe
                                  ↓ deterministic temporary compile
               Spine 4.2 preview + fixed capture plan
                                  ↓ licensed official 4.2.119 runtime
                  immutable 640×640 PNG capture bundle
                                  ↓ exact project / preview / bundle / artifact
                   read-only visual candidate compiler
                                  ↓ exhaustive human case decisions
               candidate-bound linear revision + strict CAS
                                  ↓
          sampled_visual_approved | sampled_visual_rejected
                                  ↓
                  release gate always blocked
```

真实 capture 的外部信任前置条件是操作者提供并确认授权的官方 `@esotericsoftware/spine-player@4.2.119`。仓库不下载或再分发 runtime；test-only `SpinePlayer` stub 只覆盖 Chrome 进程、loopback 与 PNG 通路，不能进入真实视觉证据链。Capture 地址由 project ID、temporary preview SHA、runtime capture bundle SHA 和 capture artifact-set SHA 四项组成。Application service 从这四项重放 authoritative capture 并确定性编译 candidate；CLI 与 HTTP 都复用同一服务，不扫描目录或解析 `latest`。

Prepare/candidate/history/exact-decision 是零写入读路径。首次提交才会发布 exact candidate，并在 candidate SHA 命名空间下同时写入内容寻址 decision 和连续 revision slot。提交 payload 只包含人工 review、逐 case action/evidence 绑定，以及 `base_revision`/`previous_decision_sha256`；revision 和其他 authority 字段由服务重建。CAS 拒绝 stale head、跳号和并发 slot 抢占，字节相同的安全重试可复用现有 decision。历史最多 64 项，读取任意 decision 前都会重放完整前驱链。

HTTP 投影不返回本地路径。图片只能经 candidate 的 case/evidence/PNG SHA 读取；decision mutation 还要求完全同 authority 的 loopback Origin、JSON content type 和显式 intent header。独立 UI 不自动选择 capture、历史 revision 或 head 基线；409 会清除旧历史/基线并保留草稿，要求操作者重新读取后显式确认新 head。详细操作与路由见[复核 body-sway 官方 runtime 采样帧](how-to-review-body-sway-runtime.md)。

`sampled_visual_approved` 只表示固定 still inventory 全部获人工批准。它不声明离散帧之间的连续时间、reviewed seam anchors、安全幅度、未采样姿势或可发布 timeline，因此 release gate 仍固定为 blocked；reject/unobservable 还会增加明确的 sampled rejection reason。

P10.4a–P10.4b2 把 current visual head 准入、离散 gain candidates 和连续预览模型证明拆成三层只读合同：

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

连续证明内嵌并重算 candidate、RigIR、target profile、MotionInstance v2、temporary preview manifest 与 preview projection。固定后端包围数学三角函数、Q9 图层与 Q4096 顶点量化误差，并检查 FK、画布、mesh area/edge 与共享索引内部连续性；它不把 point samples 当作区间证明。输入和结果都有显式 byte/box/depth 上限，任何未证明状态都不能升级为通过。操作入口见[编译 body-sway 连续预览模型证明](how-to-compile-body-sway-continuous-proof.md)。

该结论只适用于固定 preview 数学模型，不代表目标平台 `libm`、官方 Spine runtime 或 raster truth；attachment 间 seam 仍缺少 reviewed anchors。静态 seam candidate、人工 decision 和 reviewed anchor set 应作为独立上游合同，之后才能在相同动作域上追加 seam 证明，不能修改本阶段既有 hash 语义。

后续阶段继续遵守：

- setup：画布、原点、side 语义、draw order 和 region 合成回归通过。
- visual：抬臂、屈肘、抬腿、屈膝探针在极值帧无明显断层、翻三角或越界。
- runtime：目标 adapter 的能力矩阵明确，未支持特性 fail loud；产物不依赖伪造版本字段。
- provenance：输入、analysis、override revision、manifest、RigIR 和 probe 报告均能由哈希串联。
