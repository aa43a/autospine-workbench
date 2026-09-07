# 首批 Benchmark 冻结记录

执行代码为提交 `3117379`，全部32源文件的实际字节、大小和画布头信息与盘点一致。
未修改原始PNG/PSD，也未把文件名对应、坐标缩放或关节位置标记为人工批准。

## 工程划分

| 用途 | 角色 |
| --- | --- |
| Development（3） | 铃仙、琪露诺、爱丽丝 |
| Visible（4） | 蓬莱山辉夜、西行寺幽幽子、魂魄妖梦、露米娅 |
| Holdout（3） | 十六夜咲夜、八云蓝、芙兰朵露 |
| Reserve（10） | 小恶魔、雾雨魔理沙、大妖精、红美玲、蕾米莉亚、帕秋莉、伊吹翠香、博丽灵梦、八云紫、藤原妹红 |

选择规则：有PSD候选映射者优先、按源SHA排序；Alice曾被隔离审计，因此固定进入
development。按3/4/3分配前10个，其余reserve。此为明确工程划分，存在素材可用性
选择偏差，不能外推到任意人物。已知芙兰朵露画布为横幅；若后续不支持，应计入失败
并说明输入原因，不能在测试后将其移出holdout来改善分数。

yaomeng与yaomeng1均保留在同一魂魄妖梦条目，随该原图属于visible，不当作两个
独立角色或拆到不同分组。两个PSD哪个对应有效源图、是否同源变体仍待人工确认。

## 可重放工件

- [原始身份导入](manifest-pending-v1.json)
- [分组提案](split-proposal-v1.json)
- [冻结manifest](manifest-frozen-v1.json)
- [32源文件验证](source-verification-v1.json)
- [初始空观测](observations-initial-v1.json)
- [初始指标](metrics-initial-v1.json)
- [仅开发集输入检查](input-quality-development-v1.json)

冻结manifest地址为 `ab91a9b8a7a6f0a07a933800e5627c18004c70e3f9aa8c35daf1203c9edb4b1c`。
对应不可变store副本由Benchmark CLI发布；文档JSON是同一规范字节的导出。

初始指标：首批0/10完成、10个not_run；全部20个均not_run。没有执行绑骨评测，
所以P50/P90、自动采用抽查准确率和覆盖率均为null，不是0秒、100%或通过验收。
source verification的32/32 verified只证明源文件身份，不能算作32次成功绑骨。

开发集3张PNG仅做alpha/画布检查，阈值8/32下当前无预设告警。这不说明完整全身、
姿态、语义、关节、PSD分层或可变形质量已通过；这些仍需独立证据与复核。
没有读取holdout原图做输入分析或根据holdout调阈值。

## 开发集 PSD 审计

另外对开发集3个PSD执行了固定脚本的隔离审计，原图和旧项目均未更改。
[审计身份清单](development-audit-2026-09.json)封存脚本、环境和79个文件的字节身份：

| 样本 | PSD画布 | 像素层 | 观测 |
| --- | --- | ---: | --- |
| 铃仙 / lingxian | 1280×1280 | 21 | 仅结构与像素审计，未批准语义 |
| 琪露诺 / crino | 1280×1280 | 18 | 1个空层，17个可见层；需要复核保留规则 |
| 爱丽丝 / alice | 1024×1024 | 23 | 仅结构与像素审计，未批准语义 |

审计材料位于workspace的 `tmp/benchmark-development-audit-2026-09`，包含3份audit、
composite、embedded composite、contact sheet和62张逐层PNG。没有注册到主工作台
项目发现，也没有填写source_to_psd_transform或任何人工决定。

新增合同、CLI、指标、输入分析与维护性合计40项测试通过；5类真实记录通过Schema
校验，3份开发集alpha报告通过语义验证。完整Python基线针对此前独立固定2cb411f，
结果见[静止checkout报告](../baseline-frozen-checkout-2026-09.md)，不能混记为本提交的全量运行。

## 下一步

图层语义接续切片已为3个开发PSD核验62张逐层PNG，输出19项词汇范围内的名称建议：

| 开发样本 | 图层 | 明确名称建议 | 空层 |
| --- | ---: | ---: | ---: |
| [爱丽丝候选](semantic-alice-candidates-v1.json) | 23 | 5 | 0 |
| [铃仙候选](semantic-lingxian-candidates-v1.json) | 21 | 5 | 0 |
| [琪露诺候选](semantic-crino-candidates-v1.json) | 18 | 5 | 1 |

15项仅是名称建议，不是正确率或自动采用覆盖率。真实标注均保持语义空值、左右unknown、
纳入undecided；未读取holdout，未提交人工语义决定或关节真值。琪露诺headwear虽有
非零bbox，但审计alpha_nonzero=0，因此保留空层复核，不自动排除。

最新页面为 `../tmp/benchmark-semantics/{alice,lingxian,crino}-review-v1.html`，
相对仓库根目录。候选经真实源文件核验、Schema验证、CAS精确重放后封存；
琪露诺离屏Chrome显示检查见同目录 `crino-review-v1.png`。
本轮112项Benchmark回归通过（19.923秒），维护性3项通过；完善Schema字符串边界
和中文说明后10项CLI/UI复测通过（2.234秒）。[入口说明](../how-to-benchmark-semantics.md)。

显式映射复核接续切片：新版页面末尾可填写接受/拒绝请求，默认未选择任何结果或
检查项；CLI 重新核验源文件、要求显式人工确认后才保存决定。只有 exact accepted
决定可以生成空的 pending 标注模板。拒绝、缺确认、过期请求和篡改决定均已测试。
本版没有隐式最新决定或撤销语义，复核人字段为本地声明，不是身份认证。

当前页面为 `../tmp/benchmark-mapping/{alice,lingxian,crino}-formal-review-v1.html`
（相对仓库根目录）。琪露诺真实 Chrome 完整显示检查见同目录
`crino-formal-review-full.png`，结果/复核人/原因/检查项均保持默认未填写。
全部 Benchmark 94项通过（17.235秒），维护性3项通过（0.092秒）。决定测试使用
隔离临时数据及 TEST ONLY 复核人；没有替真实开发集填写或记录人工接受决定，
原三个候选地址、旧 Runtime/认证证据和真实真值状态均未改变。

锚点校准接续切片：新增点击对应点、图上编号、撤销/清空和草稿恢复；CLI 可据锚点
拟合逐轴缩放/平移，生成残差报告及新叠加页。退化/高残差不应用变换，报告读取时
精确重算输入闭包。尚无真实人工锚点录入或映射批准，初始三个候选地址不变。

最新本地页面为 `../tmp/benchmark-mapping/{alice,lingxian,crino}-anchors-v1.html`
（路径相对仓库根目录）。琪露诺真实 Chrome 离屏显示检查见同目录
`crino-anchors-v1.png`；图片与控件正常显示不代表完成校准。
本切片全部 Benchmark 74项通过（15.895秒），维护性3项通过；最后草稿ID恢复和
静态误差提示调整后，CLI/页面11项复测通过（2.020秒）。数值测试用合成对应点，
没有代替操作者在真实图片上录点或生成真实校准报告。

2026-09-07 接续切片已交付[开发集坐标复核页](../how-to-benchmark-mapping.md)：
原 PNG 与 PSD 合成图可并排/叠加查看，支持缩放、平移、镜像、草稿下载与重载。
三个初始候选均经 Schema、语义 validator 和不可变 store 精确读回复验：

- [爱丽丝候选](mapping-alice-candidate-v1.json)
- [铃仙候选](mapping-lingxian-candidate-v1.json)
- [琪露诺候选](mapping-crino-candidate-v1.json)

本地生成页为 `../tmp/benchmark-mapping/{alice,lingxian,crino}-review.html`
（路径相对仓库根目录）。仅读取所选 development 的 PNG、PSD 和合成 PNG，未打开
holdout。爱丽丝经真实 Chrome 离屏显示检查，原图/PSD 角色尺寸与位置差异在叠加页
清晰可见，证明默认 canvas-fit 假设不能直接当真实对齐。截图保存在同目录
`alice-final.png`；这不是正式人工批准、Spine Runtime 或标注准确性 golden。

本轮 Benchmark/映射/交互/维护性合计60项通过（13.041秒）。独立审查发现
畸形 audit.characters 会产生未捕获异常，修复后7项CLI复测通过（1.269秒），其中
新增1项畸形输入回归。Node 交互测试执行了镜像、数值拒绝、下载与重置逻辑。
没有重跑旧内核全量，也没有改变上一切片固定基线的统计范围。

先处理开发集的PNG↔PSD候选对应、缩放/裁切/补边/镜像和坐标系，再准备可人工复核
的关节/语义真值与真实候选观测。自动采用先记录建议并核对正确性，满足高精度条件后
才启用可撤销决定；本切片未增加policy_auto生产写入，也未宣布自动绑骨MVP完成。

2026-09-07 关节录入与语义采用切片：新增 PSD 画布 17 关节草稿、离线录点/撤销/
不可观测原因/恢复，以及绑定候选和草稿的显式语义复核请求与决定。决定仅用于
Benchmark 语义，不授予生产权限。CLI 重验素材和审计闭包；改过的草稿须重新复核。

三个 development 样本生成 `../tmp/benchmark-joints/{alice,lingxian,crino}-v1.html`
和 `../tmp/benchmark-semantics/{alice,lingxian,crino}-adoption-v1.html`。共51个关节
仍未标注，未生成任何真实接受决定。关节草稿通过 Schema 校验，琪露诺页面经真实
Chrome 离屏检查图片与初始状态；截图为 `../tmp/benchmark-joints/crino-qa.png`，
不作为 Runtime 或关节准确性证据。原语义候选身份不变，holdout 未打开。

完整 Benchmark 回归128项通过（23.951秒），最终巨大整数边界及维护性7项复测通过。
新源码均低于300行。旧可信内核全量与官方 Runtime 本切片未重跑。下一步接入自动
关节候选对照和误差统计，真实精度需待人工标注与复核后计算。

2026-09-07 接续对照切片：已复用未修改的历史 `_layers` / `_skeleton` /
`AuditBBoxHeuristicProvider` 输出17点基线，并与关节草稿进行逐点对照。三个开发
样本生成 `../tmp/benchmark-joints/{alice,lingxian,crino}-comparison-v1.html`，同目录
保存 `*-baseline-v1.json`、`*-comparison-v1.json`。51个人工点仍未标注，三份报告
可比较数均0，中位误差均null，未把猜点或缺失值充当真值。

琪露诺页面经 Chrome 离屏检查，旧算法部分肩/手点明显落在错误部位，此项仅为
视觉诊断，不能量化真实关节精度；保留该基线用于后续Contact候选改进对照。
截图为 `crino-comparison-qa.png`，不是Spine Runtime证据。旧可信内核和4.2/4.3.26
Adapter均未修改；没有进行holdout调参或写入生产决定。

完整Benchmark回归142项通过（37.754秒），维护性检查通过，新源码均低于300行。
下一主线是Contact Geometry及关节候选质量，草稿正式复核后才计算验收精度。
