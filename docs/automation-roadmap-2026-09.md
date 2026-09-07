# AutoSpine 自动化产品路线（2026-09）

2026-09-07 用户调整：新增 Spine 4.3.26 并作为新预览默认目标，4.2 作为显式兼容目标。
这覆盖原“暂停更多 Spine 版本”的 4.3 部分；其它暂停项和主链优先级不变。
适配范围见 [4.3.26 说明](spine43-adapter-2026-09.md)，官方 Runtime 验证仍待 opt-in 执行。

本文件取代旧路线的执行优先级。历史 P0–P10 编译阶段名称继续保留；这里的产品
工作包不改变旧阶段语义。Issue 编号采用用户计划最后的首批列表，避免与正文
P0 表格里的重复 AS 编号冲突，例如 AS-002 统一表示 Pipeline Profile。

## 主链与里程碑

| 顺序 | 工作包 | 交付判据 |
| --- | --- | --- |
| 1 | P0 / R0 可信内核冻结 | 代码与文档对齐、全量基线、A exact 清单、B 负例、稳定 tag |
| 2 | P1 / R1 一键 Spine | 已有 audit 无需 SHA，PipelineRun、能力解析、异常队列、幂等续跑 |
| 3 | P2 / R2 自动 region rig | 语义、左右、contact、关节约束与骨架；只复核异常 |
| 4 | P3 / R3 通用变形 | 分段臂腿优先，再整肢、袖子；独立 P3/P5 v2 与接缝 QA |
| 5 | P4 / R4 多动作 | AnimationIR、组合、投影迟滞、出平面阻塞与 8 类动作 |
| 6 | P1-B 表情 | AttachmentSet、离散切换、anchor、Spine 4.2 与 Runtime probes |
| 7 | P5 次级运动 | 先头发飘带，再宽袖裙子，固定步长离线 Bake |
| 8 | P2-B / P6 / R5 端到端 | 隔离 Runner、恢复、多 seed、20 角色验证 |
| 9 | P7 / R6 Blender | 同一 Rig/Animation 输出 armature、UV mesh、Action/NLA |
| 10 | P8 生产化 | 安装、恢复、性能、文档与跨目标回归 |

Runner 与 Attachment 可提前推进，但不能挤占 Mesh/Weight 的主链资源。
28 周是两工程师加半名技术美术/测试的并行排期，不是当前执行完成承诺；
无法充分并行时 Blender 延后至 32–36 周。受限输入保持单角色、全身、正面或
轻微 3/4、可用 See-Through 分层和白名单动作。

## 首轮 backlog

| Issue | 工作 | 当前状态 |
| --- | --- | --- |
| AS-000 | 状态、roadmap、guarded authorization 对齐 | 本轮落实 |
| AS-001 | certification-core 基线冻结 | 工作区基线运行；冻结 tag 尚待验收 |
| AS-002 | pipeline-profile-v1 | 合同、Schema、validator、CLI 与反例测试已实现 |
| AS-003 | PipelineRun 状态机 | v1 CLI、状态机、不可变 journal、CAS、取消与恢复已实现 |
| AS-004 | Project Capability Resolver | setup-region 范围已实现，读取 current 且检测输入漂移 |
| AS-005 | Build Spine Preview | 无 SHA CLI + 主工作台异步 setup ZIP、取消和复核后续跑已实现 |
| AS-006 | Review Queue | setup-region 队列已实现；Mesh/Attachment/Runtime 等随能力扩展 |
| AS-007 | policy_auto | 待开发；不借用 human decision |
| AS-008 | 自动化指标报告 | 待开发 |
| AS-009 | 20 角色 manifest | 20 PNG + 12 PSD 只读盘点完成；正式标注待录入 |
| AS-010 | 首批 10 角色标注流程 | 3 开发 / 4 可见测试 / 3 holdout |

后续依序建立 AS-150–153、AS-200–206、AS-260–263、AS-300–305、
AS-400–403、AS-500–505、AS-700，内容以本次用户详细计划为准。
当前环境没有 `gh` 或 GitHub 写入连接器；本表是本地 backlog，不能视为已创建远端 Issues。

本切片操作见 [项目级 region 预览](how-to-build-region-spine-preview.md)。下一步推进
AS-007 自动采用策略和 AS-008 指标；R1 的广泛素材、官方 Runtime 视觉与生产验收仍待完成。

## 验收与约束

首批 10 角色先校准门槛：语义 ≥90%、左右 ≥95%、自动采用抽查 ≥98%、
核心关节覆盖 ≥65%、肩髋踝中位误差 ≤角色高 3%。自动采用优先精度，
覆盖率不足进入复核，不能降低阈值静默采用。

P3 必须至少覆盖三分段臂、三分段腿、两袖子候选，setup 精确重建、
安全角零翻转、接缝裂缝可检出、Spine 4.2 fixed-tick 验证。
Beta 目标：端到端 ≥70%、无需改代码 ≥80%、无结构修改 ≥50%、
复核 P50 ≤15 分钟/P90 ≤35 分钟，错误静默导出为零。

新生产文件 300 行预警、400 行硬上限；旧单体 ratchet 只减不增。
新功能建立 automation、asset、motion2d、runners、targets、benchmark 包，
旧 P9/P10 通过 façade 调用，不做批量搬迁。

每项能力交付合同/profile、Schema、validator、纯核心、内容寻址 reader/store、
至少一个用户入口、fixture/数值/代表性视觉验证。纯配置合同暂不伪造视觉 golden；
完整功能验收仍须其真实资产和 Runtime 证据。

R5 前暂停新增 P10.8/P10.9、更多 Spine 版本、Runtime Physics、360°、
Grease Pencil、深度生图集成、默认大量 RIFE 帧、Live Tracking、全自动发布授权
和旧 P10 大规模重构。已实现的 guarded Runtime 授权属于保留内核。
