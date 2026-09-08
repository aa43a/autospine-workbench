# 剩余图层结构候选

`propose-layer-structure` 分析补全草稿中仍未处理的结构图层。
它不会重复分析已确认绑定或新头部候选，也不会修改草稿或旧 Mesh。

```powershell
python -m autospine_workbench.benchmark propose-layer-structure `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --draft ../tmp/r2b-completion/alice-draft-v1.json `
  --html ../tmp/r2b-structure/alice-v1.html `
  --output ../tmp/r2b-structure/alice-v1.json
```

HTML 展示原图层、主要连通域边界、候选骨骼与阻塞原因。报告以
`structure-candidates/v1` 存储，reader 重放绑定、草稿、骨架和源 PNG 后重新计算。

## 分区条件

alpha≥8、4 连通；主要组件面积至少为 8 像素且占本层 alpha 像素的 1%。
最多报告 32 个主要组件，省略像素数显式记录，源图不裁切、不删除。
每个组件的重心分别计算到左右候选骨段的最近距离；左右来自骨架标签，不从画布方向推断。
距离差至少为骨架垂直高度的 1%，最近距离不超过其 15%，才提出侧别。
这些阈值是独立实验 profile 参数，不是经过 GT 校准的置信度。

legwear 对应 thigh/calf/foot；handwear 对应 upperarm/forearm/hand；
footwear 对应 foot。只有恰好两个主要组件且分别对应左右时，才提出组件分区候选。
其他情况返回 `layer_requires_split` 或 `component_side_ambiguous`。
同侧附属碎片、细线连接和骨架定位误差仍可能影响结果，需要可视复核。

bottomwear 只提出 `rigid_setup_only` 跟随 pelvis 的候选，需确认裙/裤语义。
这不表示裙摆变形、碰撞或多链权重已支持。不明物件和翅膀保留语义阻塞；
空层、隐藏层及其他已有阻塞不会因为新分析解除。

## 本切片边界与下一步

这一步产出结构候选，不产生新的 PNG、Binding Decision 或多区域 Mesh。
既有 19 项选择及新增 31 项待复核头部候选均保持原状态。
下一步根据组件身份构造无损分区掩码，明确低 alpha 与小碎片归属，验证 setup 像素重建；
然后连接分区权重和双腿/脚踝动作 QA。完整角色组合与 Runtime 验收仍未完成。

真实来源与结果见 [验证记录](benchmark/structure-candidates-2026-09-08.json)。
