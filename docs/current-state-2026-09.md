# 当前状态：2026-09-07

基准提交：`4254151283d82b515934faf14d6d935e1e9a695a`，提交日期 2026-09-03。
本次接续读取了“为我解读这篇论文 (2)”的最新工作记录，并以本地 Git 为准核对。

## 已提交内核与未提交工作

`4254151` 已交付 guarded v2 runtime authorization：preflight、单次内存执行许可
与 manager owner lease。把“自动授权入口”继续描述成下一切片已经过时。
这些机制不授予视觉批准或发布权，也不会自动启动官方 Runtime。

接续时工作区已有 15 个已跟踪文件修改和 10 个新文件，涉及 Runtime execution、
manager、readback、HTTP routes/security、server 接线与配套测试。这些属于前序
未提交工作，不是本轮新产品能力，也尚未被稳定 tag 覆盖。

本轮发现其中 reader 314 行、runner 312 行、runner test 421 行超过原有门禁。
仅提取纯 inventory/run-state 校验和测试辅助类；reader/runner 的发行闭包与
执行许可仍留在原位。不调整 P10 300 行门禁、默认 400 行上限或历史单体 ratchet。

## 可用边界

| 能力 | 实际状态 |
| --- | --- |
| Resolved / Manifest / region RigIR / P3 leg-only / IK | 已有可信编译与验证机制 |
| BVH、Kimodo NPZ、MotionIR、投影、P9 | 已有版本化离线链，真实历史身份见 pilot |
| Spine 4.2 JSON/Atlas/PNG 与 Runtime | 已有适配/采集机制；每份证据按 exact 身份读取 |
| guarded v2 Runtime authorization | 已提交；不能外推为真实 Runtime 或发布已通过 |
| 主工作台一键 region Spine | 尚未实现，仍是 P1 主线 |
| 三种 Pipeline Profile | 本轮实现声明合同、Schema、validator、开发 CLI；尚未接执行器 |
| 通用分段臂腿 Mesh、袖子权重 | 尚未实现，不修改 leg-only v1 语义 |
| 20 角色 Benchmark | 标注流程已准备，已定位 12 个新增 PSD，待审计与 split 标注 |

## A/B 历史保护

[Pilot handoff](pilots/kimodo-wave-left-v1.md) 继续作为 A/B 历史与 current
revision 地址的唯一记录，避免将旧 A/B P9 身份混入 A r6 / B r16。
A 已记录的静态接缝与 43-case 人工审核并不代表新的 P10.7b v2 采集已通过。
B 的四条不可观测下肢接缝与 ankle.left 阻塞不得因为历史 P9 成功而被绕过。

`tools/certification_baseline_inventory.py` 只读盘点已跟踪 golden 与 pilot
记录的字节 SHA，输出到标准输出；不替代 A/B 本地工件的完整 exact replay。
保留现有 golden、不重写旧地址、不填造人工决定。

## 本轮交接

测试及冻结结论见 [基线报告](baseline-tests-2026-09.md)。稳定版本标签
`certification-core-2026-09` 尚未创建：此次仅作 checkpoint commit，执行链不能直接视为认证冻结点；
完整 A/B 工件清单与当前身份重放也尚未完成。

新执行顺序见 [自动化路线](automation-roadmap-2026-09.md)。下一开发切片为
AS-003/004 的 PipelineRun 与能力解析，随后接 AS-005 一键 region 预览与 AS-006
异常队列。这不是新增 P10.8/P10.9 阶段。

本机未发现 `gh`，当前工具也无 GitHub 写入连接器；未创建远端 Issues、Milestones
或 Labels。本地 backlog 与 [标注流程](benchmark-annotation-2026-09.md) 已保存。
