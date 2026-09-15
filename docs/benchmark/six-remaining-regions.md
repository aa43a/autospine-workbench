# 六处剩余区域：当前内容与下一步

以 first-ten-workflow-v7 的当前候选重新读取内容寻址包，生成 `tmp/character-six-remaining-review/index.html`。只剩六个静态参考区域：五处含 alpha≥8 的内容、一处空纹理，无仅低透明度区域。

| 角色 | 区域 | 检查结果 | 下一步 |
| --- | --- | --- | --- |
| 铃仙 | layer-018 | 独立睫毛，位置在眼部 | 已生成 rigid:head 来源绑定方案，待确认 |
| 爱丽丝 | layer-022 | 发箍，位置在头顶 | 已生成 rigid:head 来源绑定方案，待确认 |
| 爱丽丝 | layer-008 | 腰侧人偶 | 待明确跟随位置；不能根据 objects 名字直接自动绑定 |
| 芙兰 | layer-000 | 翼层 | 保留此前翼部候选方向，尚未采用 |
| 芙兰 | layer-023 | 全透明头饰源图 | 修复空层可见性传递，不能仅改验收数字 |
| 幽幽子 | layer-004-unbound-residual | 袖部残余，有一个 alpha≥8 像素 | 保留，不在此前十二处授权范围 |

头部两层方案位于 `tmp/character-final-head-review/{lingxian,alice}/index.html`，包含原图、角色内位置、目标骨骼及来源摘要。已检查生成的上下文图；没有写入新绑定决定。

## 空层原因

芙兰当前语义候选 layer-023 的 `observed` 为 `empty: true, visible: false, alpha_nonzero: 0`；实际 123×77 PNG 的 alpha bbox 为 null。源图 SHA256 为 `036fd4f6c681eff3b355d614f80efba2e53fcb0a5aa65e992db0de43a8f126d1`。

`targets/spine43/workbench_preview.py` 和 `automation/character_coverage.py` 读取顶层 empty/visible，未读取上述 observed 标记。这解释了该源层仍被输出并进入待办。下一实现需同时处理编译可见性和覆盖账本，显式区分 observed 隐藏与用户覆盖；旧编译输出和内容地址必须保留，不能原地改写既有候选，也不能只放宽验收门禁。

只读来源复核结果保存在 `tmp/character-six-remaining-review/empty-source.json`。本轮未删除空图、未扩展十二处排除授权，未增加整角色完成数量。
