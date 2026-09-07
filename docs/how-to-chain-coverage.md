# 默认选择与 alpha 覆盖分析

用户明确要求“按默认绑定关系确认 然后继续下一项”。本次据此选定已有
`suggested_option_id`：Alice 7项、铃仙7项、琪露诺5项，共19项。
无默认建议的43项保留pending，没有替用户猜选左右或双侧，没有自动排除图层。
[选择记录](benchmark/default-bindings-confirmed-2026-09-08.json)绑定精确候选和草稿地址。
确认结果保存为现有v2选择草稿，并通过CLI完整源闭包回读；不赋予生产发布权。
可编辑页面位于 `../tmp/r2b-multibone/{alice,lingxian,crino}-confirmed-v1.html`。

接续实现 `analyze-chain-coverage`，逐层分析具有Mesh骨链选项的原始RGBA图层，
对每个候选骨段测量固定样本的alpha覆盖，并保留所有候选作为对照。

```powershell
python -m autospine_workbench.benchmark analyze-chain-coverage `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --bindings ../tmp/r2b-multibone/alice-v2.json `
  --draft ../tmp/r2b-multibone/alice-defaults-confirmed.json `
  --html ../tmp/r2b-coverage/alice-v1.html `
  --output ../tmp/r2b-coverage/alice-v1.json
```

`--draft` 用于页面标识已选择的骨链，需要先通过绑定CLI封存；省略时只展示候选。
分析报告仅绑定不可变候选与源图，不随草稿选择改变，不改写用户选择或原始Pose。

固定profile：alpha≥8、4连通、每骨段21个等距样本、3px欧氏邻域。
组件按面积降序与稳定ID排序，最多显示32个；省略的组件数量和像素总面积单独记录。
质心和包围盒使用PSD画布坐标，包含原图层offset。4连通不会把仅对角接触的像素连为一体。
32M总分析像素、131072条扫描行区间和单PNG128MiB为资源限制，超过时明确失败。

橙框是组件，红线是覆盖率低于50%的骨段。此阈值仅作诊断提示，尚未做精度校准。
骨段低覆盖可能来自资产裁切、服装覆盖范围、关节位置或绑定方向问题；
高覆盖只说明附近存在alpha，不能证明语义、左右、关节或权重正确。
一个图层多个组件也不等于必须拆图；后续可在同一附件中生成互不相连的网格区域。

下一项：将覆盖区域接到关节支撑点和网格候选，再生成权重并做动态QA。
本切片没有生成网格或权重，不能将分析通过计为Mesh验收完成。

三角色实际8个多骨候选图层已分析并精确回读，结果见
[覆盖清单](benchmark/chain-coverage-2026-09-08.json)。Alice已选两条手臂链上臂15/21覆盖，
前臂和手均21/21；铃仙已选两臂各骨段均21/21。这里的分母是采样点数，不是准确率。
Alice腿层2组件，铃仙腿层5组件；细小组件可能是抗锯齿碎片，不把组件数当作肢体数。
22项相关测试通过，真实报告均通过JSON Schema验证；Chrome检查了Alice实际叠图。
未运行全量Python/Web或Spine Runtime测试，未改旧Mesh、Spine适配器或生产绑定状态。
