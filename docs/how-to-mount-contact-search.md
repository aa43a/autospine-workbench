# 语义约束边界搜索

在局部挂接诊断上增加搜索区域约束，不修改原mount-contact-v1或已有绑定决定。
新合同autospine.mount-contact-search/v1保存源contact地址、规则参数、候选点与局部证据。
候选点不是骨骼pivot，不自动选中，不增加Mesh或动画。

## 运行

仓库目录设置PYTHONPATH=src，然后执行：
```powershell
python -m autospine_workbench.benchmark.mount_contact_search_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --contact ../tmp/r2b-mount-contact/alice/contact.json --html ../tmp/r2b-mount-search/alice/review.html --output ../tmp/r2b-mount-search/alice/search.json
```

read_search先重放contact、mounts、plan和源闭包，再重算本候选；纯核心validate可直接比较重算结果。
Schema位于schemas/mount-contact-search-v1.schema.json。分析依赖沿用可选NumPy/Pillow。

## 规则

服装源边界限定在源bbox上部25%；手部关系双方边界限定在hand_l/r参考点周围8%角色高度；
翅膀双方限定在躯干参考点周围20%高度。物件与chest关系不在本次手部搜索能力内。
空窗口不回退到全图。源／目标边界来自alpha>=8的完整图层，不把ROI框作为边界。

分块计算每个源边界点到目标边界的最近欧氏距离；同距按源y/x、目标y/x排序。
最多保留3个候选，源点间隔至少max(8px,1.5%高度)。最多5000万点对计算，超出则显式返回资源限制。
每个候选复用原local_pair进行ROI分析。点对距离与整个ROI接触计数是不同指标。

## 三角色结果与视觉边界

9个对应关系产生15个点候选；4个关系没有本搜索策略的候选，保持说明。
Alice服装上缘最佳0px，截图已从旧侧缘移到腰带附近；铃仙上缘最佳0px。
Alice物件右手窗口最佳15.81px，仍有明显间隔，不能宣称抓握接触。
琪露诺服装上部最佳12.04px，保留不确定性。

琪露诺翅膀有3个零距离候选，但截图显示它们落在翼片外轮廓，不能标作根部。
这说明20%躯干邻域仍过宽，最近边界距离不足以定位根部；下一步应限制翼片朝躯干的内侧边界，
并检查源层内容重叠与遮挡，而不是把零距离当作通过。
本次不把名称、几何接近或截图推测提升成已确认语义。

12项针对性测试通过：上缘限制、空手部窗口、候选间距、平移确定性、无效几何，以及旧局部接触回归。
三报告Schema与源重放通过，浏览器检查15张ROI卡片和4项无候选说明。
导航为../tmp/r2b-mount-search/index.html。回归脚本tools/check-mount-search.mjs，
参数为输出root、依赖目录、Chrome路径。
未修改旧Spine输出、权重或决定；未重跑Runtime。
