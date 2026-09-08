# 在整角色上下文中检查四肢候选

该诊断页将当前四肢动画放回完整来源图层中，支持时间轴、播放和隐藏静态上下文。
它不把其余图层自动绑定到root，也不将原图参考标记为完整角色动画。

```powershell
python -m autospine_workbench.benchmark.character_context_cli `
  --state-root workspace --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --atlas ../tmp/r2b-isolation/alice-v1.json `
  --candidate ../tmp/r2b-stable-fallback/alice/ffeba51258fee821bbd111a34f50e9e60023d7adb789cea16581cd655894b617.json `
  --output-dir ../tmp/r2b-character-context/alice
```

工具精确重放ownership atlas及原图来源，验证候选所有文件SHA和同一骨架setup。
根据atlas显式归属将腿／鞋源图层替换为动画分区，其他源图层按原顺序静态显示。
不会通过截取名字猜测分区归属，不会同时画出已替换的完整腿／鞋原图造成双重影像。
静态来源层不消费或改写其历史绑定决定；图层顺序仍是未复核的source order。

Alice来源为23层：腿／鞋两层对应4个动画分区，另21层作为静态上下文；
两层中共有570个残余像素仍被排除，没有补成绑定或静默归属。
界面因此可用于观察裙摆遮挡腿部的整体效果，但不能检验裙子跟随、全身动作或最终draw order。

网格复用既有elbow_bake_webgl绘制器，再由Canvas2D按源顺序合成静态图层。
没有使用Canvas逐三角形裁剪，因为该方式会引入可见伪接缝。
此页不是官方Spine Runtime，不覆盖最终GPU或生产门禁；正式候选包完全不变。

9项针对性测试和代码长度门禁通过。浏览器检查61个时刻非空且发生动画变化、
静态上下文切换及截图；未新增官方Runtime捕获，未运行全量测试。
报告包含每个源图层当前消费状态，按内容寻址保存，`read_context`可精确重算。

下一步将已有已确认的刚性绑定与当前分区候选整合到同一目标Adapter，
为尚未决定的层保留明确缺项，再做官方Runtime整角色合成与遮挡回归。
不要把本页中的21个静态来源层当成21个已经完成的动画绑定。
