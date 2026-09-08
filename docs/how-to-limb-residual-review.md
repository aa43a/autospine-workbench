# 四肢残余的同帧显隐复核

在标准骨架合并候选上，使用官方 Runtime 对照完整画面与临时隐藏残余的画面。该工具只操作当前显示，不修改纹理、权重、动画或绑定决定。

## 使用

```powershell
node --test tools/test-limb-residual-metrics.mjs
$env:KEEP_PREVIEW='1'
node tools/inspect-limb-residual-runtime.mjs ../tmp/r2b-wing-limbs/crino ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' ../tmp/r2b-limb-residual-review-v2
```

终端输出本机预览地址。页面可拖动时间，切换完整合成、隐藏全部残余、仅残余、按源层隐藏，以及白底／深色／棋盘背景。分组来自已绑定源工件的覆盖清单。未知模式拒绝，显隐后恢复同帧必须逐字节一致。

输出 `index.html`、`report.json` 和逐姿态 PNG。报告记录候选 SHA、Runtime 包版本与 SHA、采样工具 SHA、相机参数、逐帧指标和截图文件清单；源文件在采样前后重新校验，已有内容不同的输出不会覆盖。新工具通过现有 opt-in hook 接入，不改变原播放页或原 Spine 包。

## 指标的解释

对每一帧，分别隐藏每个源层的残余，比较同一相机下最终 framebuffer：

- `changed_pixels`：任意 RGBA 通道差大于1的像素数。
- `any_channel_changed_pixels`：包括差值1的所有变化像素，单独保留低 alpha 与量化差异。
- `pixels_exposed_by_hiding`：完整合成 alpha>=8，隐藏后 alpha<8的像素数。
- `changed_rect_bottom_left`：变化像素在 framebuffer 左下原点坐标系中的包围框，可定位到具体帧与附件。

这些是当前预览缩放下的显示像素，不是源纹理像素，也不是缺陷数量。隐藏导致透明只说明画面依赖残余，不证明原画面有裂缝，更不证明残余应该删除。

## 2026-09-09 琪露诺结果

候选地址 `d4edd539649de66ba75f314c58b05b3bbf2748d01ce5d291727c357a15e67acb`，121帧、三个残余分组，共363组同帧对照。

| 源层 | 源残余像素 | 通道差>1峰值 | 该峰值帧 | 包含差值1的变化峰值 | 隐藏后透明峰值 |
|---|---:|---:|---:|---:|---:|
| handwear | 8,188 | 62 | 90 / 60秒 | 699 | 3 |
| legwear | 3,709 | 21 | 15 / 60秒 | 597 | 3 |
| footwear | 464 | 50 | 20 / 60秒 | 103 | 2 |

三个分组在全部121帧均有非零贡献。除0、0.5、1、1.5、2秒外，页面还导出统计峰值所在的0.25秒和1/3秒，共21张对照PNG。它们没有获得删除或自动归属授权。

4项纯指标测试通过。真实浏览器检查了未知模式拒绝、五个姿态的显隐恢复、时间按钮、背景选择和原控件隔离；同 viewport 下的导出PNG与浏览器原生PNG逐像素一致。透明PNG查看时容易夸大浅色散点，深色浏览器合成未见同等明显表现，不能将其直接记为 Runtime 致命视觉失败。

下一步应在这些具体帧检查袖口／裙摆附近的像素归属与遮挡，保留当前固定动作，优先处理可确认的局部问题。没有证据支持整批删除12,361个残余像素，也不需要继续全局修改四肢权重。
