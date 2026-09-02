# 准入已批准的 body-sway 视觉复核头（冻结 v1）

本文只说明冻结 P10.3c v1 链：如何把当前 `sampled_visual_approved` revision 编译为
`BodySwayReviewAdmission v1`。该文档是进入后续安全范围与连续时间分析的只读交接合同，
不是 MotionInstance v3、Spine timeline 或发布许可证。

它不能消费 completed v2 job 或 P10.3c v2 head。普通 v2 流程请使用
[P10.4a v2 自动准入页面](how-to-admit-body-sway-review-v2.md)，不要把 v2 地址手工填入本命令。

## 前置条件

准备以下同源证据：

- P10.0 candidates、P10.1 decision 与 P10.2 probe report 三个 JSON 文件；
- Layer Manifest/P3/P5/P9 链的 7 个完整 SHA；
- P10.3 runtime capture 的 preview SHA、bundle SHA 与 artifact-set SHA；
- 当前视觉 candidate SHA、当前 revision 和该 revision 的 decision SHA；
- 当前 head 的状态必须是 `sampled_visual_approved`。

不要从目录名猜 SHA，也不要使用缩写、`latest` 或历史中较早的 approved revision。可先运行
`prepare-body-sway-visual-review --document-only` 读取当前 history，把其中的 current revision
与 head decision SHA 作为 admission 参数；admission 命令会在内部读取精确 decision。若 head
在此后变化，重新读取并重新编译 admission。

## 1. 编译 admission

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -B -m autospine_workbench compile-body-sway-review-admission `
  <project-id> `
  --candidates .\review\idle-candidates.json `
  --decision .\review\idle-decision.json `
  --probe-report .\review\body-sway-probe.json `
  --layer-manifest-sha256 <layer-manifest-sha256> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --motion-instance-sha256 <motion-instance-sha256> `
  --motion-retarget-bundle-sha256 <motion-retarget-bundle-sha256> `
  --motion-instance-v2-sha256 <motion-instance-v2-sha256> `
  --reviewed-motion-bundle-sha256 <reviewed-motion-bundle-sha256> `
  --temporary-preview-sha256 <temporary-preview-sha256> `
  --runtime-capture-bundle-sha256 <runtime-capture-bundle-sha256> `
  --capture-artifact-set-sha256 <capture-artifact-set-sha256> `
  --visual-candidate-sha256 <visual-candidate-sha256> `
  --visual-revision <current-revision> `
  --visual-decision-sha256 <current-decision-sha256> `
  --state-root .\workspace
```

默认 stdout 是 path-free 摘要，包含 admission SHA、全部下游交接身份、claims 与 release
gate。命令不发布工件，也不修改 state tree。

## 2. 保存 canonical 文档

需要把 admission 交给下一阶段时，增加 `--document-only`。先检查退出码，再写文件，避免把
错误 wrapper 当作合同：

```powershell
$admissionJson = python -B -m autospine_workbench `
  compile-body-sway-review-admission <其余参数> --document-only

if ($LASTEXITCODE -ne 0) {
  throw "body-sway review admission failed"
}

[System.IO.File]::WriteAllText(
  (Join-Path (Get-Location) "body-sway-review-admission.json"),
  $admissionJson,
  [System.Text.UTF8Encoding]::new($false)
)
```

相同输入、相同 authoritative head 与相同 compiler profile 会得到相同 canonical bytes 和
`admission_sha256`。输出不包含输入文件路径、state root、reviewer notes 或运行时异常详情。

## 3. 检查结果边界

成功结果固定为：

- `status: admitted_for_safety_analysis`；
- `sampled_visual_approved: true`；
- `head_observed_at_compile_time: true`；
- `safe_range`、`continuous_time`、`reviewed_seam_anchors`、
  `publishable_timeline` 与 `release_authority` 全部为 `false`；
- `release_gate.status: blocked`。

编译器按以下顺序观察视觉历史：

```text
authoritative history snapshot A
              ↓
exact candidate / revision / decision replay
              ↓
authoritative history snapshot B
              ↓
A == B 且 decision 是当前 approved head
              ↓
BodySwayReviewAdmission v1
```

这只证明两次快照之间 head 没有变化。它不会赋予 admission 永久 authority。后续任何发布命令
都必须再次读取 authoritative history，并确认 admission 中的 candidate、revision 和 head
decision 仍是当前值。

## 失败处理

退出码 2 与 `body_sway_review_admission_failed` 表示 fail closed。常见原因包括：

- 三份 P10 文件或任一上游 SHA 交叉接线、损坏或不是同一来源链；
- capture 四段地址不匹配重新编译的 temporary preview；
- 指定 decision 不是当前 head，或当前状态是 reject/unobservable；
- 读取期间出现新的 visual-review revision；
- revision、SHA、candidate case 或 runtime capture 内容不合法。

错误输出故意不包含本地路径和内部异常。排障时重新运行 P10.2、capture prepare 与 history
读取，逐项比较 canonical stdout 中的完整 SHA；不要扫描 state 目录寻找“最近”的替代工件。

## 下一门禁

P10.4a 只提供后续分析的输入准入。P10.4b 应以该 admission 为显式输入，增加参数幅度区间、
区间内采样/连续时间分析和 reviewed seam anchors；仍需在最终发布点重验 current head。只有这些
证据形成独立、可重放的安全合同后，才讨论 MotionInstance v3 与 Spine timeline 发布。
