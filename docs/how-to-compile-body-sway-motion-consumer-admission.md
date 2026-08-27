# 编译 P10.6a body-sway 动作消费准入

P10.6a 把一份完整、内容地址匹配的 `BodySwayDynamicSeamProbe v1` 与其中明确绑定的
P9 reviewed-motion bundle 重新接合，供后续版本中立动作消费阶段使用。命令在编译前后
重新观察视觉复核与接缝复核 current head；它只产生一个零写入、path-free 的
compile-time admission。

该 admission 不是 MotionInstance v3，也不会新增 track、key、动画、Spine 导出或发布
资产。即使准入成功，完整 attachment 边界、raster/人工视觉、官方 Spine Runtime 等价
和 release authority 仍未得到证明。

## 前置条件

准备以下精确输入：

- `project_id`；
- 完整 canonical `BodySwayDynamicSeamProbe v1` JSON 文件；
- 该 probe 的完整 SHA-256；
- 包含 probe 内嵌精确 P9 bundle、视觉复核历史和接缝复核历史的 state root。

输入文件必须是 P10.5d stdout 中的完整 `probe` 对象，不是带 `ok`、`status` 和外层
`head_observation` 的 CLI 包装。命令会先重新计算 probe 内容哈希并执行完整语义重放，
不会信任文件名、旁路摘要、SHA 缩写或 `latest`。

P10.5d probe 还必须满足消费准入所需的认证状态。`indeterminate` 不是失败反例，但不能
进入动作消费准入。如果尚未生成输入，请先按照
[探测 P10.5d body-sway 动态接缝锚点](how-to-probe-body-sway-dynamic-seams.md)
完成前一阶段。

## 运行命令

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$Project = "<project-id>"
$Probe = ".\inputs\body-sway-dynamic-seam-probe.json"
$ProbeSha = "<body-sway-dynamic-seam-probe-sha256>"

$Raw = (& python -m autospine_workbench `
  compile-body-sway-motion-consumer-admission `
  $Project `
  --dynamic-seam-probe $Probe `
  --dynamic-seam-probe-sha256 $ProbeSha `
  --state-root .\workspace)
if ($LASTEXITCODE -ne 0) { throw $Raw }
$Result = $Raw | ConvertFrom-Json
$Result
```

命令不发布 bundle，也不修改 state tree。成功退出码为 `0`，stdout 是 canonical JSON；
顶层 `status=compiled` 只表示准入命令完成，不表示时间线或发布资产已经生成。

地址、文件、重放、P9 交叉绑定、认证状态或 current-head 检查失败时退出码为 `2`，
stdout 固定为：

```json
{"error_code":"body_sway_motion_consumer_admission_failed","message":"Body-sway motion-consumer admission compilation failed.","ok":false,"status":"error"}
```

错误响应不会暴露本机路径或底层异常。

## 检查输出

成功 stdout 顶层包含：

- `ok=true` 与 `status=compiled`；
- `project_id`、`clip_id`；
- `dynamic_seam_probe_sha256`；
- `reviewed_motion_address`，固定 P9 `motion_instance_v2_sha256` 与 bundle SHA；
- `body_sway_motion_consumer_admission_sha256`；
- 完整 `admission`；
- 外层 `head_observation`。

`body_sway_motion_consumer_admission_sha256` 只标识 `admission` 文档，不包含 CLI 包装或
外层 observation。结构合同见
[BodySwayMotionConsumerAdmission v1 Schema](../schemas/body-sway-motion-consumer-admission-v1.schema.json)。
JSON Schema 只检查结构约束；Python 语义 validator 仍须重放内嵌 probe、精确 P9 身份、
编译 profile、claims 和 release gate。

`admission.source.body_sway_dynamic_seam_probe` 是完整 P10.5d 文档，不是摘要。source 还
分别固定 dynamic/continuous source-set、ReviewedSet 双 SHA、RigIR、target profile、
preview projection 和 P9 七项身份。`admission.motion_domain` 固定包含：

- unit gain `{numerator: 1, denominator: 1}`；
- 与 P10 preview 相同的 sample ticks 和 sampled-linear rotation tracks；
- 与 exact MotionInstance v2 相同的 setup-local 坐标与 timing；
- 原样继承的 root translation、contact markers 和 stepped draw order；
- 分离的 base-channel 与 motion-domain SHA。

这些字段是后续编译输入，不是 MotionInstance v3。public validator
`require_body_sway_motion_consumer_admission(...)` 必须取得 exact verified P9 bundle；它
从 admission 内嵌 probe 重编 pure core。可选显式传入 `dynamic_seam_probe` 时，还会要求
它与内嵌文档 canonical bytes 完全一致。

如需保存 stdout，应先确认退出码为 `0`，再使用无 BOM UTF-8 写入审计文件。保存该文件
不会延长 current-head authority，也不会把它变成 bundle 或发布工件。

## 理解精确 P9 绑定

命令从 probe 完整 source closure 中读取 P9 的 `motion_instance_v2_sha256` 与
reviewed-motion `bundle_sha256`，再从显式 state root 按这对地址读取并严格复验 bundle。
它不会：

- 扫描其他 MotionInstance；
- 自动选择最新 P9 bundle；
- 用同 project/clip 的相邻文件替代缺失地址；
- 修改 MotionInstance v2；
- 编译 MotionInstance v3。

project、clip、MotionInstance v2 或 bundle 任一身份不一致都会 fail closed。

## 理解 current-head 检查

命令的固定顺序为：

```text
bounded dynamic-probe read + full semantic replay
                         ↓
exact P9 reviewed-motion bundle load + full verification
                         ↓
outer before observation
  ├─ visual history A → exact decision → history B
  └─ seam history A → exact decision/replay → history B
                         ↓
pure motion-consumer admission compilation
                         ↓
outer after observation（再次执行两项内层双快照）
                         ↓
before/after identity + canonical documents exact match
                         ↓
public semantic validation + admission hash
```

admission 内部 `head_observations.method` 固定为
`before-after-current-head-recheck`；CLI 包装的外层 `head_observation.method` 固定为
`outer-before-after-consumer-core-compilation`。两层 scope 都是 `compile_time`，且
`permanent_authority_claimed=false`。分析期间任一视觉或接缝 revision 漂移都会使整个命令
失败。命令完成以后产生的新 revision 不会改写历史 admission，但会使它失去“当前 head”
资格；后续实际 timeline consumer 必须再次检查 authority，不能只验证旧 SHA。

## 准入成功代表什么

P10.6a 只允许声明以下窄事实：

- supplied P10.5d probe 已通过完整重放并满足消费前置状态；
- probe 与 exact P9 MotionInstance v2/bundle 的 project、clip 和来源身份闭合；
- 视觉与接缝决定在本次编译窗口内仍是 current head；
- 该版本中立 motion domain 可以作为后续 timeline 编译器的输入。

因此 `claims` 中只有 exact source closure、compile-time current heads、连续 preview
结构认证、reviewed-anchor 工程距离认证与 setup-local timeline compilation admission
为 `true`。dynamic seam safety、完整 attachment 边界、raster/视觉、runtime、
MotionInstance v3/Spine adapter emission、publishable timeline 和 release authority
全部固定为 `false`。

它始终不能声明：

- 已生成 MotionInstance v3、通用动画或 Spine timeline；
- 完整 attachment 边界连续或不存在裂缝；
- raster/人工视觉已覆盖全部时间与幅度；
- 目标 adapter 与官方 Spine Runtime 等价；
- timeline 可发布或拥有 release authority；
- compile-time head observation 是永久审批。

P10.5d 的 `4 px²` 仍只是 reviewed-anchor point 工程代理，P10.6a 不会把它升级为完整
边界或视觉结论。

## 下一步边界

后续 MotionInstance v3 或其他版本中立 timeline compiler 应把本 admission 当作一个
需要重新验证时效的输入，而不是发布许可证。该阶段至少还要独立完成：

1. 将已证明的 setup-local motion domain 编译为明确的 timeline 合同；
2. 在消费时再次检查视觉与接缝 current head；
3. 对完整 attachment 边界做固定姿势、极值和时间区间的 raster/人工视觉回归；
4. 由操作者提供并确认授权的目标 Spine Runtime 做加载与截图回归；
5. 单独关闭许可与 release gate。
