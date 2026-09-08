# 复核同帧局部透明度变化

此工具只读取已经捕获的官方Runtime原／候选PNG，不重新渲染、不修改候选权重。
先精确重放独立边界比较，再核验每张PNG的SHA、32×32尺寸、原／候选相同world rect和中心alpha。
分析alpha通道；显示的PNG直接复制原始字节，SVG仅标记数值分析的位置。

```powershell
python -m autospine_workbench.benchmark.seam_roi_context_cli `
  --config ../tmp/r2b-right-boundary/hub-config.json `
  --character alice --output-dir ../tmp/r2b-right-roi
```

打开输出的index.html，按中心alpha下降排序浏览原图、候选和新增低alpha分布。
黑框标出目标世界像素。蓝色表示所在透明连通区域触达裁剪边缘，红色表示4邻接下局部封闭；
每行另显示8邻接敏感性结果。这里“触达边缘”绝不等于全角色外部，“封闭”也不是已确认裂缝。

## 当前结论

- Alice右侧183个重叠ROI中，87个存在原alpha≥8、候选alpha<8的像素。
- 4邻接下6个ROI含局部封闭新增低alpha；8邻接下为0。ROI重复覆盖相同区域，不能累加成6处裂缝。
- 最大中心下降在frame55／pair13：211→116，中心仍不低于8；距最近低alpha像素约3.1623px。
- 该ROI新增8个低alpha像素都触达裁剪边缘；放大图更符合纹理边缘变化，但未排除开放式细缝。
- 不依据这些局部结果扩大Mesh、改变权重或自动回退Alice右侧；候选仍needs_review，无采用权。

15项针对性测试及长度门禁通过；Schema、精确reader、篡改拒绝及页面图像加载验证通过。
本切片复用732次Runtime捕获中的all模式PNG，没有新增Runtime帧，未跑全量测试。
报告按内容寻址保存，读者可用 `read_report`重算比对；Schema仅检查结构，reader负责完整语义。

下一步转向完整角色合成与接缝视觉回归，关注开放式细缝、原有空白和颜色／重叠。
不要为了消除单点alpha差继续扩展权重求解器或把ROI分类当成自动采用门禁。
