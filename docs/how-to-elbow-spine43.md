# Spine 4.3.26 手臂诊断包

本入口将已通过烘焙 QA 的手臂 Mesh 编译为独立 Spine JSON、原 PNG 与多页 Atlas。
它只导出已通过的 Mesh 图层；保留完整候选骨架用于坐标重建，但不替其它图层指定绑定。
不改变原正式 Adapter 的准入范围，不提升为正式发布工件。

```powershell
python -m autospine_workbench.benchmark export-elbow-spine43 `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --bake ../tmp/r2b-mesh/alice-bake-v1.json `
  --zip ../tmp/r2b-mesh/alice-spine43-elbow-v1.zip `
  --output ../tmp/r2b-mesh/alice-spine43-elbow-v1.json
```

解压整个 ZIP，保持 `skeleton.json` 与 `images/` 相邻，导入 JSON 后选择 `elbow-diagnostic` 动画。
`lingxian` 同理。琪露诺没有已选 Mesh，明确返回 `elbow_preview_mesh_required`，不导出空动画。

## 格式与验证范围

按 [官方 4.3 SkeletonJson 读取器](https://github.com/EsotericSoftware/spine-runtimes/blob/4.3/spine-ts/spine-core/src/SkeletonJson.ts)
核对了 `animations.<clip>.attachments.<skin>.<slot>.<attachment>.deform` 层级。
加权 Mesh 的 deform 按每个顶点、每个骨影响顺序保存局部偏移；权重列表不排序，避免偏移错位。
PSD y-down 转为 Spine y-up，骨角度、局部 y 和 deform y 同时反号。Rotate key 使用 `value`。
这不是旧顶层 deform 数据加一个 4.3 版本号。

`preview-manifest.json` 包含来源 Bake 地址、JSON/Atlas/PNG 摘要、导出和排除图层列表。
侧边 JSON 回执还记录整个 ZIP 摘要；ZIP 固定成员顺序与时间，重复编译逐字节一致。
`read_target_preview` 会重放来源、重建 ZIP 并精确比较回执。

目标编码测试验证 setup、弯曲关键帧和帧间局部偏移重建；这只是独立数值验证，不是官方 Runtime。
没有运行官方 Runtime 或 Spine Editor 导入自动化，因此保留 `runtime_status=not_evaluated`。

## 完整角色与接缝阻塞

当前仅 Alice、铃仙的四张已选手臂可进入该诊断包。其它图层（包括未烘焙的刚性图层）逐项列出，
`full_character_status=blocked`、`seam_status=not_evaluated`。
剩余绑定、身体与手臂接触锚点、动态接缝和 Draw Order 尚未验证，不能将这个包视为完整角色导出。
下一步应把完整角色的已确认刚性层组合进诊断场景，再处理未确认绑定与跨层接缝；
同时使用实际 4.3.26 Editor/Runtime 检查 deform 的目标行为。

## 本切片验证

[真实记录](benchmark/elbow-spine43-2026-09-08.json)保存两个 ZIP 与回执地址。
独立解码 JSON 后重算整条骨架和逐影响 deform，在每角色 241 个采样点与源 Bake 对照，
最大坐标误差小于 4×10⁻¹³px。32 项相关 Python 测试、Schema、ZIP 文件摘要与回执读回通过。
Alice 排除 21 层，铃仙排除 19 层，均在包内明确列出；这不是剩余层均无法处理的结论。
未运行全量 Python/Web 或官方 Runtime/Editor 导入。
