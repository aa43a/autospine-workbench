# 编译 body-sway 幅度包络候选

> **冻结 v1 历史入口。** 本命令只接受 `BodySwayReviewAdmission v1`，不能消费
> P10.4a v2 admission。当前 v2 链请使用独立的 job-only
> `compile-body-sway-safety-analysis-v2`，不要把 v2 地址手工填入本命令。

本步骤是 P10.4b1。它从一个仍为当前 head 的 `sampled_visual_approved`
复核结果，生成九个只读、可重放的离散结构候选。输出不是安全证书，不会发布
MotionInstance v3，也不会修改 state tree。

## 前置条件

先完成冻结 v1 P10.4a，并保留当时使用的三份显式 JSON 输入、十二项 SHA 地址和
一个 visual revision。若复核历史后来追加了 revision，旧批准结果会被拒绝；不要把旧
admission 当成永久 authority。

真实 runtime capture 仍必须来自操作者已授权的固定 Spine 4.2.119 runtime。
测试 stub 只能验证进程和协议，不能替代视觉证据。

## 运行命令

```powershell
python -m autospine_workbench compile-body-sway-amplitude-envelope `
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

默认 stdout 是 path-free 摘要。增加 `--document-only` 可输出 canonical
`BodySwayAmplitudeEnvelopeCandidate v1`；命令本身仍为零写入。如需保存，请由
调用方显式重定向到新文件，并把 stdout 当成不可变内容处理。

成功返回码为 0。任一输入损坏、交叉接线、批准 revision 已过期、分析期间 head
变化或 exact gain `8/8` 重放不一致时，返回码为 2，错误 JSON 不暴露本地路径或底层
异常。

## 九个 gain 的含义

分析器固定检查 `0/8, 1/8, …, 8/8`。每个 gain 同比例缩放已经人工选定的四骨
幅度向量，cycles 和 phase 不变；它不是四个幅度可独立组合的盒状参数空间。

- `8/8` 必须与 P10.2 sample stream、全部 checks 以及临时 Spine preview 的
  sampled-linear rotation keys 完全一致。它是唯一已有人审 sampled still 的点。
- `0/8…7/8` 是 hypothetical scaled keys，只获得相同固定 tick 上的 FK、mesh、
  canvas 和 shared-index 结构检查；没有视觉批准。
- 每个 probe 都有独立 evidence SHA；九项共享同一个精确 tick schedule。

不要从“较小 gain 均通过”推出两点之间通过，也不要假设结构状态随幅度单调。
离散点没有覆盖 sampled-linear key 之间的连续时间。

候选内嵌严格验证的 exact P10.2 report，因此 standalone validator 会把 `8/8`
的 schedule、stream、checks 和 passed 状态重新绑定到 admission 的 report SHA。
preview projection SHA 只由 exact command 摘要返回，不作为 detached candidate 中
无法自行证明的 authority。后续阶段必须重跑 exact command 和 current-head 检查，
不能只接收一份来源未知的 candidate JSON。

候选的 canonical UTF-8 大小上限为 20 MiB：其中 16 MiB 明确保留给合法的
P10.2 report、2 MiB 给 review admission，另有 2 MiB 给本阶段九个 probe 与合同字段。
该预算覆盖两个上游合同的最大合法输入，不会把较大的合法角色静默排除在本阶段之外。

## 固定阻塞项

合同始终保持：

- `safe_range=false`
- `continuous_time=false`
- `visual_range=false`
- `reviewed_seam_anchors=false`
- `motion_instance_v3=false`
- `publishable_timeline=false`
- `release_authority=false`

下一子阶段会针对实际 sampled-linear preview 段做保守连续区间分析；无法证明的
区间必须标记为 indeterminate。静态 seam anchors 及其人工 decision 是另一条独立
合同，不能由本候选隐式补齐。
