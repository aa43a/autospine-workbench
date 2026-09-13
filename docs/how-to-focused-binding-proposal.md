# 集中复核剩余图层

当自动规则已处理安全项，仍有少量绑定需要人工确认时，可以导出一页集中方案。
每层同时展示整角色中的位置、候选骨骼与独立源图，不需要在多个报告之间寻找。
页面只读，输出的 `proposal.json` 不是已复核决定。

从仓库根目录运行，例如：

```powershell
$env:PYTHONPATH='src'
python tools/prepare-character-binding-review.py `
  --workspace .. --state-root workspace --project PROJECT_ID `
  --binding layer-000=rigid:head --binding layer-007=rigid:chest `
  --skirt layer-006 --output ../tmp/binding-review
```

`--binding` 必须是当前图层真实存在的选项。`--skirt` 只为当前裙装构建器支持的
bottomwear / bottomwear-front 提出独立裙摆候选方向，不会创造一个刚性绑定选项。
重复图层、未知选项、图像摘要不匹配或来源已变化会失败。

输出记录项目、来源地址、逐层图像摘要及具体选项。获得明确确认后，应通过既有绑定
复核入口保存；保存前重新验证来源。裙装还需构建及动作验收，头发刚性绑定不包含次级运动。

2026-09-13 咲夜：七层方案位于工作区 `tmp/character-sakuya-binding-review/index.html`。
前后发、头饰、双耳建议随 head，上衣随 chest，裙装建议使用独立裙摆链。
这七层在生成页面时均未新增人工确认，不能计入整角色完成率。

随后用户确认七层方案，六层刚性绑定已通过原复核接口保存，裙装方向进入构建。
回执见 `benchmark/sakuya-focused-binding-receipt-v1.json`；新候选四动作共 1,028 帧
官方 Runtime 技术验证通过，见 `benchmark/sakuya-skirt-three-motion-v1.json`。
18 层刚性已复核、2 层部分覆盖、3 层加权候选；没有静态参考层，但仍未完成整角色验收。
对 walk 第 256 帧的初次透明 PNG 预览曾显示头部外侧和腿间明显散点。
后续实际像素检查发现其中大量 alpha 仅 1/255 或 2/255；将同一捕获帧按真实透明度
合成到不透明棋盘背景后，先前的大片白点不再出现。因此初次预览不能证明可见渲染故障。
腿鞋残余归属仍待处理，但不应为透明 PNG 查看器的显示误差删除原素材。

可使用 `tools/inspect-framebuffer-alpha.py --image CAPTURE.png --expected-sha256 SHA
--output OUTPUT` 复查。SHA 应取自该任务的 Runtime 文件清单。
工具输出四种不透明背景合成、完整 alpha 统计及原捕获摘要，不修改源 PNG。
它是保存帧的诊断工具，不是新 Runtime 捕获，也不自动批准视觉结果。
