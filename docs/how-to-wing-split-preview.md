# 从实际遮罩生成可回退的拆分候选

上传 `wing-split-draft/v1` 后，CLI 对照不可变边缘预览报告、上衣纹理身份和完整文件清单校验，再按整数笔刷语义栅格化。只有最终为 `remove` 的像素从本候选上衣中移除；`keep` 与未标注像素均保留。

移除图保存在 `split/removed-topwear.png`，原图另存在 `split/original-topwear.png`。原图可由剩余图与移除图重建，逐像素检查 alpha 和非透明 RGB。原始源文件、翼片纹理、根部、骨骼、动作、Atlas 布局保持不变。

`split/mask.png` 是 0/1/2 类别图，灰度值不是用于显示的 0/255 透明遮罩。`split/draft.json` 保存上传选择。新报告独立内容寻址并由 `wing_split_preview.verify` 重放校验，不赋予生产授权。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_split_preview_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-edges/crino/preview-manifest.json --draft 'C:/Users/Administrator/Downloads/wing-split-draft-v1 (1).json' --output-dir ../tmp/r2b-wing-split-applied/crino
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-split-applied ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

输出仍为 Spine 4.3.26 的局部诊断包；外置官方验证 Runtime 为 spine-webgl 4.3.13。导入 ZIP 中的 `editor/skeleton.json`，保留旁边的 images 目录。

## 2026-09-09 实际结果

用户草稿为 11 笔，移除 6,208 个可见像素。查看实际移除图后，确认主要内容是两侧下垂晶体和周围底色。6,112 个像素在此前重叠提示框之外，96 个在框内；提示框只覆盖前一步的主翼重叠，不是语义真值，所以框外不等于误涂服装。

四片主翼仍大体保留，摆动截图仍显示主翼重影。结果记录为局部素材清理候选，`ghosting_resolved=false`。原 review_queue 保留为拆分前提示，不能当成拆分后的视觉 QA。

7 项针对性测试通过。官方 Runtime 121 帧通过，与候选原图参考的最大通道差为 0。前后 5 个同帧对照中，约 2,200 个 framebuffer 像素改变，最大通道差 255；这是显式移除素材带来的变化，不能套用上一步仅低 alpha 边缘迁移的容差。

`review.html` 并排显示原图、实际移除图和剩余图。`edit-draft.html` 已载入用户的 11 笔，支持继续调整后另存。后续已新增 [主翼投影分组复核](how-to-wing-projection-review.md)，在保留现有清理结果的前提下生成四组待复核候选；不擅自扩张用户遮罩。
