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

exact Layer Manifest + exact P3 static bundle
                                      ↓
                P10.5a static seam candidates
                                      ↓
          P10.5b decision → P10.5c reviewed set
                                      ↓
                 P10.5d dynamic seam probe
                                      ↓
            P10.6a motion-consumer admission
                                       ↓
             P10.6b MotionInstance v3 bundle
                                       ↓
             P10.7a Spine 4.2 v3 bundle
                                       ↓
       [external] P10.7b Runtime/raster gate
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
- P9 UI 的读取与采纳边界分离。`POST /api/motion-policy/preflight` 仍是 zero-write Python application service：既有文件请求携带 `File.text()` 原文字符串，不先经 JavaScript parse/stringify；proposal 投影出的正式 policy 只序列化一次。`policy_identity` 对完整正式 policy 运行 inner strict decoder、validator 与 canonical SHA，`candidate_inventory` 对 standalone report 或正常 CLI envelope 解包后重算 policy/foot/depth 三 SHA、完整 candidate inventory 及 source/schedule/policy 交叉绑定，并把排序后 candidate ID 字符串清单的 canonical SHA 返回页面。页面只在身份、计数和该清单摘要全部一致时渲染表单。
- 一次最终 human adoption 通过 `POST /api/motion-policy/review-packages/{package_id}/adoptions` 进入写边界，并要求 `X-Autospine-Intent: motion-policy-adoption-v1`。Application service 只接受完整 package ID 与严格四字段 review input；它重新加载 exact package，不接受任意文件路径、shell 命令、客户端 P3/P5 地址或候选文档，随后复用既有 decision/policy compiler、ReviewedMotionBundleStore 与 exact reader。发布是内容寻址且可幂等复用；成功响应 path-free，并同时证明刚返回的 P9 双 SHA 已读回复验。HTTP adapter 继续负责 loopback/same-origin、JSON、大小、intent 与错误映射。下载 review input 只是备份，不参与服务端 authority；P9 adoption 也不授予 seam、Runtime、raster 或 release authority。
- P9→P10.5b 使用只读 `GET /api/motion-policy/review-packages/{package_id}/seam-review-entry`。Application service 从 package ID 重新加载 Foot/Depth exact package，验证共享 P3 来源，再由 VerifiedMeshBundleReader 重放 P3，并准备固定六关系 Seam candidate；客户端不能提交 Manifest/P3 SHA。响应只含 path-free 地址、candidate 身份、摘要和 blocker。该 handoff 不写 revision、不选择 locator、不自动 accept，手工四段地址只保留为专业审计 fallback。
- P10.0–P10.2 application service 只通过共享 exact-chain loader 读取七个完整 SHA 所选的 Layer Manifest/P3/P5/P9 工件。Candidate、人工 review input、decision 和 probe report 保持独立；三条 CLI 都不发布工件或修改 state tree。P10.3 visual-review service 改从 project/preview/bundle/artifact 四段地址重放 capture；prepare 零写入，只有通过 CAS 的 submit 才追加 candidate-bound revision。
- P10.4a admission command 重新编译 exact preview、重验 capture，并按 `history A → exact decision → history B` 观察当前 approved head。输出仅是 path-free compile-time 准入合同；它不持久化、不授予永久 authority，未来发布消费方必须重新读取当前 head。
- P10.4b1 amplitude-envelope command 只沿 reviewed 四骨幅度向量的统一 gain 射线重放九个 sampled key 状态；reviewed gain 必须精确匹配 P10.2 和临时 preview，分析结束后再次双快照 current head。候选不得包含 tracks/keys/animations，也不得声明连续时间、安全范围、seam 或发布 authority。
- P10.4b2 continuous-proof command 完整重放 P10.4b1 source closure，以向外舍入区间同时覆盖 `time_fraction × λ`；每一对相邻 preview tick 都必须进入共享有界预算。后端异常、预算耗尽、非有限数或证明对象不满足内部计数/边界不变量时 fail closed 为 `indeterminate`。全段通过只授予 preview-model structural claims，平台 libm/runtime、raster、seam、MotionInstance v3 与发布仍明确排除。
- P10.5a seam candidate command 只读取精确 Layer Manifest/P3 静态地址，固定输出六条左右关系和可回看的 attachment-local locator。candidate generator 内嵌从实际行为常量重建的 canonical algorithm profile；candidate、human decision、reviewed set 和动态 probe 是四个独立合同，任何一层都不能改写上一层 evidence hash。
- P10.5b/P10.5c 把人工 revision 与静态 ReviewedSet 分离；历史 bundle 可以精确复验，但只有 current ready head 能进入后续编译。P10.5d 不从 candidate 重新选 locator，也不把历史可读性升级为 current authority。
- P10.5d command 从完整 P10.4b2 proof 和精确 P10.5c 双 SHA 建立 source closure，在 pure analyzer 外执行 before/after current-head observation；每个 observation 内部又分别双快照视觉与接缝历史。全部 observation 只在 compile time 有效，consumer 必须重新检查。
- P10.5d analyzer 对六关系全部 reviewed pairs 覆盖相邻 tick 与统一 gain，只认证 `4 px²` reviewed-anchor point proximity 工程代理。region–region、region–mesh、mesh–region 有固定投影；mesh–mesh、预算耗尽、非有限包络、backend 自相矛盾和任何 head 漂移都 fail closed。attachment 边界、raster/视觉、runtime、timeline 和发布明确排除。
- P10.6a consumer admission 内嵌并完整重放 P10.5d probe，从其 source closure 读取精确 P9 双地址并复验 reviewed-motion bundle；pure core 只构造 unit-gain、setup-local、版本中立 motion domain，seal 前后重新观察视觉与接缝 current head。
- P10.6a 不发出 MotionInstance v3、adapter 或 Spine timeline。其内部与 CLI 外层 head observation scope 都固定为 `compile_time`；完整 attachment 边界、raster/视觉、runtime、publishable timeline 和 release authority 保持 blocked。
- Kimodo 的 raw NPZ、source sidecar 与 map 是三个独立输入。sidecar 解释数组/FPS/producer，map 决定投影/角色/contact；两者都不得根据文件名、数组数量或相邻目录隐式发现。

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

P3 门禁已经完成：四肢 attachment 的确定性 alpha mesh 与参数化两骨权重通过权重、拓扑、setup 和极值动作探针。安全角与代表性 PNG 进入不可变 bundle；不合格输入显式发布 `reviewed-noop`，不伪造 mesh。P3 工件保持版本中立。生产与复验入口分别为 `compile-mesh-rig`、`verify-mesh-bundle`；主工作台底部的“P3 Mesh 证据”只读回看精确双 SHA bundle。

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

正式测试证明确定性合成 NPZ 的 root、代表性肢体旋转和 contact 可通过三个 rig 的 P5/P6 结构门禁；M1.0 另证明同一六输入可得到确定性 path-free intake report，且其 P7 preview 身份可与后续正式编译对齐。真实运行的 `wave-left-v1` 已通过 intake，并完成 P7/P8、A/B P5 与各自 P9 reviewed-motion bundle 的 exact replay；身份集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)。这仍未证明 checkpoint authenticity、广泛动作质量、目标角色深度/遮挡效果、seam 或该 clip 的官方 Spine Player 截图。关闭真实资产门禁还需要 A 的 seam/P10.5 链、B 的上游修复或版本化 partial seam 合同、干净 state 重编译、目标角色视觉对照与固定 runtime golden。

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

Evidence 保留源事实，candidate 把证据绑定到一个精确目标 rig。进入人工表单前，Python preflight 先为正式 policy 返回 canonical identity，再重算 policy/foot/depth 三份 identity 与完整 candidate inventory；声明 SHA、P8/P5/P3 source、tick schedule、hysteresis、pair/slot/setup-front 任一不闭合都会 fail closed。Preflight 的 `passed` 只说明这组内存文档可进入当前页面，不是 decision、revision、reviewed policy 或 bundle 地址。Decision 仍必须由人对候选集逐项批准、拒绝或标记不可观测。Reviewed policy 才是 runtime 意图：foot root correction 显式编码 release/loop-reset，draw order 在全部帧上给出完整 slot permutation。Heading 和 scale 仍仅作 evidence，attachment switch 尚未实现。

MotionInstance v2 和 Spine adapter v2 是新能力边界；v1 instance、P8 evidence 及既有 P6 bundle 的内容哈希保持不变。Reviewed bundle 固定六文件 inventory，地址显式包含 project、MotionInstance v2 SHA 和 bundle SHA。严格 reader 从 run manifest 重放 exact P3/P5 上游，不使用 `latest`、目录扫描或替代 bundle 回退。

这一门禁关闭的是合同、provenance、内容寻址发布与 exact reader 重放的结构闭环，不是官方 runtime 或 raster truth。Preflight 只把候选展示边界收窄到 loopback Python 语义；最终 adoption 才调用服务端 decision/policy 编译、不可变 store 和 exact reader。CLI 使用相同领域边界，保留为专业复验与无浏览器流程，不再是普通页面确认后的手工交接步骤。P9 动态官方 runtime screenshot、seam 和真实作品质量门禁仍未关闭，不得由 preflight、adoption 成功、合成 fixture 或结构 audit 代替。操作入口见 [复核并发布 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

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

prepare 和 GET 只读重编 candidate；提交前不会发布 candidate，提交时才把 exact candidate 与 decision 写入各自内容地址。decision 历史以 candidate SHA 隔离，不提供 `latest`，同一输入的并发重试收敛，不同输入只允许一个 CAS winner。HTTP 图片证据还要求 candidate option、attachment 与 exact P3 source PNG SHA 同时匹配。操作入口见[复核 P10.5b 静态接缝锚点](how-to-review-seam-anchors.md)。

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

P10.6a 在不改变 P9、P10.4b2、P10.5c 或 P10.5d hash 语义的前提下建立消费入口：

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

P10.6b 已在实际消费时重新检查 visual/seam current head，并把上述 motion domain 编译为
可严格重放的 MotionInstance v3/timeline bundle。固定库存为 admission、v3 与 run；发布使用
v3/bundle 双 SHA，无 `latest`。MIv2 root translation、markers 与 stepped draw order 原样保留，
rotation overlay 只允许躯干四骨。历史 reader 不观察 current head，因此只证明当时发布的字节
可重放。store 在创建 publication parent 前独立执行 before → contract → after 门禁，公开命令
发布后再按精确地址读回；run 的 authority 只开放 MotionInstance v3 emitted，release gate 固定
blocked。admission 独立上限为 64 MiB。

P10.7a 以 project 与 MIv3 双 SHA 作为公开输入，严格重放 MIv3→P9→P5/P3→RigIR/源 PNG，
再用独立 adapter profile `3.0.0` 生成固定 Spine 4.2 JSON、atlas 与 PNG。五文件 bundle 使用
独立 `spine42-v3/<skeleton-sha>/<bundle-sha>` 地址空间；store 和公开命令均执行 current-head
门禁，发布后 exact reader 会从完整上游逐字节重建。旧 P6 profile/hash 不变，未知能力 fail
loud。run 只开放 adapter emitted，官方 Runtime/raster、永久 head、publishable timeline 和
release authority 均保持 blocked。

P10.7b 用固定官方 Runtime/浏览器身份、case plan、完整 setup attachment isolate 与 sampled
raster 指标形成不可变 capture；candidate 和完整 human decision 保持分离。其后的 readiness
v1 不是新的发布编译阶段：strict canonical request 只声明 Manifest/P3 与可选 P9、P10.5c、
P10.6b、P10.7a、capture 和 decision 精确地址，reader 按声明调用现有只读 pure replay
compiler/validator 重建并验证 exact artifacts，再输出八个固定 checkpoint。v1 Schema、哈希和
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
depth candidates 与各自 exact replay 通过的 P9 reviewed-motion bundle。P9 成功仍不能写成 seam 或真实样本通过：A 下一步进入真实 seam 人审与 P10.5c，B 的四条下肢关系不可观测，在修复分层/语义或建立版本化 partial 合同前仍被阻塞；两者之后还需要官方 capture。操作入口见
[P10.7c Setup Golden How-to](how-to-compare-spine42-v3-setup-golden.md)、
[就绪状态审计 How-to](how-to-audit-spine42-v3-readiness.md)和[后续开发路线](development-roadmap.md)。

后续 timeline/runtime 阶段继续遵守：

- motion contract：MotionInstance v3 的公开 compile 路径与 store trust boundary 都在待发布值构造前后重新检查两个 current head，不直接信任历史 admission/stdout；发布后按内容地址读回，历史 verify 不反向声明 current authority。
- setup：画布、原点、side 语义、draw order 和 region 合成回归通过。
- visual：除锚点代理外，完整 attachment 边界在固定动作与极值帧通过 raster/人工回归。
- runtime：目标 adapter 的能力矩阵明确，未支持特性 fail loud；产物不依赖伪造版本字段。
- provenance：输入、analysis、override revision、manifest、RigIR 和 probe 报告均能由哈希串联。
