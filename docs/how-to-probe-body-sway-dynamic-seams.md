# 探测 P10.5d body-sway 动态接缝锚点

P10.5d 把一份完整的 `BodySwayContinuousPreviewProof v1` 与一个精确的
`ReviewedSeamAnchorSet v1` bundle 组合，在同一 body-sway 时间与统一 gain 域内证明
已复核锚点对的距离上界。命令只读、零写入；它不会生成 MotionInstance v3、Spine
timeline 或发布资产。

这是一项 reviewed-anchor point 工程代理。即使全部区间通过，也不表示 attachment
边界连续、raster/视觉接缝合格、官方 runtime 等价或拥有 release authority。

## 前置条件

准备以下精确输入：

- `project_id`；
- 由 P10.4b2 `--document-only` 保存的完整 canonical continuous-proof JSON 文件；
- P10.5c 输出的 `reviewed_seam_anchor_set_sha256`；
- 同一 P10.5c 输出的 `bundle_sha256`；
- 包含该 P10.5c bundle、视觉复核历史和接缝复核历史的 state root。

continuous proof 必须仍能完整重放 P10.4b1、RigIR、target profile、MotionInstance v2、
临时 preview 和 projection。ReviewedSet bundle 必须按显式双 SHA 读取并重放固定三文件
inventory。命令不扫描目录、不读取 `latest`，也不接受 SHA 缩写。

如果尚未保存完整 P10.4b2 文档，先按
[编译 body-sway 连续预览模型证明](how-to-compile-body-sway-continuous-proof.md)
运行 `compile-body-sway-continuous-proof --document-only`。不要把它的默认摘要包装当作
`--continuous-proof` 输入。

## 运行命令

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$Project = "<project-id>"
$ContinuousProof = ".\inputs\body-sway-continuous-proof.json"
$ReviewedSet = "<reviewed-seam-anchor-set-sha256>"
$ReviewedBundle = "<reviewed-seam-anchor-set-bundle-sha256>"

$Raw = (& python -m autospine_workbench `
  compile-body-sway-dynamic-seam-probe `
  $Project `
  --continuous-proof $ContinuousProof `
  --reviewed-set-sha256 $ReviewedSet `
  --reviewed-set-bundle-sha256 $ReviewedBundle `
  --state-root .\workspace)
if ($LASTEXITCODE -ne 0) { throw $Raw }
$Result = $Raw | ConvertFrom-Json
$Result
```

命令没有 `--document-only`：成功 stdout 已经包含完整、path-free 的 probe 和 head
observation。这里的 path-free 表示不泄露本机 state-root 或工件地址路径；内嵌上游合同
仍可保留其格式允许的相对 artifact path。成功退出码为 `0`。输入、地址、重放或
current-head 检查失败时退出码为
`2`，stdout 固定为：

```json
{"error_code":"body_sway_dynamic_seam_probe_failed","message":"Body-sway dynamic seam probe compilation failed.","ok":false,"status":"error"}
```

错误响应不会暴露本地路径或底层异常。退出码 `0` 只表示分析合同成功完成；
`probe.status` 仍可能是 `indeterminate`。

## 检查输出

成功 stdout 顶层包含：

- `ok=true` 与 `status=compiled`；
- project、clip、continuous proof、ReviewedSet、bundle 和 source-set 身份；
- `body_sway_dynamic_seam_probe_sha256`；
- 完整 `probe`；
- 外层 `head_observation`。

`body_sway_dynamic_seam_probe_sha256` 只标识 `probe` 文档，不包含外层命令包装和
head observation。`probe` 内保留完整 source closure、问题域、每段证据、固定 analyzer、
claims、status、release gate 和 summary。公开 validator 会重新分析完整 source，而不是
只检查 Schema 或相信已有摘要。

结构合同见
[BodySwayDynamicSeamProbe v1 Schema](../schemas/body-sway-dynamic-seam-probe-v1.schema.json)。
JSON Schema 固定字段、状态和常量 claims；Python validator 还会完整重放 source、重新
运行 analyzer，并比较 canonical evidence 与 release gate。Schema 通过本身不授予
current-head 或发布 authority。

如需留存本次 stdout，可在确认退出码后原样写入审计文件：

```powershell
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText(
  (Join-Path (Resolve-Path .) "dynamic-seam-probe-run.json"),
  $Raw,
  $Utf8NoBom
)
```

该文件只是历史审计副本。保存、复制、重新校验或拥有相同 SHA 都不会使其中的
`head_observation` 获得永久 authority；后续消费方必须重新观察两个 current head。

## 理解 current-head 双层检查

命令的固定顺序为：

```text
bounded continuous-proof read + full replay
                       ↓
exact historical P10.5c bundle load + source closure
                       ↓
outer before observation
  ├─ visual-review history A → exact decision → history B
  └─ seam-review history A → exact decision/replay → history B
                       ↓
pure dynamic-seam analysis and probe compilation
                       ↓
outer after observation（再次执行两项内层双快照）
                       ↓
before/after identity + canonical documents exact match
                       ↓
public semantic replay + probe hash
```

外层 `method` 固定为
`outer-before-after-analysis-of-inner-double-snapshots`。before/after 的内层 `method`
固定为 `visual-review-double-snapshot-plus-seam-review-history-a-b`。外层和内层 scope
都只有 `compile_time`，`permanent_authority_claimed` 固定为 `false`。

分析期间任一视觉或接缝 revision 改变都会 fail closed。命令结束以后出现新 revision
不会改写已保存文档，但会使它失去“当前 head”资格；不能把历史可重放性解释为当前
审批权。

## 证明域与 locator 支持

分析固定覆盖：

- ReviewedSet 中规范顺序的六条 torso-arm、pelvis-leg、leg-foot 左右关系；
- 每条关系的全部 2–8 对 reviewed anchors；
- temporary preview 的每一对相邻 sampled-linear tick；
- 时间分数与已复核四骨向量的统一 gain `λ∈[0,1]`；
- region–region、region–mesh 和 mesh–region locator 组合。

region locator 以 Q4096 attachment-local 点随 slot bone 刚性投影；mesh locator 以
Q65535 重心坐标组合动态 LBS 三角形顶点。v1 不支持 mesh–mesh 关系，遇到该组合会
fail closed，而不是改用 setup 点、最近顶点或 region fallback。

每个 box 对 parent/child world point 的平方距离做向外舍入上界。阈值固定为
`4 px²`，等价于 anchor point 欧氏距离 `2 px`。这是版本化的工程容差，不是经过视觉
标定的 seam 阈值；少量锚点也不能代表整条 attachment 边界。

只有上游 P10.4b2 status 为
`continuous_preview_model_structural_certified`，且每个 P10.5d segment 都是
`continuous_anchor_proximity_certified`，顶层才是
`continuous_preview_model_reviewed_anchor_proximity_certified`。这只会打开 reviewed
anchor proximity 工程 claim；`dynamic_seam_safety`、`visual_seam_quality`、
`runtime_equivalence`、`publishable_timeline` 和 `release_authority` 始终为 `false`。

## `indeterminate`、预算与异常

每段最大深度为 14、每段最多 32,768 个 box；全部段共享 32,768 个 box。证据必须满足
完整二叉细分计数、固定关系/pair inventory、有限上界与 reason 对应关系。以下情况不会
变成通过：

- anchor 上界超过 `4 px²` 或出现非有限包络；
- 深度、每段 box、全局 box 或参数分辨率耗尽；
- interval backend 抛出异常或返回形状、tick、计数、模型、reason 不一致的对象；
- 上游 P10.4b2 未获得结构认证；
- 任一 source、bundle、review head 或 canonical hash 重放不一致。

可完成分析但未证明的段保留完整六关系/pair 结构并标记 `indeterminate`；全局预算耗尽
后的段不会被省略。无效输入和 current-head 漂移则让整个命令以退出码 `2` 失败。两者
都不得解释为反例，也不得用于授予发布权。

## 运行可选真实边界门禁

真实 A/B gate 默认跳过，显式开启后只读现有 state：

```powershell
$env:AUTOSPINE_VERIFY_REAL_BODY_SWAY_DYNAMIC_SEAM_GATE = "1"
# 可选：$env:AUTOSPINE_REAL_STATE_ROOT = "E:\path\to\workspace"
python -m unittest tests.test_body_sway_dynamic_seam_real_gate -v
Remove-Item Env:AUTOSPINE_VERIFY_REAL_BODY_SWAY_DYNAMIC_SEAM_GATE
```

A 当前只允许用明确标注的 TEST-ONLY 内存 decision 验证静态 ReviewedSet mechanics；
golden 不含 genuine P10.5c current-head 与 P10.4b2 authority，因此测试不会伪造 dynamic
probe。B 的四条 `unobservable` 关系必须继续阻塞 ReviewedSet 编译。门禁前后会比较
workspace inventory；缺少精确输入时给出可诊断 skip，不生成 candidate、decision、
bundle 或 probe artifact。

## 下一步边界

P10.5d 关闭的是固定 preview 数学模型中的 reviewed-anchor point proximity 证据，不是
最终 seam 验收。下一阶段若生成 MotionInstance v3 或通用动画消费合同，必须重新检查
current heads，并另行加入官方 Spine runtime、固定 raster 截图和完整 attachment 边界的
视觉回归；不能直接把本 probe 的 stdout 或 hash 当作发布许可。
