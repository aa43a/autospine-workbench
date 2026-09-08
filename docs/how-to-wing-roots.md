# 翅膀内侧根部候选

解决上一版“零距离点落在翼片外轮廓”的问题。逐alpha连通域按躯干方向选内侧边界，
不使用到目标纹理的最短距离作为根部排名，也不生成隐藏像素或正式绑定。

## 运行

仓库目录设置PYTHONPATH=src后执行：
```powershell
python -m autospine_workbench.benchmark.wing_root_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --search ../tmp/r2b-mount-search/crino/search.json --html ../tmp/r2b-wing-roots/crino/review.html --output ../tmp/r2b-wing-roots/crino/roots.json
```

read_roots重放源search、contact、mounts、plan与原始图像，再逐字段比较重算结果。
Schema为wing-root-v1.schema.json；纯核心validate也执行重算。
所有旧合同和历史报告不变，所有root选择为null，draw_order_reviewed和occlusion_verified为false。

## 算法

alpha>=8四连通组件按面积降序、最小y/x确定顺序，最多4096组件，超限明确失败。
小于16像素的组件保留在报告，但不生成根部。
用组件重心到躯干参考点方向筛选朝内边界，保留距躯干最近距离加1%角色高度的边界带。
每组件最多3个候选，间隔至少max(8px,1%高度)，按到躯干距离和y/x确定排序。
未知内侧方向返回待复核，不猜左右解剖侧别；组件ID不是骨骼身份。

记录组件被目标alpha覆盖的比例、根部处目标alpha及根部到躯干33次采样。
组件ROI继续使用局部接触分析。这些全是二维投影观察，不是物理接触或真实遮挡证明。

## 琪露诺结果

4个主要组件各2个候选，共8个；28个微小组件全部保留，无像素删除。
截图显示红色新候选已移到翼片靠胸部的内端，橙色旧候选仍标在外缘用于对照。
主要组件投影覆盖约84.7%–92.1%，不能直接解释为隐藏根部。

补充wing_projection_similarity.compare检查图层原始RGBA重叠：17,378个双alpha>=8像素，
RGB与RGBA逐像素完全相同数量均为0；RGB平均绝对差81.292880，alpha平均绝对差124.925135。
因此不能仅凭覆盖率断言相同纹理重复，也不能据此批准遮挡关系。只比较双阈值重叠区域，
没有做颜色空间、预乘alpha或最终渲染比较。

13项针对性测试、真实Schema、源重放和浏览器32组件/8根部检查通过。
保留旧Spine输出、权重和绑定决定，没有新的Runtime验证。
浏览器工具tools/check-wing-root.mjs，参数为角色输出目录、依赖目录、Chrome路径。
页面../tmp/r2b-wing-roots/crino/review.html。

下一步可把这些根部候选接入可撤销选择与胸骨跟随预览，对实际运动进行检查。
仍需确认根部选择及层序；四个连通域并不自动意味着必须新增四根独立骨骼。
