# 编译 body-sway 连续预览模型证明

> **冻结 v1 历史入口。** 本命令只重放 v1 amplitude candidate，不能消费
> P10.4a v2 admission。当前 v2 链必须等待独立的 P10.4b v2 合同和入口。

本步骤是 P10.4b2。它重放 P10.4b1 的精确输入，在已复核四骨幅度向量的
统一 gain 射线 `λ∈[0,1]` 上，对临时 preview 的每一对相邻 sampled-linear key
做保守区间分析。它可以证明固定预览数学模型的结构性质，但不会生成
MotionInstance v3，也不会解除发布门禁。

## 前置条件

先完成 P10.4b1，并保留相同的三份 P10 JSON 输入、全部显式地址和当前
`sampled_visual_approved` revision。命令会先重新编译 P10.4b1 candidate，连续分析
结束后还会再次检查 authoritative visual-review head；分析期间新增 revision 会使
本次运行失败，而不会留下过期的成功结果。

真实 runtime capture 仍必须来自操作者已授权的固定 Spine 4.2.119 runtime。
测试 stub 不能替代这项视觉证据。

## 运行命令

```powershell
python -m autospine_workbench compile-body-sway-continuous-proof `
  <project-id> `
  --candidates .\inputs\idle-behavior-candidates.json `
  --decision .\inputs\idle-behavior-decision.json `
  --probe-report .\inputs\body-sway-probe-report.json `
  --layer-manifest-sha256 <sha256> `
  --p3-rig-sha256 <sha256> `
  --p3-bundle-sha256 <sha256> `
  --motion-instance-sha256 <sha256> `
  --motion-retarget-bundle-sha256 <sha256> `
  --motion-instance-v2-sha256 <sha256> `
  --reviewed-motion-bundle-sha256 <sha256> `
  --temporary-preview-sha256 <sha256> `
  --runtime-capture-bundle-sha256 <sha256> `
  --capture-artifact-set-sha256 <sha256> `
  --visual-candidate-sha256 <sha256> `
  --visual-revision <revision> `
  --visual-decision-sha256 <sha256> `
  --state-root .\workspace
```

默认 stdout 是不含本机路径的摘要。增加 `--document-only` 可输出完整 canonical
`BodySwayContinuousPreviewProof v1`；命令仍为零写入。完整文档内嵌经过严格验证的
上游 temporary preview manifest，因此可能保留该合同允许的相对 artifact
`path`/`image_path`。这些不是本机绝对 state-root 路径，但完整文档也不应直接当作
公开 telemetry；需要公开摘要时使用默认输出。

成功返回码为 0。输入损坏、交叉接线、旧 revision、分析期间 head 漂移或重放不一致
时返回码为 2；错误 JSON 不暴露本地路径或底层异常。

## 证明域与算法

证明问题不是四个骨骼幅度各自独立变化的四维盒。`λ` 同比例缩放已经人工决定的
四骨 amplitude vector，固定 cycles 和 phase；时间域严格覆盖 temporary preview
中每一对相邻 sample tick。每段同时分析：

- sampled-linear 的 base rotation、body-sway overlay 与 root translation；
- setup-local FK、region/mesh 顶点、LBS 和画布 containment；
- 三角形 signed-area ratio、绝对面积退化阈值和 edge stretch；
- Q9 图层量化与 Q4096 顶点量化的半步误差包络。

后端使用向外舍入的 binary64 基本运算和固定有理 Taylor 三角函数包络，再对
`time_fraction × λ` 自适应二分。它不是密集点采样。默认每段最多 32,768 个 box、
深度最多 14，全部段共享 32,768 个 box 的全局预算。预算不足、后端异常、非有限数、
边界无法证明或后端返回自相矛盾的证明对象，都会降级为 `indeterminate`；不能转成
反例，也不能授予安全 claim。

顶层只有所有相邻段均通过时才是
`continuous_preview_model_structural_certified`，并且只允许以下两项为 true：

- `continuous_preview_model_structural_safety`
- `uniform_gain_zero_to_reviewed_structurally_certified`

任一段未证时顶层为 `indeterminate`，两项均为 false。每段保留 tick、保守 bounds、
box/terminal/depth 计数、scope、exclusions 和独立 evidence SHA，便于重放与审计。

## 明确没有证明的内容

即使所有段都获得结构证明，合同仍固定不证明：

- Spine 4.2 runtime 与本分析器的实现级等价；
- 目标平台 `libm` 与数学三角函数包络的逐位等价；
- raster 视觉质量和整个 gain 范围的人工视觉批准；
- attachment 之间的 seam 连续性；
- MotionInstance v3、可发布 timeline 或 release authority。

因此 release gate 始终是 `blocked`。下一步应独立编译静态 seam anchor candidates，
由人工接受、调整、拒绝或标记不可观测，再把 reviewed anchor set 接入动作证明；不能
从 mesh 内部连续性推断 attachment 间接缝安全。
