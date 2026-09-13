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
