# AutoSpine Workbench 功能与入口参考

本文是面向操作者和开发者的 Reference。它回答“功能是否已经实现、从哪里进入、会得到什么”，不替代具体操作步骤。P0 Resolved Project v1、P10.6b MotionInstance v3、P10.7a Spine 4.2 v3 adapter bundle、P10.7b sampled raster 基础设施与独立 P10.7c setup regression 已完成；当前开发入口是 **P9-real-kimodo-candidate-review**。`wave-left-v1` 已完成 intake、P7/P8、真实 A/B 各自的 P5 exact replay、正式 depth policy 与候选交叉预检；P9 页面已能自动选择/加载 exact package、重算身份，并通过时间轴或一键操作辅助采用安全 Foot 建议。当前仍须为 A/B 分别完成最终 human adoption、发布 P9，并关闭 seam 与官方 capture blocker。计划项见[开发路线](development-roadmap.md)。

## 统一入口

启动服务后打开：

- [功能入口中心](http://127.0.0.1:8765/workflow-hub.html)：按阶段、入口类型和状态搜索全部功能；
- [绑定复核工作台](http://127.0.0.1:8765/)：图层、拆分、关节、候选和 P3 证据复核；
- [Body-sway 视觉复核台](http://127.0.0.1:8765/body-sway-review.html)：P10.3c sampled still 复核；
- [Seam Anchor 复核台](http://127.0.0.1:8765/seam-anchor-review.html)：P10.5b 静态接缝锚点复核；
- [Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html)：P9 项目/package 自动加载、安全 Foot 辅助采用、异常处理与最终人工采纳。

功能入口中心读取 [`web/workflow-catalog.json`](../web/workflow-catalog.json)，列出 65 个已注册 CLI、四个任务页面和尚未实现的计划项。对于 CLI，它只复制 `python -B -m autospine_workbench <command> --help` 帮助命令，不在浏览器或服务端执行命令；源码模式下须先在当前 PowerShell 执行 `$env:PYTHONPATH = (Resolve-Path .\src).Path`，再复制和运行帮助命令。文档卡片通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开；查看器只读获取 `/docs/<文件名>.md`，不能访问目录外文件，并把响应作为纯文本显示，不解析 HTML 或执行文档内容。

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
| 图层浏览与 QA | “图层”模式、图层列表和 QA 面板 | 搜索、显隐、语义、左右、bbox、空层及合成差异 |
| 图层 authoring | 右侧图层编辑器 | 语义、side、disposition、setup 可见性、pivot、目标骨和备注 |
| 双侧切分复核 | 右侧“切分预览审查” | 接受或拒绝精确 split artifact；算法变化使旧决定 stale |
| 关节校正 | “关节”模式和坐标编辑器 | 拖动、数值输入、键盘微调、恢复自动位置 |
| 四肢候选比较 | 右侧“候选审查” | accept、adjust、reject、unobservable；证据按 SHA 回看 |
| P3 Mesh 证据 | 页面底部“P3 Mesh 证据” | 显式选择 rig/bundle SHA 后只读重验；不是权重编辑器 |
| Revision 保存 | “保存校正”或 `Ctrl+S` | override v3、CAS、append-only history、409 草稿恢复 |

### Body-sway 视觉复核台

以 project、temporary preview、runtime capture bundle 和 artifact set 四段地址读取官方 Spine Runtime 固定帧。每个 case 可标记 `approve`、`reject` 或 `unobservable`，并通过 CAS 追加不可变 revision。全部批准只得到 `sampled_visual_approved`，不证明连续时间、完整接缝、runtime 等价或发布安全。

### Seam Anchor 复核台

以 Layer Manifest SHA、P3 rig SHA 和 P3 bundle SHA 读取左右六条静态接缝关系。每条关系可 `accept`、`adjust`、`reject` 或 `unobservable`；`adjust` 保存最终 locator 对。全量 accept/adjust 只得到 `reviewed_anchor_set_ready_for_compile`，仍须经过 P10.5c 与 P10.5d。

### Motion Policy 复核台

普通模式先从只读 package API 列出本地项目/动作；存在推荐项时自动选择，并按 exact package ID 加载正式 policy、Foot/Depth reports。package ID 绑定项目、动作、clip、三份报告身份和 candidate inventory，不按文件名、mtime 或 `latest` 推测。服务端重算 package 身份，页面随后再用 loopback-only、zero-write Python `candidate_inventory` 复验 source、schedule、policy/depth 交叉绑定与 `candidate_ids_sha256`。通过后，证据模型按时间排序 Foot samples，显示曲线、重点窗口和角色足点。

启用时间轴辅助采用时，一次拖动会把经过范围内尚未决定且满足当前规则的安全 Foot candidates 作为一个可撤销事务写入草稿；“一键采用”覆盖其余安全 Foot。安全规则固定要求 Foot `state=candidate`、observations 完整且数值有限、correction ratio 与 residual 均不超过各自合同上限的 80%。辅助决定带来源，不覆盖现有人工或批量决定。Depth、`rejected_limit`、`rejected_conflict`、缺证、非有限值、超阈值和 `adjust` 不自动批准，仍进入异常区；重点窗口只是边界/极值/p95 等视觉提示，不单独排除候选。只有 100% 覆盖、全局字段合法并由操作者执行一次最终采用后，页面才下载逐 candidate 展开的严格四字段 review input。该最终动作是 Motion Policy Decision v1 的 human adoption；页面不保存 revision、不发布 P9，也不提供零点击发布。

“专业模式”保留 proposal 批准、三文件与声明 SHA 手工导入，用于外部副本审计和身份排障。它使用与普通模式相同的 Python preflight 与最终采纳门禁。

## CLI 功能

先在项目根目录设置源码路径：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench --help
python -B -m autospine_workbench <command> --help
```

下表与当前 CLI parser 的 65 个命令一一对应。具体必填 SHA、文件路径和外部前置条件以各命令 `--help` 及链接的 how-to 为准。

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

### P9：Reviewed Motion

| 命令 | 功能 |
| --- | --- |
| `compile-kimodo-policy-evidence` | 从精确 P7/P8 编译不含人工决定的策略证据 |
| `compile-heading-evidence` | 通过显式 policy map 编译 heading evidence |
| `probe-foot-lock` | 报告只供人工复核的 foot-lock 候选 |
| `probe-depth-order` | 报告只供人工复核的 pairwise depth-order 候选 |
| `compile-motion-policy-decision` | 将显式人工选择绑定到精确候选报告 |
| `compile-reviewed-motion-policy` | 将已批准决定编译为版本中立 root/draw-order policy |
| `compile-motion-instance-v2` | 将 reviewed policy 应用到精确 P5 instance |
| `export-spine42-v2` | 只读构建 reviewed motion 的 Spine 4.2 v2 export report |
| `publish-reviewed-motion-bundle` | 发布 MotionInstance v2 六文件 bundle |
| `verify-reviewed-motion-bundle` | 重放精确 P9 reviewed-motion bundle |

操作说明：[复核 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

### P10.0–P10.4：Idle 与 Body-sway

| 命令 | 功能 |
| --- | --- |
| `compile-idle-behavior-candidates` | 从精确 P3/P5/P9 编译 idle 行为候选 |
| `compile-idle-behavior-decision` | 将人工 review 绑定到精确 idle 候选 |
| `compile-body-sway-probe` | 生成七项 sampled body-sway 结构诊断 |
| `compile-body-sway-preview` | 在内存中生成不具发布权的临时 Spine 4.2 preview |
| `capture-body-sway-runtime` | 用操作者提供且已授权的 Spine Runtime 捕获并封存证据 |
| `prepare-body-sway-visual-review` | 按精确 capture 地址准备 sampled still 人工复核 |
| `submit-body-sway-visual-review` | 提交覆盖全部 case 的 visual-review revision |
| `compile-body-sway-review-admission` | 准入当前 approved visual head 供后续分析 |
| `compile-body-sway-amplitude-envelope` | 沿统一 gain 生成九档 sampled 候选 |
| `compile-body-sway-continuous-proof` | 对 sampled-linear preview 的单位 gain 区间作有界证明 |

操作说明：[Idle/body-sway](how-to-review-idle-behaviors.md)、[临时预览与视觉复核](how-to-review-body-sway-runtime.md)、[Runtime 捕获](how-to-capture-body-sway-runtime.md)、[连续证明](how-to-compile-body-sway-continuous-proof.md)。

### P10.5：接缝锚点

| 命令 | 功能 |
| --- | --- |
| `compile-seam-anchor-candidates` | 从精确 Layer Manifest/P3 静态链编译六条接缝候选 |
| `prepare-seam-anchor-review` | 准备固定六关系的静态接缝证据 |
| `submit-seam-anchor-review` | 提交覆盖六关系的人工 review revision |
| `compile-reviewed-seam-anchor-set` | 将 current ready head 发布为 reviewed seam set bundle |
| `verify-reviewed-seam-anchor-set` | 只读复验一个精确历史 seam set bundle |
| `compile-body-sway-dynamic-seam-probe` | 覆盖全部相邻 tick 和统一 gain 的 reviewed-anchor 点距代理 |

操作说明：[接缝候选](how-to-compile-seam-anchor-candidates.md)、[人工复核](how-to-review-seam-anchors.md)、[Reviewed Set](how-to-compile-reviewed-seam-anchor-set.md)、[动态探针](how-to-probe-body-sway-dynamic-seams.md)。

### P10.6a：动作消费者准入

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-motion-consumer-admission` | 重放认证 P10.5d/P9 链并产生零写入 setup-local timeline 消费准入 |

操作说明：[编译 P10.6a 准入](how-to-compile-body-sway-motion-consumer-admission.md)。准入本身不包含 MotionInstance v3、Spine timeline、runtime 等价或发布权；它是 P10.6b compile 命令的严格输入。

### P10.6b：MotionInstance v3

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-motion-instance-v3` | 命令/store 双重查 current heads，把完整 P10.6a 成功 wrapper 原子发布为三文件 v3 bundle，并按地址读回 |
| `verify-body-sway-motion-instance-v3` | 按精确 v3/bundle 双 SHA 重编历史 bundle，不声明 current-head authority |

操作说明：[编译并复验 P10.6b MotionInstance v3](how-to-compile-motion-instance-v3.md)。admission 上限为 64 MiB；run 只授予 MotionInstance v3 emitted，release gate 仍 blocked。输出是版本中立 setup-local timeline；P10.7a 会显式消费它。

### P10.7a：Spine 4.2 v3 Adapter Bundle

| 命令 | 功能 |
| --- | --- |
| `compile-body-sway-spine42-v3` | 从精确 MIv3 双 SHA 重放 P9/P5/P3，在 current-head 门禁下发布五文件 Spine 4.2 v3 bundle，并按地址读回 |
| `verify-body-sway-spine42-v3` | 按 skeleton/bundle 双 SHA 重建完整上游和五文件历史产物，不读取 current heads |

操作说明：[编译并复验 P10.7a Spine 4.2 v3](how-to-compile-spine42-v3.md)。run 只授予 `spine_adapter_emitted`；官方 Runtime、raster、永久 head、publishable timeline 和 release authority 仍为 false/blocked。P10.7b 必须从这个精确地址开始。

### P10.7b：官方 Runtime 与 Sampled Raster 证据

| 命令 | 状态 | 功能 |
| --- | --- | --- |
| `capture-body-sway-spine42-v3-runtime` | `external_required` | 用操作者提供并确认有权使用的官方 Spine Player 4.2.119 与本机 Chrome，捕获固定 case 的 composite 和全部 setup attachment isolate，计算 sampled raster 指标并发布不可变 evidence |
| `verify-body-sway-spine42-v3-runtime` | `available` | 按 P10.7a/capture 双 SHA 复验目录库存、PNG、metrics、manifest 与精确 P10.7a 来源 |
| `prepare-body-sway-spine42-v3-raster-review` | `available` | 从精确 capture 只读编译逐 case、逐 attachment 的 candidate，不作人工批准声明 |
| `submit-body-sway-spine42-v3-raster-review` | `available` | 将覆盖全部 candidate 行的显式人工输入编译为 path-free decision；不发布 revision 或 release authority |
| `audit-body-sway-spine42-v3-readiness` | `available` | 用只读 pure replay compiler/validator 复验 strict canonical 请求中的精确地址并报告八个 checkpoint；不扫描 latest/current review head，也不运行外部阶段、Runtime、发布或写入 |

capture manifest 会记录 runtime JS/CSS、`package.json`、`LICENSE`、浏览器、capture plan、P10.7a 来源与 PNG 摘要。`LICENSE` 文件存在不等于已经取得授权，许可确认仍由操作者负责。

指标只以 `alpha >= 1` 的二值掩码比较捕获计划内 transparent composite 与 attachment isolate union，并检查 missing/extra/xor、边界、裁切和非空 isolate。人工 decision 只覆盖同一组 sampled case 与 setup attachment inventory。两者都不证明未采样时间、连续 runtime raster safety、永久 current-head authority、publishable timeline 或 release authority；release gate 始终 blocked。

操作说明：[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)、[审计两份真实样本的 Spine 4.2 v3 就绪状态](how-to-audit-spine42-v3-readiness.md)。公开结构见 [request Schema](../schemas/spine42-v3-readiness-request-v1.schema.json) 与 [report Schema](../schemas/spine42-v3-readiness-report-v1.schema.json)；Schema 不替代 canonical/self-hash/dependency 的 Python 语义 validator。readiness v1 已冻结，第八项仍固定为 `p6_setup_golden_comparison_not_declared`。新增 P10.7c 不修改该合同；有效审计只说明本次显式地址的 preflight 结果，不等于 setup golden 对照或发布权。

当前示例请求没有声明两项目的 P9 exact 地址。A 的 P3 candidate 六条 seam 均可观测，但其 P10.5c 地址为 `null`，所以审计只能报告 `reviewed_seam_anchor_set_address_not_declared`；它没有读取 current review head，不能声称 head 为空。B 的 P3 candidate pure replay 则证明左右 pelvis-leg 与 leg-foot 共四条关系不可观测，必须修复上游语义/分层或另立版本化 partial 合同。官方 Runtime 已存在，但位于这些更早 blocker 之后；结构 fixture 不能替代真实样本验收。

### P10.7c：P6 Setup Golden 独立回归

| 命令 | 状态 | 功能 |
| --- | --- | --- |
| `compare-body-sway-spine42-v3-setup-golden` | `available` | 锁定 comparison profile、显式 P3、P6 export/runtime golden 合同和精确 P10.7a/P10.7b 地址，重放后只读比较唯一 opaque setup 帧 |

操作说明：[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。请求与报告分别使用独立的 `spine42-v3-setup-regression-*-v1` Schema；report/sample 自哈希只是内容身份，命令的 gate 会从 exact P6/P10/capture/PNG 在内部重新计算并绑定 sample。命令不会运行 Runtime、扫描 `latest`/current head、写入 state 或修改 approved PNG；stdout 报告临时且不可寻址，readiness v2 前仍需 immutable comparison bundle。`passed` 只表示固定 setup 帧在批准阈值内，不证明动画 case、连续时间安全、永久审批或发布权。共享的 `wave-left-v1` 已有 P7/P8 与真实 A/B 各自的 P5，但当前仍缺各自 P9、seam、P10.7a 与 capture 地址，尚无真实 P10.7c 通过结论。

## HTTP 写入边界

P9 页面使用两个只读 package GET 和一个严格的 zero-write POST：

| 方法与资源 | 只读计算 | 安全边界 |
| --- | --- | --- |
| `GET /api/motion-policy/review-packages` | 发现固定文件名的本地 exact review package，重算身份并返回确定性的推荐 package ID | loopback-only；响应 path-free，不扫描下载目录、不按 mtime 选 `latest`，不批准或发布 |
| `GET /api/motion-policy/review-packages/{package_id}` | 按完整 package ID 读取正式 policy、Foot/Depth reports 和预检 inventory | exact ID 必须绑定项目、动作、clip、三份报告 SHA 与 candidate inventory；损坏或变化时 fail closed |
| `POST /api/motion-policy/preflight` | 从原始 JSON 文本运行 inner strict decoder；`policy_identity` 返回 Python canonical SHA，`candidate_inventory` 解包受支持 envelope 后重算 policy/foot/depth 三 SHA、完整 standalone 合同、交叉绑定、四项计数及候选 ID 清单 SHA | loopback + exact same-origin、JSON、`X-Autospine-Intent: motion-policy-preflight-v1`；外层 48 MiB、内层 policy/foot/depth 1/16/16 MiB；不读路径、不写 state、不批准或发布 |

POST 在这里只用于承载有界完整 JSON 文档，不代表 mutation。本地 HTTP 服务仍只有三类写操作：

| 方法与资源 | 写入内容 | 并发边界 |
| --- | --- | --- |
| `PUT /api/projects/{id}/overrides` | override v3 与 resolved snapshot | `base_revision` CAS |
| `PUT .../visual-review/candidates/{candidate}/decisions` | P10.3c sampled visual decision revision | exact candidate、intent header 与 head CAS |
| `POST .../seam-anchor-reviews/.../candidates/{candidate}/decisions` | P10.5b seam decision revision | exact candidate、intent header 与 head CAS |

其余浏览器 API 为读取或 zero-write 计算。Package 推荐、motion-policy preflight 的 `passed` 和辅助 Foot 草稿都不是最终 human adoption，也不替代 CLI 对 exact decision/policy/bundle 的最终编译与复验。离线 CLI 中的 `compile`/`publish` 命令可能向 state root 发布内容寻址工件，因此运行前仍应查看对应 `--help` 和 how-to。完整路由见 [README 的 HTTP API](../README.md#http-api)。

## 当前能力边界

- P3/P5 可以进入现有 P6 Spine 4.2 导出链。
- P6 当前只有离线 CLI；主工作台没有 Spine 导出编排，Project API 的 `export_spine` 仍为 `false`。
- resolved snapshot 已确定性生成并被下游寻址，现有独立 v1 JSON Schema、严格语义 validator、派生 QA 校验及 r5/r7 历史哈希回归；它仍没有独立 CLI/UI，外部 candidate/split artifact 字节重放继续由各自 binder 负责。
- override history 已 append-only 保存，但主工作台尚无历史浏览/恢复 UI；安全恢复必须追加新 revision，不能改写历史。
- P7 real-pilot intake 审计已经可用：它把真实 NPZ、recorded sidecar、map、camera 与两份 provenance 原件闭合为零写入 path-free 报告。`wave-left-v1` 已通过该审计并完成 P7/P8、A/B P5 exact replay、正式 depth policy 与 depth candidates，身份集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)。P9 可自动加载两组 exact package 并辅助采用本轮安全 Foot 建议，但 A/B 仍各缺一次最终 human adoption 和 P9 地址；preflight 也不认证 checkpoint 或批准动作质量。
- P10 body-sway 已完成 P10.7b sampled raster 基础设施、冻结的 P10.7b-readiness v1 审计和独立 P10.7c setup regression 命令；readiness 第八项仍固定为 missing。当前默认 state 的独立 seam 审计确认 A/B 都没有 review history/head：A 的六条关系可复核，B 有四条腿/脚关系不可观测；真实 capture 也尚未交付，因此不能声称 A/B 已通过 P10.7c。
- `blink`、口型和头发目前只存在 idle candidate 类型或规划入口，没有可靠素材生成、绑定与 runtime 交付。
- See-through/pose 推理、真实 Kimodo checkpoint authenticity/动作质量验收、实时追踪、自由形变、runtime IK、生产部署仍未实现。

不要把结构验证、fixture、sampled screenshot/指标、anchor-point 距离、loader replay 或一次人工 decision 写成连续 raster 安全、真实双样本验收或发布通过。
