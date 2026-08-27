# AutoSpine Workbench 功能与入口参考

本文是面向操作者和开发者的 Reference。它回答“功能是否已经实现、从哪里进入、会得到什么”，不替代具体操作步骤。P0 Resolved Project v1、P10.6b MotionInstance v3、P10.7a Spine 4.2 v3 adapter bundle 与 P10.7b sampled raster 基础设施已完成；当前验收入口是 **P10.7b 两份真实 See-through 样本的官方 Runtime 捕获与人工复核**。计划项见[开发路线](development-roadmap.md)。

## 统一入口

启动服务后打开：

- [功能入口中心](http://127.0.0.1:8765/workflow-hub.html)：按阶段、入口类型和状态搜索全部功能；
- [绑定复核工作台](http://127.0.0.1:8765/)：图层、拆分、关节、候选和 P3 证据复核；
- [Body-sway 视觉复核台](http://127.0.0.1:8765/body-sway-review.html)：P10.3c sampled still 复核；
- [Seam Anchor 复核台](http://127.0.0.1:8765/seam-anchor-review.html)：P10.5b 静态接缝锚点复核。

功能入口中心读取 [`web/workflow-catalog.json`](../web/workflow-catalog.json)，列出 58 个已注册 CLI、三个任务页面和尚未实现的计划项。对于 CLI，它只复制 `python -B -m autospine_workbench <command> --help` 帮助命令，不在浏览器或服务端执行命令；源码模式下须先在当前 PowerShell 执行 `$env:PYTHONPATH = (Resolve-Path .\src).Path`，再复制和运行帮助命令。文档卡片通过 `/document-viewer.html?doc=docs/<文件名>.md` 安全文档查看器打开；查看器只读获取 `/docs/<文件名>.md`，不能访问目录外文件，并把响应作为纯文本显示，不解析 HTML 或执行文档内容。

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

## CLI 功能

先在项目根目录设置源码路径：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench --help
python -B -m autospine_workbench <command> --help
```

下表与当前 CLI parser 的 58 个命令一一对应。具体必填 SHA、文件路径和外部前置条件以各命令 `--help` 及链接的 how-to 为准。

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
| `compile-kimodo-motion` | 从固定 NPZ、source sidecar 和 map 生成 MotionIR bundle |
| `verify-kimodo-motion` | 重编并复验精确 Kimodo NPZ MotionIR bundle |

操作说明：[Kimodo NPZ](how-to-compile-kimodo-npz.md)；Kimodo-shaped BVH 使用 P5 的 `compile-bvh-motion`，见[Kimodo BVH](how-to-compile-kimodo-bvh.md)。

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

capture manifest 会记录 runtime JS/CSS、`package.json`、`LICENSE`、浏览器、capture plan、P10.7a 来源与 PNG 摘要。`LICENSE` 文件存在不等于已经取得授权，许可确认仍由操作者负责。

指标只以 `alpha >= 1` 的二值掩码比较捕获计划内 transparent composite 与 attachment isolate union，并检查 missing/extra/xor、边界、裁切和非空 isolate。人工 decision 只覆盖同一组 sampled case 与 setup attachment inventory。两者都不证明未采样时间、连续 runtime raster safety、永久 current-head authority、publishable timeline 或 release authority；release gate 始终 blocked。

操作说明：[捕获并复核 P10.7b Spine 4.2 v3 Raster 证据](how-to-capture-spine42-v3-runtime.md)。基础设施可用，但两份真实 See-through 样本的外部 Runtime 捕获、P6 golden 对照和逐项人工决定仍待完成；结构 fixture 不能替代真实样本验收。

## HTTP 写入边界

本地 HTTP 服务目前只有三类写操作：

| 方法与资源 | 写入内容 | 并发边界 |
| --- | --- | --- |
| `PUT /api/projects/{id}/overrides` | override v3 与 resolved snapshot | `base_revision` CAS |
| `PUT .../visual-review/candidates/{candidate}/decisions` | P10.3c sampled visual decision revision | exact candidate、intent header 与 head CAS |
| `POST .../seam-anchor-reviews/.../candidates/{candidate}/decisions` | P10.5b seam decision revision | exact candidate、intent header 与 head CAS |

其余浏览器 API 为只读。离线 CLI 中的 `compile`/`publish` 命令可能向 state root 发布内容寻址工件，因此运行前仍应查看对应 `--help` 和 how-to。完整路由见 [README 的 HTTP API](../README.md#http-api)。

## 当前能力边界

- P3/P5 可以进入现有 P6 Spine 4.2 导出链。
- P6 当前只有离线 CLI；主工作台没有 Spine 导出编排，Project API 的 `export_spine` 仍为 `false`。
- resolved snapshot 已确定性生成并被下游寻址，现有独立 v1 JSON Schema、严格语义 validator、派生 QA 校验及 r5/r7 历史哈希回归；它仍没有独立 CLI/UI，外部 candidate/split artifact 字节重放继续由各自 binder 负责。
- override history 已 append-only 保存，但主工作台尚无历史浏览/恢复 UI；安全恢复必须追加新 revision，不能改写历史。
- P10 body-sway 已完成到 P10.7b sampled raster 基础设施；官方 capture 依赖外部已授权 runtime，两份真实 See-through 样本尚未完成人工验收，且任何 sampled 结果都不是连续时间证明或可发布 timeline。
- `blink`、口型和头发目前只存在 idle candidate 类型或规划入口，没有可靠素材生成、绑定与 runtime 交付。
- See-through/pose 推理、真实 Kimodo checkpoint 质量门禁、实时追踪、自由形变、runtime IK、生产部署仍未实现。

不要把结构验证、fixture、sampled screenshot/指标、anchor-point 距离、loader replay 或一次人工 decision 写成连续 raster 安全、真实双样本验收或发布通过。
