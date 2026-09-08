# 独立边界采样与Runtime对照

该采样不依赖候选的gap detector。根据固定reference的原alpha边界对应，将setup中点按x/y排序，
选择首项、中位项、末项（不足3项则去重），在0–2秒每1/30秒沿reference移动。
每个中点向下取整后加0.5，对原动画和候选取完全相同的世界像素单元。
它是3个代表性对应的时间覆盖，不是整段轮廓覆盖、曲线均匀采样或连续时间证明。

## 运行

```powershell
python -m autospine_workbench.benchmark.seam_boundary_probes `
  --reference ../tmp/r2b-continuous-anchor/alice-v1.json `
  --manifest ../tmp/r2b-continuous-anchor/alice/preview-manifest.json `
  --follower layer-002-r --output-dir ../tmp/r2b-right-boundary
```

将输出报告传给现有 `tools/verify-seam-local-runtime.mjs` 的第三个参数，
原包为 `r2b-continuous-anchor`，候选包为 `r2b-stable-fallback`，角色alice，profile为native-pair。
新来源使用 `seam-local-runtime/v3` 和 `probe_report_sha256`；旧v1/v2工件语义不变。
外部官方Runtime仍为4.3.13，导出目标4.3.26。

`benchmark.seam_boundary_comparison` CLI接收reference、reference-manifest、probe、runtime、candidate、
manifest、output-dir参数，精确重建采样，并检查原／候选manifest、全部截图和包文件SHA。
`read_comparison`重放相同来源，输出独立 `seam-boundary-comparison/v1`，不改写历史admission。
两个JSON Schema负责结构，精确reader负责坐标、配对、采样矩阵和来源等语义。

集合启动配置可选 `boundary_comparison`：包含report及上述六个来源路径。
加载时精确重放并绑定同一候选，页面明确显示“独立边界”样本及结论。
原疑似点准入报告保留；技术身份记录独立报告地址，不产生采用权。

## 2026-09-08 Alice右侧结果

- 3个原边界对应 × 61个时刻 = 183个目标；原／候选、pair/all共732张局部截图。
- 官方Runtime原／候选各121帧回归通过；页面集成另跑两角色各121帧。
- 58个目标pair与all合成alpha下降超过1，最大下降95。
- 原和候选183个中心目标均未低于alpha8，没有新增低于8的目标。
- 原边界增距仍1.727884px，几何仍通过；采样状态为review_runtime_alpha_loss。
- 15项针对性Python测试、Schema校验、精确reader和页面集成通过；未跑完整测试集。

alpha下降不等于裂缝；没有低于8也不能证明整个ROI无裂缝。
候选未更改，右侧仍待复核。下一步定位最大变化在边界内／外的位置，检查同帧ROI的
轮廓移动、颜色与重叠，再决定是否需要局部修复；不要为了让alpha差为零而盲目改权重。
