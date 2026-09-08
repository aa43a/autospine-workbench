# 从残余显示差异反查源纹理

上一版显隐报告能指出帧和附件，但不能直接说明源纹理中哪些像素参与了差异。本切片在相同相机下重新捕获官方 Runtime 的实际世界顶点，将 framebuffer 像素中心反算到 UV，再给出双线性采样的四 texel 邻域。

## 复现与复核

先启动[残余显隐复核服务](how-to-limb-residual-review.md)。将下面 URL 替换成该服务输出的地址：

```powershell
node tools/capture-residual-locations.mjs 'http://127.0.0.1:14179/?character=crino' ../tmp/r2b-limb-residual-review-v2/report.json ../tmp/r2b-wing-limbs/crino ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' ../tmp/r2b-residual-locations
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.residual_location_cli --capture ../tmp/r2b-residual-locations/capture.json --output-dir ../tmp/r2b-residual-locations/review-v2
python -m unittest tests.test_residual_locations tests.test_quality -q
```

捕获分别选取各残余层的颜色变化峰值和隐藏后透明峰值，重新计算同帧统计并与已有报告完全比对。Runtime SHA、相机、候选地址及源纹理 SHA 不一致时拒绝输出。

打开 `review-v2/index.html`，每张卡片包括完整合成、仅隐藏本层残余、红圈采样位置、原残余纹理窗口和 alpha×32灰度诊断。原画布窗口坐标显示在标题下方。放大诊断只用于看清低 alpha，不进入任何生产纹理。四像素邻近分组仅用于排版，所有采样保留，未映射位置也不会丢弃。

`locations.json` 绑定捕获地址和候选地址，保留三角形索引、UV采样位置、四texel邻域及局部窗口。像素坐标分别标明 framebuffer 左下原点和纹理左上原点；反查的是采样邻域，不是删除遮罩或像素归属决定。

## 琪露诺结果：2026-09-09

6组附件／帧，共235次采样，全部成功映射；整理成46组局部窗口。

| 源层 | 颜色峰值帧 | 隐藏后透明峰值帧 | 峰值邻域最大源alpha |
|---|---:|---:|---:|
| handwear | 90 | 27 | 4 |
| legwear | 15 | 89 | 5 |
| footwear | 20 | 1 | 6 |

帧率为60。所有选中峰值采样的纹理邻域均没有 alpha>=8 的 texel，非零 alpha 范围为1–6；这个结论只覆盖采样邻域，不能推广到全部12,361个残余像素。

查看局部卡片，handwear第90帧最大组的29次采样落在翼片边缘附近，原画布窗口左上为(807,325)；这不是肩肘主体错位的证据。footwear第20帧最大组41次采样集中在鞋袜外缘，窗口左上(740,1143)，该组隐藏后没有alpha8穿越。原图窗口几乎透明，因此增加了显式标记的alpha放大视图。

8项测试通过，包括像素中心、旋转四边形、双线性邻域、未映射保留、非法输入、分组完整性、确定性和文件长度。真实浏览器确认46张卡片全部载入、无损坏图片。所有候选纹理、权重与动作保持不变。

下一步优先复用“低alpha边缘只转给唯一可靠邻近区域”的规则，生成这些局部采样邻域的归属候选，再做同帧回归。没有证据支持重新调整四肢主权重，也不应把峰值邻域之外的残余全部吞并。
