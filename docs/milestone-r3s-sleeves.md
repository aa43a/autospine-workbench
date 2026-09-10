# R3-S：可导出的受限袖装动画

目标是辉夜、幽幽子四处已标注袖子成为可重建的Spine 4.3.26候选，而非继续累积独立实验页。保持来源与正式采用分离。

## 验收范围

- 已保存归属→多连接点结构→服装权重/辅助驱动→确定性修正Bake→Spine候选→官方Runtime与袖口视觉QA。
- 初始最低动作范围固定为前臂±30°、手±30°、垂布±10°，并增加前臂/手/垂布组合动作；不能为通过测试静默缩小范围。
- 四处setup误差≤1e-7px、权重和误差≤1e-9，安全范围内无翻转，面积比[0.5,2]、边长伸长≤2。先密集采样，再检查Bake插值及Runtime。
- 接口位置保持、alpha裂缝/过度重叠另行QA；几何相连不等于纹理连接通过。
- 普通用户入口发现当前唯一来源并一键重建，显示失败原因和支持动作范围；可撤销，不要求填SHA。
- 额外至少一个未参与调参的袖装案例通过同一流程，才扩大通用性声明；本阶段不以角色名称写分支。

## 连续交付顺序

1. 多连接点与固定边界的局部约束；保留手/unknown及固定袖布，验证129点和关键姿态之间的过渡。
2. 袖口接触与组合动作；必要时增加支撑点，保持原纹理，不强制吞并unknown。
3. 将候选骨架/权重/修正转换到Spine 4.3.26，重新计算目标deform，并运行真实Runtime。不能用CPU预览替代。
4. 一键编排、恢复与QA汇总，完成四袖交付和独立案例验证。

当前基线：四处根部/边界工件已可重放；只有辉夜左侧根部过渡保留收益，其他根部试验回退。所有袖子仍有失败，尚未完成上述里程碑。
# 首个切片结果（2026-09-10）

`cloth-only-pbd48-guard129-v1` 固定全部已测交界顶点，只修正明确属于垂布的内部顶点。
33 个修正键以世界坐标位移表示，键间在真实分支 FK 上插值位移，129 点检查；尚未转换为 Spine deform。
预算固定为前臂长度的 15%，48 次迭代，不按角色调参。

| 袖子 | 垂布轨原失败数 | 试验失败数 | 结果 |
| --- | ---: | ---: | --- |
| 辉夜右 | 83 | 3 | 保留候选 |
| 辉夜左 | 49 | 0 | 新增局部翻转，回退 |
| 幽幽子右 | 83 | 7 | 新增局部翻转，回退 |
| 幽幽子左 | 82 | 16 | 新增局部翻转，回退 |

计数分母均为 129；此处垂布压力测试仍为 ±15°，手轨仍为 ±90°，不是里程碑最低范围验收。
辉夜右候选手轨仍有 55 个失败采样。全部袖子仍 blocked，无正式采用或 Runtime 通过声明。
共享顶点的几何固定不代表 alpha 接缝连续；袖口连接、组合动作与官方 Runtime 是后续必做项。

重建入口：

```powershell
$env:PYTHONPATH='src'
python tools/build-sleeve-helpers.py --multi-anchor --input ../tmp/r3a-cloth-interface --output ../tmp/r3s-cloth-anchors huiye uuz
```

下一切片先在约定的前臂 ±30° / 手 ±30° / 垂布 ±10° 范围建立故障位置与袖口连接检查，
处理固定边界邻域的局部自由度，再进入修正键转换和目标 Runtime 验证。不会用降低范围替代验收。

## 受限组合动作切片

新增固定范围 profile `forearm30-hand30-cloth10-sine129-v1`，包含三条单轴及四种相对符号的同步正弦组合轨。
每轨 33 个修正键、129 个真实分支 FK 采样；对组合姿态重新求解，不叠加旧单轴修正。
交界顶点位移为零，循环首尾重合。该检查不等于任意三轴角度组合的完整体积证明，也不代替 alpha 接触检查。

| 袖子 | 前臂 | 手 | 垂布 | 组合 ++ | 组合 +- | 组合 -+ | 组合 -- |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 辉夜右 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 辉夜左 | 0 | 98 | 0 | 35 | 104 | 104 | 35 |
| 幽幽子右 | 0 | 0 | 0 | 0 | 23 | 23 | 0 |
| 幽幽子左 | 0 | 42 | 0 | 21 | 60 | 60 | 21 |

以上为按无回归门禁选择后的失败采样数，分母 129。全部仍阻塞正式采用；辉夜右仅采样几何通过。
命令：`python tools/build-sleeve-helpers.py --motion-envelope --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-motion-envelope huiye uuz`。
下一步用失败三角形与 sleeve/cuff/hand/hanging_cloth 归属对应定位连接邻域，修正其结构自由度，同时为已通过几何的轨道接入目标 deform 转换。

## Spine deform 与官方核心验证

新增 `targets/spine43/sleeve_deform.py`，将画布修正位移逆旋转到每个骨骼影响的局部坐标，
并转换 Y 方向；129 个骨骼旋转/deform 键，257 点独立目标格式插值检查。
已导出辉夜右袖的 JSON / Atlas / 原分区精确纹理 / ZIP，其他三袖返回结构化阻塞原因。
输出拒绝覆盖已有不同字节；不是整角色包，不产生发布权。

辉夜右7轨目标格式几何检查通过，关键帧还原最大误差约 6.64e-13px。
目标线性插值与原正弦轨在中点存在最大约 0.120px 的差异，目标网格在257点仍通过。
官方外置 `@esotericsoftware/spine-core 4.3.13` 共验证1799帧，与独立目标求值参考最大误差约0.000119px。
这仅是官方核心骨骼/加权顶点验证，未启动GPU或验证纹理采样；alpha接缝及Framebuffer仍未通过验收。

```powershell
python tools/export-sleeve-spine.py --input ../tmp/r3s-motion-envelope --output ../tmp/r3s-spine huiye uuz
node tools/verify-sleeve-core.mjs ../tmp/r3s-spine/huiye/layer-002-component-0000 ../tmp/spine43-verification/node_modules/@esotericsoftware/spine-core
```

其余失败三角形按已保存归属定位：辉夜左17个（15垂布、2袖口），幽幽子右2个（垂布），幽幽子左3个（2垂布、1袖口）。
下一步针对这些连接邻域增加局部结构支撑，继续保留手与未知区，避免全局调权重。

## 服装连接带自由度

`garment-connection-ring1-sine129-v1` 允许仅被 sleeve/cuff/hanging_cloth 三角形引用的连接带顶点参与有界修正。
接触 hand、unknown 或其他角色的顶点固定；连接带使用一个拓扑邻接环，不按角色名或像素坐标分支。
拓扑、UV、纹理、基础权重均未变化。共享边顶点一起移动，不把同一条边复制或断开。
候选除原始FK门禁外，还逐轨对上一版已保留修正运行无回归检查，未取得收益则保留旧记录。

| 袖子 | 前臂 | 手 | 垂布 | 组合 ++ | 组合 +- | 组合 -+ | 组合 -- |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 辉夜右 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 辉夜左 | 0 | 29 | 0 | 11 | 58 | 56 | 11 |
| 幽幽子右 | 0 | 0 | 0 | 0 | 23 | 23 | 0 |
| 幽幽子左 | 0 | 21 | 0 | 0 | 58 | 58 | 0 |

每格分母129。辉夜左、幽幽子左保留新自由度；其余保留旧候选。
本版未新增可正式采用袖子，未复用旧Runtime报告作为新资产验证。

```powershell
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --baseline-envelope ../tmp/r3s-motion-envelope --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-connection-domain huiye uuz
```

## 固定边界可行位移下界

诊断将48次迭代提高到256次，剩余失败无改善且位移达到预算上限；该试验没有改变生产求解器。
新增 `one-free-area-bound-cap50-v1`：对恰有一个可移动顶点的三角形，面积对该点位置是线性的，
据此计算恢复目标面积所需位移的准确下界。候选预算取基础15%前臂长度与下界×1.1的较大值，
硬上限为50%前臂长度。新profile显式改变修正预算，旧profile及历史hash不变；动作范围与QA门槛不变。
多自由顶点的可行性不由该下界证明，最终仍依赖完整几何检查。

| 袖子 | 前臂 | 手 | 垂布 | 组合 ++ | 组合 +- | 组合 -+ | 组合 -- |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 辉夜右 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 辉夜左 | 0 | 11 | 0 | 11 | 24 | 22 | 11 |
| 幽幽子右 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 幽幽子左 | 0 | 0 | 0 | 0 | 19 | 19 | 0 |

每格为129采样中的失败数。幽幽子右新候选通过Spine目标257点几何检查及外置官方core的1799帧数值验证，
最大顶点误差约0.0001125px；仍没有GPU或alpha接缝通过声明。辉夜左与幽幽子左继续阻塞。

```powershell
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --boundary-budget --baseline-envelope ../tmp/r3s-connection-domain --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-boundary-budget huiye uuz
python tools/export-sleeve-spine.py --input ../tmp/r3s-boundary-budget --output ../tmp/r3s-spine-boundary huiye uuz
```

## 共享支撑网格试验

剩余辉夜左袖面积异常集中于袖口三角形144：三个旧顶点均受手部保护，但其中两边连接袖口内部。
幽幽子左袖剩余异常为边长伸长超限，不能只按面积坏三角形定位。

新增 `sleeve_support_mesh.py`：服装交界共享边只创建一个中点，相邻三角形同步细分，不产生T形接缝；
新UV和影响坐标按原顶点仿射插值，任意原始骨骼姿态下保持细分前的LBS表面。
新手部/未知区域顶点继续固定，服装支撑点才参与求解。原始粗网格的预算下界仍保留，不能因细分而丢失。

本次试验没有通过整袖门禁，全部保留旧候选：细分后的辉夜左7轨失败数为0/21/0/6/56/56/6，
幽幽子左为0/24/0/0/45/49/0；幽幽子右也出现回归。
拓扑变化后不以坏三角形计数下降作为收益，只有全部轨道采样通过才允许替换旧网格。
两个右袖已通过的基线、导出和核心Runtime证据未修改。

```powershell
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --boundary-budget --support-mesh --baseline-envelope ../tmp/r3s-boundary-budget --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-support-budget-v2 huiye uuz
```

下一步应求解邻接三角形的联合约束；当前逐三角形投影可能在修好一处时破坏邻域，不能靠继续加密网格或增加迭代次数证明收敛。

## 联合约束和手部刚性对照

可选 `cloth-solver` 环境增加 NumPy 2.4.6 / SciPy 1.18.0（本地Python3.14验证），不改变核心依赖。
`cloth_joint_solver.py` 同时最小化面积/边长超限与位移预算违反，固定手和未知顶点，最后再次限制位移并执行原几何门禁。
优化器状态不是通过依据。联合约束在细分网格上仍失败，四袖均保留旧记录。

另一条独立试验按hand三角形归属将其共享边界改为手骨刚性驱动，保持setup重建并排除unknown顶点。
辉夜左袖单手轨失败数变为27（旧11），其他姿态也回归，故同样不保留。该试验不修改用户的归属标注。

```powershell
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --boundary-budget --support-mesh --joint-solver --baseline-envelope ../tmp/r3s-boundary-budget --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-joint-solver huiye uuz
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --boundary-budget --rigid-hand --baseline-envelope ../tmp/r3s-boundary-budget --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-rigid-hand huiye uuz
```

当前保留基线仍是两个右袖通过、两个左袖阻塞。下一步应实现袖口位置约束与旋转继承分离，
并将已具备的生成、回退与导出串成可恢复入口；不能把这些负向试验算作里程碑验收通过。

## 统一候选重建入口

新增[袖装统一工作流](how-to-sleeve-workflow.md)：从已保存草稿开始，一条命令执行8步默认链路，
自动解析地址、保存草稿快照和步骤收据、校验缓存并支持中断恢复。
结果页集中呈现每个区域的阻塞原因、时间轴与Spine候选下载；不把步骤完成状态提升为正式采用。
目前是CLI与派生结果页，主工作台按钮、Runtime自动编排和GPU/alpha验收仍未实现。

后续已接入可选的官方核心Runtime自动编排：`--runtime-core`绑定外置4.3.13包的精确文件，
作为独立可恢复步骤验证新导出候选，并在结果页显示报告。主工作台按钮与GPU/alpha接缝仍待实现。

## 主工作台袖装入口

已增加绑定规划页的袖装候选构建入口、项目隔离的后台队列、阶段状态查询和逐袖下载。
复用上面的默认CLI与收据，不新增权重算法或隐式采用权。任务重启显示中断，重建可恢复；
标注、项目版本或候选ZIP变化时下载明确失败。页面切换项目会丢弃旧响应，终态停止轮询。

R3-S仍未完成：两个左袖的局部变形，以及GPU/alpha接缝验收仍是实际缺口。

本切片实测：辉夜、幽幽子经后台队列完成九步重建，两个右袖候选ZIP读取及哈希检查通过，
左袖仍显示`motion_envelope_geometry_failure`。Web全量474项、后端相关24项测试通过，
含跨项目响应、中断恢复、重复提交、来源变化、ZIP篡改和文件长度门禁。

## 明确袖口的共享边界权重

`sleeve_cuff_harmonic.py`只调整同时邻接`cuff`和`hand`的共享顶点，且排除任何含`unknown`的顶点。
手部内部和其他区域保持原权重。沿网格邻接距离做固定128轮权重扩散，再按setup重新计算局部坐标；
使用语义、拓扑及距离，不包含角色名、图层编号或特定画布坐标规则。

四袖仍按原129采样、前臂±30°/手±30°/垂布±10°与四组组合动作复核。
辉夜左袖失败帧从`0/11/0/11/24/22/11`降到`0/0/0/0/13/11/0`；
其他三袖无回归。两个左袖仍阻塞。setup重建、权重归一、未知及手内部固定、相似变换不变性均有测试。

扩大到未标记袖口的手—垂布界面会回归；可选联合稀疏求解同样未通过逐帧非回归门禁，均不进入默认链。
默认`retained-sleeve-chain-v2`增加`cuff`步骤，以原`boundary`作为对照，逐袖只保留改善结果。
原工件不覆盖，新运行使用独立身份；时间轴指向最终袖口候选。

剩余问题诊断：`combined_pm`联合求解在辉夜的92/96/100采样点及幽幽子的88/92/96/100/104采样点
本身仍失败；这些点均是已求解关键帧，因此不能归因为仅有线性插值误差。
应继续检查手—垂布固定边界与可行的袖口位置约束，而非提高关键帧密度来掩盖问题。

本轮完整入口验证：两角色各10步执行完成，两个右袖官方核心数值检查与候选ZIP校验通过；
新版袖口结果用于后续导出门禁。相关28项测试通过，新增模块保持300行以下。

## 边长必要位移预算：四袖几何通过

原预算仅由面积约束推导。幽幽子左袖极值姿态的自由顶点132与固定顶点133之间，
回到QA边长上限至少需要31.712px位移，但当帧只分配25.839px；增加求解迭代或关键帧不能消除该矛盾。
新`area-edge-displacement-bound-cap50-v1`按三角不等式补充必要位移：
`max(0,当前边长 - 1.9 × setup边长) / 可移动端点数`。
最终预算仍受前臂长度50%硬上限约束，沿用10%余量，固定端点不移动；面积和边长QA门槛不变。
该下界不等于解的存在性证明，最终仍以实际重建和密集采样为准。

四袖7轨×129点全部通过，无三角形翻转；Spine 4.3.26转换后7轨×257点加密检查同样全部通过。
默认工作流升级为`retained-sleeve-chain-v3`，在原`cuff`步骤启用此预算，不增加新的操作阶段。
面积保持但边长过度伸展的合成fixture能复现旧预算失败、新预算修复，且固定端点不变；
另覆盖双自由端点、固定边失败、预算硬上限及相似变换不变性。

`tmp/r3s-edge-visual/{huiye,uuz}.png`是软件栅格setup/极值对照，不是GPU或官方渲染验收。
四袖可导出仍不代表正式采用；GPU与透明袖口连接检查继续待完成。

官方核心Runtime复核：4袖×7轨×257帧，共7196帧数值验证通过；两角色各10步完整流程完成，
再次运行20个检查点全部校验后复用，四个ZIP均通过完整性检查。相关29项测试通过。

## 袖口软件 alpha 接缝检查

新增 `tools/check-sleeve-contacts.py`。从导出报告回溯精确袖装标注，定位cuff与hand/sleeve/hanging_cloth共享边，
筛选源纹理中具备3×3不透明余量的探测点；按已导出Spine动画重算7轨×257姿态，
在原生像素中心执行双线性alpha采样与三角形覆盖检查。无可观测样本的界面保留复核状态，不静默计为通过。
工件记录导出、标注、纹理、骨架、姿态及分析代码身份；不依赖可被替换的预生成姿态JSON。

四袖有效采样共127729次，alpha<8失败为0。辉夜右/左各有1条界面缺少不透明源图余量，
保持`needs_review`；幽幽子两袖的所选界面均有可观测点，状态`cpu_coverage_passed`。
该检查是软件保守覆盖测量，未验证GPU混合、过滤与帧缓冲；所有工件仍为authority:none。

```powershell
python tools/check-sleeve-contacts.py --input ../tmp/r3s-edge-spine --output ../tmp/r3s-contact-verified huiye uuz
```

输出合同：`schemas/sleeve-contact-coverage-v1.schema.json`。当前GPU验证仍受浏览器访问策略限制，
不得通过更换启动方式或本地转发绕过；软件结果不能填补这一证据缺口。

```powershell
python tools/build-sleeve-helpers.py --motion-envelope --connection-domain --boundary-budget --cuff-harmonic --baseline-envelope ../tmp/r3s-boundary-budget --input ../tmp/r3s-cloth-anchors --output ../tmp/r3s-cuff-harmonic-replay huiye uuz
```
