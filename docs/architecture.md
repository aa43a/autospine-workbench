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

server → application services only
web    → HTTP contracts only
```

- `project_store.py` 只保留发现项目和协调 application service 的 façade 职责，不再承载分析算法、持久化实现或 Rig 编译。
- `server.py` 负责 HTTP、输入大小、loopback 安全和错误映射，不实现领域规则。
- 前端分为 API、authoring state、保存事务和各 stage view；view state 不得污染 revision draft。
- 外部姿态模型只能通过 canonical pose observations 进入；alpha 几何只读取 resolved layer 与固定 PNG，融合结果必须保留原始 pose 和未标定分数语义。
- COCO17 raw 输入、adapter、canonical pose、人工评估和候选工件分开内容寻址；坐标反镜像、左右标签交换、视角和镜像声明不得合并成一个隐式开关。
- 离线命令按 stage 边界拆分：P1 输入/候选、P2 manifest/RigIR、P3 mesh、P4 IK、P5 MotionIR 与 P6 目标版本 adapter 分别拥有显式编译和只读验证入口；命令之间只传递精确内容地址，不解析 `latest`。

## 文件长度预算

生产源码的硬上限为 400 个物理行。新文件超过 300 行时就应评估按职责拆分；函数通常不超过 60 行，超过 100 行必须先拆解或在评审中记录理由。

当前四个历史单体采用 ratchet：只允许缩短，不允许超过测试中记录的当前上限。

| 文件 | 当前上限 | 拆分目标 |
| --- | ---: | ---: |
| `web/styles.css` | 1713 | 每个主题/布局文件 ≤ 400 |
| `web/app.js` | 1293 | façade ≤ 250，模块 ≤ 400 |
| `src/autospine_workbench/project_store.py` | 838 | façade ≤ 300 |

`tests/test_quality.py` 自动执行上述硬上限与 ratchet。JSON Schema、文档和生成工件不套用源码行数上限，但仍应按版本和领域拆分，禁止手工复制生成文件来规避检查。

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

后续阶段继续遵守：

- setup：画布、原点、side 语义、draw order 和 region 合成回归通过。
- visual：抬臂、屈肘、抬腿、屈膝探针在极值帧无明显断层、翻三角或越界。
- runtime：目标 adapter 的能力矩阵明确，未支持特性 fail loud；产物不依赖伪造版本字段。
- provenance：输入、analysis、override revision、manifest、RigIR 和 probe 报告均能由哈希串联。
