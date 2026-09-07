# 复核刚性单骨与多骨 Mesh 骨链

新的 `build-layer-bindings` 入口支持一张图层关联多个骨骼，旧 `build-region-bindings`
及其v1草稿继续可用。两者是独立版本，不能把旧单骨草稿直接当成v2多骨草稿导入。

```powershell
python -m autospine_workbench.benchmark build-layer-bindings `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --skeleton ../tmp/r2b-skeleton/alice-v2.json `
  --html ../tmp/r2b-multibone/alice-v3.html `
  --output ../tmp/r2b-multibone/alice-v2.json `
  --draft-output ../tmp/r2b-multibone/alice-draft-v2.json
```

替换 `alice` 为 `lingxian`、`crino` 即可生成另外两个角色。
页面可选择绑定模式和骨链、记录拆层/语义问题或排除，整份保存/恢复与撤销。
CLI增加 `--draft <下载的文件>` 可以核验并封存编辑结果；使用新的输出文件名避免覆盖旧页面。

本版按名称生成覆盖假设：`handwear`、`arm`、`sleeve` 提供 `upperarm → forearm → hand`，
`legwear`、`leg` 提供 `thigh → calf → foot`。`-l/-r` 仅生成对应侧的未复核建议，
保留另一侧选项，避免镜像或上游命名问题；无后缀时提供左右和双侧两链选项。
双侧六骨是一个图层的可影响骨集合，不代表每个顶点分配六个权重。
名称归一化支持大小写、全角字符、空白；没有使用画布左右偷偷决定角色左右。

旧刚性绑定仍表示一个slot/region跟随一骨；多骨选项表示后续加权Mesh的影响骨集合。
页面三种颜色显示三个骨段，选择选项后弱化其它候选，便于看图核对。
辅助骨架、图层图片与完整候选地址关联，草稿只引用一个选项ID，不能携带未经验证的权重。

当前完成的是调整后的第1项：版本中立的单骨/多骨候选与复核入口。
尚未完成的步骤按顺序推进：

1. alpha覆盖分析与左右连通域候选，区分单侧、双侧、混合衣物及无关部件。
2. 围绕肘/膝/腕/踝生成支撑顶点、三角网格和骨段距离初始权重。
3. 权重平滑、刚性末端、每顶点最多4影响及归一化；双侧网格避免串侧。
4. setup重建、翻转、伸缩和接缝QA，再接Spine目标适配和实际Runtime探针。

选择骨链不生成顶点、三角形或权重，不计入Mesh通过数；名称建议不计为自动采用正确率。
空、隐藏、越界及上游骨架阻塞仍明确拒绝生成有效绑定选项。
拆层只用于实际左右/部件混合或加权不可行的问题，不再仅因一层覆盖多个骨段就要求拆分。

真实结果：Alice 3层、铃仙3层、琪露诺2层新增多骨链选项，共8层；其中4层提供双侧选项。
三角色共62层中23层有单骨或多骨建议，39层仍阻塞。全部初始草稿保持pending。
[来源与统计](benchmark/layer-bindings-v2-2026-09-08.json)记录精确地址。
25项相关测试通过，覆盖单/双侧骨链、草稿、浏览器选择验证、CLI源重放、旧版兼容及文件长度。
Chrome已检查实际骨链叠图；未运行全量Python/Web或官方Runtime，也未生成Spine Mesh导出。
