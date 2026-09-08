# Rig Planner v1

为已有骨架及绑定候选生成只读策略报告，分开表达静态预览选项与最终动画需求。
规划器不生成绑定决定、权重、表情或次级运动，不授予生产权。

## 运行

在仓库目录设置 PYTHONPATH 为 src，然后运行：
```powershell
python -m autospine_workbench.benchmark.rig_planner_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --draft ../tmp/r2b-focused-review/alice/binding-review-draft.json --html ../tmp/r2b-rig-planner/alice/index.html --output ../tmp/r2b-rig-planner/alice/plan.json
```
默认分析所有源层；重复添加 `--focus-layer <layer_id>` 可限制报告范围。Alice 本次范围
来自集成报告 b5b92e6639bc76ac1ba61fcac69dc9e58bdee6a99cc1b22e44b896a7a5193cd1 的14条 excluded_layers。
已存在的不同内容输出不会被覆盖；迭代时使用新输出路径。

## 合同和可复现性

`autospine.rig-plan/v1` / `semantic-alpha-bone-strategy-v1` 保存四类源地址：
semantic candidate、skeleton、binding candidates、完整 draft，以及每层 image SHA。
Schema 为 schemas/rig-plan-v1.schema.json；纯核心 validate 比较完整重算结果；
rig_planner_cli.read_plan 从内容地址存储读出并重放源闭包。

每层包含策略、理由、alpha证据、骨段采样、静态刚性候选、能力边界和下一动作。
alpha采用现有四连通实现、阈值8；每骨21个等距样本，以floor映射到源像素。
骨段采样并非面积覆盖率，也不证明附件应由该骨驱动。连通域数不自动授权拆分。
当前名称规则为显式英文词元及已有语义词汇；未知名、冲突名和证据不足回到复核。
置信度为null，未将规则命中伪装为校准概率。

## Alice 开发样本

本次14层：9个面部动画需求、3个刚性候选、2个语义复核。
面部层仍可提供随head的静态预览选项，但没有新增眼口动画。
bottomwear与objects均有5个连通域，保留语义复核；没有按数量自动切层。
最终中文页面为 ../tmp/r2b-rig-planner/alice/review.html。

验证：6项针对性测试、JSON Schema、精确源重放、14张浏览器卡片和截图检查。
未改动原draft、Mesh或Spine输出，也未重跑Runtime。
此结果仅是Alice开发集结果，不代表分类准确率；下一步在铃仙、琪露诺运行同一规则，
再根据明确语义补服装与物件的候选路线。表情和次级运动仍按原里程碑开发。


## 三角色全量比较

同一 semantic-alpha-bone-strategy-v1 已分析 Alice 23层、铃仙21层、琪露诺18层，共62层。
使用 r2b-completion 中各角色 *-draft-v1.json 作为输入，CLI 不传 focus-layer。
报告位于 ../tmp/r2b-rig-planner-cohort/<角色>/plan.json，review.html 展示源图证据。

| 角色 | 刚性 | Mesh | 分区Mesh | 次级需求 | 面部需求 | 语义复核 |
|---|---:|---:|---:|---:|---:|---:|
| Alice | 6 | 2 | 1 | 2 | 9 | 3 |
| 铃仙 | 6 | 2 | 1 | 2 | 9 | 1 |
| 琪露诺 | 5 | 0 | 2 | 2 | 5 | 4 |

统计是策略分布，不能用于声称正确率。已有bind记录分别7/7/5条，仍保持原状。
已选刚性头发仍可被标记未来次级运动需求，两者不冲突。
鞋层整层没有绑定选项时仍进入复核，不否定已有独立分区动画。
琪露诺头饰没有alpha>=8的像素；规划器不自动删除或采用该层。
本次没有针对角色名加规则，没有改权重或重跑Runtime。

汇总入口：python -m autospine_workbench.benchmark.rig_planner_cohort_cli，
参数 --manifest、--workspace、--output、--html，以及每角色一个 --plan。
汇总必须覆盖全部源层，拒绝不同profile、重复角色和局部范围。
read_cohort 通过每个plan地址重放源闭包后重算统计，拒绝修改统计或引用。
最终导航页：../tmp/r2b-rig-planner-cohort/summary.html。

浏览器回归：
```powershell
node tools/check-rig-planner-cohort.mjs ../tmp/r2b-rig-planner-cohort ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe'
```

下一步优先补服装、手持物和翅膀的语义候选及挂接关系证据。
需要把名称歧义消解后再规划运动，不根据连通域数自动拆图；独立人标尚未建立，准确率保持null。
