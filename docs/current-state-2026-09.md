# 当前状态：2026-09-08

新增[逐关系候选准入报告](how-to-seam-admission.md)，严格校验Runtime点／矩阵／文件身份，并保留无样本未评估状态。
琪露诺311点原生密度pair/all共1244次局部捕获、242帧回归通过；左右99／212点合成alpha下降，其中93／191点新低于8。
几何通过仍需复核透明度退化。下一步验证琪露诺双侧整段回退；所有报告均无采用权。

新增[Alice 稳定整段回退候选](how-to-seam-stable-fallback.md)：左侧恢复 reference，右侧保留增量。
四区域几何通过，左右边界增距1.968960／1.727884px，新增空白帧均0。
七点全部测试条件下目标RGBA恢复到reference；224次Runtime捕获与242帧回归通过。
原有空白仍存在，未授权采用。下一步整合逐关系准入报告并验证其他角色。

新增[官方 Runtime 同帧局部合成](how-to-seam-local-runtime.md)：4.3.13 Runtime 加载 4.3.26 目标候选，Alice 七点 224 组捕获。
原生合成 alpha 全下降，四点低于8；共享／独立纹理目标像素一致，CPU 合成误差≤1。
原／增量各121帧对照通过。当前条件下透明度退化已确认，未授予采用权；下一步稳定逐关系回退／准入。

新增[直接 UV alpha 子采样](how-to-seam-direct-alpha.md)：318 个像素单元均含合成 alpha<8 的子样本。
Alice 七个中心都有双 Mesh 覆盖；其中三个中心由两层分别低于8变成合成后达到8。
当前证据区分纹理透明度与几何覆盖，下一步核对官方 Runtime 同帧局部合成；未采用，不宣称 GPU 可见裂缝已确认。

新增[亚像素等值轮廓](how-to-seam-gap-isoline.md)：对 CPU alpha 样本场作双线性插值和 4 倍细分弦段近似，保留鞍点／阈值角点不确定性。
Alice 七点均呈相向边界，8 倍细分对照分类一致，距离变化最大约 0.01662px；318 个样本全部保留。
该结果不是 GPU 或直接 UV 亚像素采样证据；下一步校准局部可见性，候选未采用。

新增[动态 alpha 边界证据](how-to-seam-gap-boundary.md)，全部 318 个样本保留最近边缘、法向与局部连通性。
Alice 左侧为相向 1／并列歧义 6；连续三帧中 37 帧在 ROI 内封闭，36、38 帧连到边缘。
这些是 alpha8 栅格单元证据，不是亚像素等值线或 GPU 判决。下一步解释栅格角点歧义，权重和采用状态不变。

新增[附件运动补偿轨迹](how-to-seam-gap-transport.md)：局部三角形仿射延拓、双附件一致性和正反向残差形成候选边。
Alice 左侧 6→4 条轨迹，第 36–38 帧连续；琪露诺左／右 70→22、107→56，最长 20／13 帧。
318 个像素样本和旧轨迹报告地址保持不变。下一步用连续轨迹校准 alpha 边界拓扑，未采用，不宣称 Runtime 新证据。

新增[空白跨帧轨迹](how-to-seam-gap-tracks.md)：八连通区域保存全部像素世界坐标，3px 双向唯一关联保留分裂／合并歧义。
Alice 左侧 7 个样本为 6 条轨迹；琪露诺左／右为 70／107 条。固定距离会在快速运动时断轨，不能把单帧轨迹判成噪声。
三角色报告精确重放和旧 context 地址一致；当前仅诊断，下一步验证运动补偿关联，内外拓扑及采用门禁尚未完成。

新增[空白支撑证据](how-to-seam-gap-context.md)：三角色已有 bundle 的文件身份与四处关系各 61 帧指标重放通过。
Alice 左侧 7 个新增像素样本均为相对附件支撑；琪露诺为相对 59、单附件 243、不确定 9。
不把单附件支撑直接认定为外轮廓移动，不据此采用增量；下一步定位跨帧空间证据。动画与历史报告未改变。

最新：[固定原 deform 的有界增量](how-to-seam-increment.md)使 Alice 左／右原对应增距降至 1.102／1.728 px，琪露诺左／右为 0.279／0.403 px；12 个区域无翻转。
Alice 右侧共同走廊空白峰值 3 → 1、无新增空白帧；其余三处有新增空白。热图显示部分点靠近外轮廓，尚未区分外轮廓移动与内部裂缝，不能把所有计数直接视为真实裂缝。
官方 Runtime 三角色 363 帧编码／采样检查通过，候选未采用。下一步增加栅格空白的空间归因，再建立可信的逐关系／整段动画准入，零增量仍应恢复固定原动画。

最新：[alpha 支持的接缝平移约束](how-to-seam-translation.md)完成四处候选、30 FPS bake 与 60 FPS 前后对照。
12 个区域网格采样继续通过；四处腿鞋仍超限（4.38–11.53 px），Alice 左侧略退化。铃仙无候选，保持 candidate_noop。
官方 Runtime 三角色 363 帧通过只证明编码一致。约束未采用；下一主线是真实 alpha 接触轮廓与局部共同边界过渡。

最新：[连续 corrective Bake 与接缝诊断](how-to-continuous-corrective.md)完成 30 FPS、2 秒的受限候选动作。
12 个区域在 121 个时刻的几何检查通过；官方 Runtime 三角色共 363 帧通过。四处腿鞋邻近关系超出 2 px 增距阈值，其余无对应点的区域不计接缝通过。
下一步建立 alpha/contact 接缝对应与共同运动约束；不能用窄范围采样通过清除来源宽角度 blocked 状态。
校正上一切片名称：琪露诺 layer-004 的骨链为 upperarm/forearm/hand；layer-005 才是 thigh/calf/foot。

最新：[主关节与远端 corrective 组合](how-to-combined-corrective.md)完成 46 key 的离散诊断导出；
5/8 个三骨区域通过，铃仙右腿和琪露诺双手臂（layer-004）保持 blocked。官方 Runtime 273 帧、旧路径 363 帧通过，Alice 精确重放一致。
下一步为连续动作 bake 和动态跨层接缝 QA，未授予生产权。

已完成[Spine分区诊断播放](how-to-ownership-spine43.md)：4.3.26数据与官方4.3.13 Runtime分开记录，
三个角色UV、独立FK、363个固定时刻的像素对照通过。后续组合诊断见上，不将诊断通过当生产批准。

新增[ownership纹理页](how-to-ownership-atlas.md)：把左右／残余打包为单页独立区域，
不改变网格和权重。源v2继续保留，下一步接入Spine region UV转换与固定帧采样检查。

按残余复核说明补齐[共享源纹理分区v2](how-to-shared-partitions.md)：统一源PNG、ownership、区域网格与混合权重，
未改变残余或批准绑定。下一步处理共享纹理的边界采样隔离，再连接多关节动作QA。

新增[横向宽度权重试验](how-to-distal-width.md)：原网格上比较三个固定宽度策略，
系数4下五处远端corrective通过、三处失败；所有全链LBS仍阻塞，未采用。
下一步检验主关节与远端corrective组合及剩余三处失败，不按单角色反复调系数。

新增[踝/腕局部加密](how-to-distal-grid.md)：十二区域完整alpha覆盖，八处混合顶点增至53–76个，
但远端QA仍全部阻塞且最差面积比退化。该实验不作为默认；下一步验证横向宽度约束的权重过渡。

新增[踝/腕局部corrective](how-to-distal-corrective.md)：固定刚性顶点、限制相对半角基底的位移，
并验证局部偏移重建。八处均未通过变形QA，未采用；后续局部加密结果见上方。

新增[全alpha覆盖修复](how-to-partition-coverage.md)：可见主组件判断与全部alpha覆盖分离，
原权重和残余保留。踝/腕前移过渡试验不稳定，作为未采用的独立对照保存。

新增[分区Mesh/Weight实验](how-to-partition-mesh.md)：12个区域独立侧别权重与逐关节QA。
远端踝/腕旋转和alpha覆盖仍失败，残余保留且未绑定；不声明完整角色或R3通过。

新增[残余复核](how-to-residual-review.md)：保留/4px邻近试算、alpha总量占比、整份草稿保存恢复，
六项默认pending；本轮没有正式采用分区或权重。

新增[无损分区](how-to-layer-partitions.md)：三个角色六层的RGBA与ownership验证通过，
低alpha平局/孤立像素保留残余；不改旧绑定和Mesh，残余复核及分区权重尚待接入。

新增[结构候选分析](how-to-layer-structure.md)：主要连通域、骨架侧别距离与小组件计数，
为双侧肢体/鞋提出分区候选。裙装只提供刚性 setup 建议；候选不更改绑定或源图。

新增[头部绑定补全](how-to-binding-completion.md)：独立profile保留19项既有选择，
为三个开发角色新增31项头部刚性候选；新增项仍pending，另外12项结构问题未解决。
未更新旧Mesh/Bake/组合包，完整角色尚未完成。

新增[已确认图层组合](how-to-character-preview.md)：Alice/铃仙各7层，未选16/14层保留；
四组肩部alpha重叠锚点为候选，分离量接近零不表示接缝通过。输出独立组合ZIP和播放页。

新增[4.3.26手臂诊断ZIP](how-to-elbow-spine43.md)：使用附件时间轴编码逐影响骨 deform，
附原图与排除图层清单；完整角色状态仍阻塞，官方Runtime未评估，旧正式Adapter不扩权。

新增[corrective动画烘焙](how-to-elbow-bake.md)：四臂120Hz采样QA通过，最大插值误差约0.13px，
提供原纹理WebGL播放页。独立工件不改旧Mesh；尚未编译Spine deform时间轴或验证跨图层接缝。

新增[肘部局部约束](how-to-elbow-constraints.md)，辅助骨结果上施加固定迭代面积/边长投影，
保留刚性端部与位移预算；修正可转换为原 LBS 局部偏移，尚未 Bake 时间轴或正式导出。

新增[肘部三方案比较](how-to-elbow-comparison.md)：同网格逐度 QA，半角辅助骨与旋转保持修正
均可保留 setup；后者已验证逐影响局部偏移重建。四臂仍未通过面积阈值，未改变正式骨架或绑定决定。

新增独立[面积 QA 报告](how-to-mesh-area-screen.md)：逐度扫描、最差三角形定位、
原面积加权收缩范围。四张手臂仍需收缩修正，接缝和 Runtime 明确未评估；旧 Mesh 地址不变。

针对Alice右臂+90°翻转新增关节平面权重profile，保持原三角形/UV并限制远端权重泄漏。
旧失败报告保留原地址。后续仍需轮廓、关节加密、面积收缩和接缝验证。
见[改进与回放](how-to-joint-plane-refinement.md)。

实验性三骨Mesh候选已实现：已有alpha规则网格、骨段距离权重、setup LBS与7个弯曲探针。
独立大报告存储不放宽历史合同上限。双侧六骨/多显著连通域仍阻塞，关节加密和接缝QA未完成。
见[操作与边界](how-to-weighted-mesh.md)。

已按用户指令选定19项默认绑定，43项无默认建议保持待处理。接续alpha分析已实现
4连通域/省略面积记录/固定骨段覆盖采样，并生成来源可重放的报告；尚无网格权重。
见[选择记录与分析入口](how-to-chain-coverage.md)。

用户调整：同一图层需支持多骨Mesh，不能用单骨region能力限制整臂/整腿。
独立layer-binding v2已接通刚性单骨、单侧三骨链和双侧两链选项，支持编辑及源绑定草稿。
本步尚未生成网格/权重；下一主线为alpha覆盖、网格权重及P3 v2动态QA。
见[多骨操作与后续顺序](how-to-layer-binding-v2.md)。

绑定草稿编辑入口已完成：三角色62条记录初始全pending，支持选择已有骨候选、拆层/语义问题、
排除、备注、下载恢复和撤销。CLI源闭包复验与草稿精确回读已接通；正式绑定决定仍未产生。
见[草稿操作](how-to-region-binding-drafts.md)。

图层绑定候选已接通：62层全部保留，15层有待复核选项，47层明确阻塞。
绑定局部变换四角重建最大误差约1.14e-13 px；暂无采用决定、完整region Rig或Runtime验证。
见[绑定操作与实际局限](how-to-region-bindings.md)。

辅助复核标注已接通独立候选骨架入口，三角色各20骨，保留每角色全部17点。
实际局部变换重建最大坐标差约1.14e-13 px，重复构建地址一致。
仍为待复核候选，尚无图层绑定/生产RigIR；见[操作与验证](how-to-assisted-skeleton.md)。

2026-09-08：用户已提供三角色模型辅助标注，51点均标记已复核，30点坐标修改。
三份输入已通过源闭包验证并原样封存；原始Pose与独立GT状态未改变。
详见 [导入结果](assisted-annotations-2026-09-08.md)。

人工标注新增模型辅助模式：一次加载17个建议点，画布直接点选拖动、批量确认和整份保存。
Pose/旧基线来源及复核标记随独立envelope封存，不计为独立GT。原空白标注入口继续可用。

R2-B 评估链已接通：独立标注Reference、显式记录CLI、三方法共同GT点对照、源闭包
精确重放及只读评估页。三个真实开发角色尚无正式Reference，误差全部null；不改变
镜像/可见性阻塞。见 [独立标注与评估](how-to-benchmark-pose-evaluation.md)。

R2-B 首个真实模型入口已交付：固定 DWPose ONNX + 隔离CPU环境，Alice/铃仙/琪露诺
三角色真实推理、完整SimCC存储、COCO17适配和只读对照已运行。原始分数可大于1，
规范分数显式编码；visibility和默认镜像保持unknown，融合仍阻塞。无人工GT，误差为null。
见 [运行说明与实际局限](how-to-real-pose.md)；RTMPose/HumanArt横向比较及精度验收待完成。

R2-A 技术链已完成：ModelRunner 协议及规范文件导入、Pose/Contact 双侧匹配、有限步长
关节约束优化、20 骨 canonical skeleton、内容地址全链回读与离线可视入口。
Synthetic 端到端测试验证接触确实影响关节，并验证骨长、位移和 setup FK；
R2-A 当时未执行真实 Pose 模型；现已增加上述独立 R2-B 入口，仍无人工 GT，不能报告精度提升。
所有结果仍为零权威候选，生产 RigIR/复核门槛不变。见 [R2-A 操作与边界](how-to-r2a.md)。

接触筛选切片新增独立报告：深重叠排除、多接触区/多图层/间隙复核及固定阈值重放。
身体角色仍为未复核衣物代理；肩踝阈值未校准，不套用髋部阈值或自动赋值关节。

接触诊断切片新增原名配对的 alpha 接触分析与离线图层叠加，复用旧接触算法和
精确源验证。衣物标签不冒充身体语义，左右未知时所有关节分配保持阻塞。
详见[接触操作说明](how-to-benchmark-contacts.md)；尚未达到自动 shoulder/hip/ankle 定位。

关节基线对照切片：复用旧 audit/bbox 算法，新增17点叠加、草稿距离统计和实际素材
精确重放。三个开发样本已生成报告，因无真实人工点，误差为null；未接入新融合算法。
此为测量旧算法不足的诊断入口，不是关节精度提升或 R2 完成。见[操作说明](how-to-benchmark-joints.md)。

接续交付17关节点PSD坐标草稿录入/恢复，以及显式语义采用请求、记录与精确重放。
真实样本仍无代填关节点或人工采用记录；Pose融合与候选骨架已有 R2-A 技术实现，
真实角色验证和生产 Rig 自动生成尚待后续。

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
