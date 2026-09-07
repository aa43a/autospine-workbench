# 当前状态：2026-09-07

开发集图层语义切片：62张逐层PNG已经核验，19项词汇的精确名称建议与待标注页面已实现；
三角色各5项建议，琪露诺1个空层保留复核。草稿默认语义空值、左右未知、纳入未决定。
详见[操作入口](how-to-benchmark-semantics.md)；尚未融合姿态/接触几何或自动采用。

开发集现在可以通过[PNG / PSD 坐标复核页](how-to-benchmark-mapping.md)并排和叠加检查，
调整缩放、平移与镜像并重载草稿。候选仍为零权威；没有自动确认映射或写入关节真值。
接续增加了对应锚点录入、逐轴最小二乘校准和残差报告。跨度不足/退化/高残差均
阻塞拟合应用，报告精确重放候选与锚点。正式映射请求/显式记录、exact reader 和
accepted 决定约束的待标注模板已实现；真实开发集尚无人工接受记录，语义/关节真值仍空。

Benchmark 接续切片：20 PNG/12 PSD 已转为正式待标注 manifest 并完成真实源验证；
首批3开发/4可见/3holdout、其余10 reserve已冻结。基础指标CLI、不可变报告和
alpha输入检查已实现；开发集3张原图仅完成机器alpha检查，未获得人工语义/关节真值。
开发集3个PSD已完成固定脚本隔离审计（62图层），琪露诺有1空层，映射与坐标变换
仍待复核；未注册为主工作台项目或修改历史A/B状态。
见 [首批记录](benchmark/first-batch-2026-09.md) 与 [CLI](how-to-benchmark.md)。
独立固定提交的全量验证见 [静止checkout基线](baseline-frozen-checkout-2026-09.md)，
与活跃工作树定向测试分开记录，尚不替代A/B current链封存或认证tag。

新增独立 Spine 4.3.26 Adapter，主工作台和 automation CLI 的新预览默认使用该版本，
可显式选择 4.2。两个目标独立绑定 PipelineRun engine 和预览存储地址；历史 4.2
认证入口保持原合同。当前产品入口仍限 reviewed region setup，4.3 Runtime 未执行。
详见 [4.3.26 适配范围](spine43-adapter-2026-09.md)。

基准提交：`4254151283d82b515934faf14d6d935e1e9a695a`，提交日期 2026-09-03。
开发 checkpoint 已提交为 `b0f2f76`，后续基线修复与素材盘点提交为 `7993b2a`；不是稳定认证标签。
本次接续读取了“为我解读这篇论文 (2)”的最新工作记录，并以本地 Git 为准核对。

## 已提交内核与前序修复

`4254151` 已交付 guarded v2 runtime authorization：preflight、单次内存执行许可
与 manager owner lease。把“自动授权入口”继续描述成下一切片已经过时。
这些机制不授予视觉批准或发布权，也不会自动启动官方 Runtime。

接续时工作区已有 15 个已跟踪文件修改和 10 个新文件，涉及 Runtime execution、
manager、readback、HTTP routes/security、server 接线与配套测试。这些属于前序
接续时的未提交工作，现已纳入上述 checkpoint；不是本轮新产品能力，也尚未被稳定 tag 覆盖。

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
| 主工作台一键 region Spine | 已实现异步构建、取消、ZIP 下载及复核后续跑 |
| 统一 Review Queue v1 | 当前覆盖 setup-region 门禁；不写决定，不替代未来 Mesh/Runtime 队列 |
| 三种 Pipeline Profile | 合同、Schema、validator 已接入独立 region 预览执行器 |
| PipelineRun / Capability / region preview CLI | 已实现；setup ZIP、幂等、恢复、取消、零发布权 |
| 通用分段臂腿 Mesh、袖子权重 | 尚未实现，不修改 leg-only v1 语义 |
| 20 角色 Benchmark | 待标注合同、store/reader、32源验证与3/4/3/10划分已冻结；映射/坐标变换/人工标注待完成 |
| 自动化指标 | 基础观察统计CLI已实现，初始全not_run；无抽查准确率/覆盖率不填造 |
| 输入质量前置检查 | 可选Pillow进行alpha/画布几何分析，只确定空图阻塞；不推断人体裁切或人数 |

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
历史 P3–P6/seam 重放 13/13 通过，但 A/B current 身份的完整封存仍未完成。

新执行顺序见 [自动化路线](automation-roadmap-2026-09.md)。AS-003/004 的 PipelineRun
与能力解析已实现；AS-005 已有[主工作台和无 SHA CLI](how-to-build-region-spine-preview.md)，
可自动构建 reviewed region 的 setup 预览并下载 ZIP，支持恢复、取消和精确读回。
AS-006 已有 setup-region 复核队列与保存后续跑；下一步为自动采用策略与指标，R1 尚未整体验收。
这不是新增 P10.8/P10.9 阶段，也不改变尚待完成的认证冻结要求。

前一 CLI 切片 [验证记录](pipeline-slice-validation-2026-09.md)：新增功能/质量 60 项、历史
重放与 A/B 边界 13 项通过。真实 A/B 无 SHA setup ZIP 均生成成功，重复运行逐字节
一致。本轮接入主工作台；动态 Mesh 验收和官方 Runtime 新采集仍未完成。

本轮 [主工作台验证](workbench-pipeline-validation-2026-09.md) 包含 100 项 Python
聚合检查、下载补强后 17 项复验、400 项 Web 测试，以及真实 Chrome 桌面/手机
点击与下载检查。移动画布高度反馈和下载证据读回漏洞均已修正。

本机未发现 `gh`，当前工具也无 GitHub 写入连接器；未创建远端 Issues、Milestones
或 Labels。本地 backlog、GitHub capability Issue 模板与 [标注流程](benchmark-annotation-2026-09.md) 已保存。
[素材盘点与 Alice 隔离审计](benchmark/intake-2026-09.md) 记录 20 PNG / 12 PSD，
不将文件名映射、画布变换或图层语义声明为已批准。
