# 局部挂接接触诊断

接续mount-candidates-v1，检查骨骼参考点附近的源alpha真实边界与候选对应层。
本切片不选择挂接点，不改变语义或绑定决定；setup投影接触不代表真实接触。

## 运行

仓库目录设置 PYTHONPATH=src，然后执行：
```powershell
python -m autospine_workbench.benchmark.mount_contact_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --mounts ../tmp/r2b-mount-candidates/alice/candidates.json --html ../tmp/r2b-mount-contact/alice/review.html --output ../tmp/r2b-mount-contact/alice/contact.json
```

替换角色目录用于铃仙、琪露诺。导航为 ../tmp/r2b-mount-contact/index.html。
read_contact按source_mount_sha256重放挂接候选、Rig Planner、绑定和源图闭包，再重算结果。
Schema为mount-contact-v1.schema.json，纯核心validate执行精确重算比较。

## 算法及解释

alpha>=8；源边界定义为四邻域至少一处透明／图像外部的不透明像素。
从全源边界找到距骨骼head_xy最近像素（像素中心距离，相同距离按y/x排序）。
以该点为中心取半径ceil(源层联合高度*4%)的ROI。
目标边界在裁剪前计算，避免把ROI边缘错误算作附件边界。
3px棋盘距离检查源边界到目标alpha和目标边界的接近程度，同时统计ROI内部重叠像素。

分类分别为：两层边界接近、源边界覆盖目标内部、仅内部重叠、局部无支持、源无边界。
像素计数不等于接触长度；ROI外的边界可能不同；阈值未经真实人标校准。
对应层由候选绑定选项中包含相关骨骼的层检索；服装另外包含chest/spine选项层。
左右手选项可能同时指向同一源层，报告保留所有关系，不把尚未确认的侧别当真值。
无对应层不会自动找全图最近层代替。

## 本次结果

三角色9个有对应层关系：3个边界接近、1个源边界覆盖目标内部、5个局部无支持；
另有2个骨骼参考项没有对应层候选。
Alice objects与topwear出现22个边界接近像素，与本次handwear候选未出现支持；
琪露诺wings与topwear出现96个，bottomwear与topwear出现18个。
铃仙服装处于源边界覆盖目标内部；Alice服装最近侧缘ROI没有上衣支持。
这些数字不能被解释为自动绑定批准，也不能据此拒绝手持假设。

截图确认Alice服装ROI落在侧缘，说明“最近骨骼边界”不能定位腰口。
下一步需要增加语义约束的服装上缘搜索，以及真实手部接触和被遮挡根部的局部候选。
当前结果已把这一限制显式呈现，不应继续仅扩大ROI或放宽距离以获得通过。

11项针对性测试通过，涵盖裁剪边缘误报、近边界与内覆盖区分、平移不变性、空源及变更图像拒绝。
三份真实报告Schema和来源重放通过，浏览器检查11张卡片及9个ROI。
旧规划、挂接候选、Mesh、Spine动画和既有决定未改动；未运行新的Runtime验证。
浏览器回归脚本 tools/check-mount-contact.mjs 参数为输出root、依赖目录、Chrome路径。
