# 编译并复验 P10.5c 静态接缝锚点集

P10.5c 把一个仍为当前 head 的 P10.5b 决定投影为
`ReviewedSeamAnchorSet v1`。产物只保留固定六条关系及决定中已经物化的
attachment-local 锚点，不重新选择 candidate option，也不生成 fallback locator。

这一步会发布不可变 bundle，但仍不证明动态动作域接缝安全、视觉质量、官方 runtime
等价或可发布 timeline。以上结论必须由 P10.5d 及后续门禁单独建立。

## 前置条件

先完成 [P10.5b 静态接缝复核](how-to-review-seam-anchors.md)，并记录同一复核地址下的：

- `project_id`、Layer Manifest SHA、P3 rig SHA 和 P3 bundle SHA；
- SeamAnchorCandidates SHA；
- 当前 head 的 revision 与 decision SHA；
- 六条关系都为 `accept` 或 `adjust`，decision status 为
  `reviewed_anchor_set_ready_for_compile`。

`reject`、`unobservable`、旧 revision、旧 decision SHA 或读取期间变化的 head 都会
fail closed。命令不扫描目录、不读取 `latest`，也不自动挑选“最新”候选。

## 编译当前 head

在项目根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$Project = "<project-id>"
$Manifest = "<layer-manifest-sha256>"
$P3Rig = "<p3-rig-sha256>"
$P3Bundle = "<p3-bundle-sha256>"
$Candidate = "<seam-anchor-candidate-sha256>"
$Revision = 1
$Decision = "<seam-anchor-review-decision-sha256>"

$Raw = (& python -m autospine_workbench compile-reviewed-seam-anchor-set `
  $Project `
  --layer-manifest-sha256 $Manifest `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --candidate-sha256 $Candidate `
  --review-revision $Revision `
  --decision-sha256 $Decision `
  --state-root .\workspace)
if ($LASTEXITCODE -ne 0) { throw $Raw }
$Compiled = $Raw | ConvertFrom-Json
$Compiled
```

编译按固定次序执行：

```text
history A → exact historical decision → exact P3/candidate replay
          → pure ReviewedSet compile → history B → immutable publish/readback
```

只有 A/B 完全一致，且指定 revision/decision 正是 ready head 时才会发布。成功 stdout
是 path-free canonical JSON；`output.reviewed_set_sha256` 和
`output.bundle_sha256` 是后续唯一允许使用的双 SHA 地址。`head_observation.scope` 固定为
`compile_time`，`permanent_authority_claimed` 固定为 `false`。

bundle 位于：

```text
workspace/builds/<project-id>/reviewed-seam-anchor-sets/
  <reviewed-set-sha256>/<bundle-sha256>/
```

其 inventory 严格只有：

```text
seam-anchor-candidates.json
seam-anchor-review-decision.json
reviewed-seam-anchor-set.json
```

相同输入会复用完全相同的不可变地址；同地址存在不同字节、额外文件或不完整 inventory
时会拒绝，而不是覆盖。

## 按精确地址复验

```powershell
$Raw = (& python -m autospine_workbench verify-reviewed-seam-anchor-set `
  $Project `
  --reviewed-set-sha256 $Compiled.output.reviewed_set_sha256 `
  --bundle-sha256 $Compiled.output.bundle_sha256 `
  --state-root .\workspace)
if ($LASTEXITCODE -ne 0) { throw $Raw }
$Verified = $Raw | ConvertFrom-Json
$Verified
```

复验会按双 SHA 读取固定三文件 inventory，重放 candidate、历史 decision 和精确 P3
来源，并重新编译 ReviewedSet。它有意不检查 decision 是否仍为当前 head：旧 bundle
应当可以作为历史证据读取，但不能因此获得当前 authority。P10.5d 消费 bundle 前必须
重新检查 P10.5b current head。

## 失败语义

编译失败退出码为 `2`，stdout 的稳定错误码为
`reviewed_seam_anchor_set_compile_failed`；复验对应
`reviewed_seam_anchor_set_verify_failed`。对外消息不泄露本地路径。以下情况都会拒绝：

- 任一 SHA、project、revision 或大小写精确路径不匹配；
- candidate 与 P3、decision 与 candidate，或 ReviewedSet 与六项 source 交叉绑定失败；
- decision 不是 current ready head，或双历史快照间发生 TOCTOU 变化；
- 六条关系次序、锚点数、locator 类型/拓扑、canonical hash 或 summary 不一致；
- bundle 被篡改、出现额外文件、丢失文件或双 SHA 地址错误。

结构合同见
[ReviewedSeamAnchorSet v1 Schema](../schemas/reviewed-seam-anchor-set-v1.schema.json)。
JSON Schema 固定字段、六行顺序、常量 claims 与 locator union；Python validator 继续负责
canonical hash、锚点唯一性、mesh 拓扑、量化权重及跨文档绑定等 Schema 无法完整表达的
语义检查。

## 可选真实来源门禁

仓库的 A/B gate 只读重放两个 See-through 样本：A 的六条关系都可观测，可用
“每行第一个 option”构造纯编译 smoke；B 有四条不可观测关系，必须保持 blocked。

```powershell
$env:AUTOSPINE_VERIFY_REAL_REVIEWED_SEAM_SET_GATE = "1"
# 可选：$env:AUTOSPINE_REAL_STATE_ROOT = "E:\path\to\workspace"
python -m unittest tests.test_reviewed_seam_anchor_set_real_gate -v
Remove-Item Env:AUTOSPINE_VERIFY_REAL_REVIEWED_SEAM_SET_GATE
```

A 的 decision 带 `test-only-contract-gate` 身份和 `TEST-ONLY` 备注，只存在于测试内存，
不会写入 review history、bundle 或 golden。它只证明真实候选形状能够通过纯编译合同，
不代表艺术家看过或批准了锚点；真正的 P10.5c 资产必须来自 P10.5b 页面保存的精确人工
revision。B 也不会被 fallback 或测试决定静默升级为可编译状态。
