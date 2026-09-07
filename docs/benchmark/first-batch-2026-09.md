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

先处理开发集的PNG↔PSD候选对应、缩放/裁切/补边/镜像和坐标系，再准备可人工复核
的关节/语义真值与真实候选观测。自动采用先记录建议并核对正确性，满足高精度条件后
才启用可撤销决定；本切片未增加policy_auto生产写入，也未宣布自动绑骨MVP完成。
