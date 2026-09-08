# 服装、物件与翅膀挂接候选

本切片将 Rig Planner 中的宽泛语义复核展开为并列语义假设及可视挂接距离。
它不修改旧规划合同，不选择骨骼，不产生人工决定，也不生成Mesh或动画。

## 运行与来源

在仓库目录设置 PYTHONPATH=src 后运行：
```powershell
python -m autospine_workbench.benchmark.mount_candidates_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --plan ../tmp/r2b-rig-planner-cohort/alice/plan.json --html ../tmp/r2b-mount-candidates/alice/review.html --output ../tmp/r2b-mount-candidates/alice/candidates.json
```

替换角色目录可运行铃仙与琪露诺。需要完整源层计划，局部scope会拒绝。
CLI先用read_plan重放现有计划及来源，再生成和发布报告；read_mounts从内容地址重新执行。
Schema为mount-candidates-v1.schema.json；纯核心validate逐字段比较重算结果。
旧计划、绑定草稿和Spine包没有变化，Runtime没有重跑。

## 几何含义

profile为garment-prop-wing-mount-v1。alpha>=8像素以像素中心计，计算到骨骼head_xy的
最近距离；hand骨骼头部通常是腕部参考点，不是模型检测的抓握接触点。
归一化高度为所有源层bbox联合的高度，接近阈值固定5%，仅用于未校准的诊断提示。
每个候选同时保存骨骼参考点、最近像素位置、距离、缺失骨骼与原因码；不删除远处候选。

服装提供裙／裤假设和pelvis参考；物件提供手持／挂件／未知假设，对照双手、chest和pelvis；
翅膀对照chest和spine。名称或语义相互冲突、没有alpha、缺少骨骼、多个近邻均保留复核。
本版使用显式英文词元和已知语义；不覆盖任意名字和所有服装种类。

最近像素在服装内部，只说明投影相交，不能视为腰口。翅膀根部可能在遮挡区内，
远离chest参考点也不能证明它不该随躯干。源图层近邻不等于真实接触。

## 三角色结果

共5个部件：Alice服装与objects、铃仙服装、琪露诺服装与翅膀。
三层服装到pelvis距离均小于1px；Alice objects到hand_r参考点37.82px；
琪露诺翅膀到chest参考点74.56px，未达到5%接近阈值。
所有selected_option、confidence均为null，仍是needs_review。

9项针对性测试覆盖来源拒绝、平移不变性、空alpha、骨骼缺失、多近邻和合同Schema。
实际候选全部Schema通过并完成源闭包重放；浏览器检查5个部件和9个挂接连线。
浏览器回归工具：tools/check-mount-candidates.mjs，参数为输出root、依赖目录、Chrome路径。
导航页面：../tmp/r2b-mount-candidates/index.html。

下一步需要检查服装腰口、物件与手部接触、翅膀根部的局部边界，
将“骨骼参考点近邻”升级为“有局部接触证据的挂接候选”。不能将5%阈值变成自动批准门槛。
