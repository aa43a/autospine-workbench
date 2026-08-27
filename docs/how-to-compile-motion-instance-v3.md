# 编译并复验 P10.6b MotionInstance v3

本文是面向本地工作流操作者的 How-to。目标是把一份成功的 P10.6a CLI 输出编译为
MotionInstance v3，并用精确内容地址复验三文件 bundle。它不负责 Spine 4.2 导出、官方
Runtime 截图或发布授权。

## 前置条件

- 已有通过 `compile-body-sway-motion-consumer-admission` 生成的成功 JSON 输出；
- 输出中的 visual 与 seam review revision 在编译 P10.6b 时仍是 current head；
- 输出引用的精确 P9 MotionInstance v2/reviewed bundle 仍可严格读取；
- 在仓库根目录运行命令，并使用产生这些工件的同一个 `--state-root`。

先确认两个命令已经注册：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-instance-v3 --help
python -B -m autospine_workbench verify-body-sway-motion-instance-v3 --help
```

## 1. 保存 P10.6a 成功输出

重新运行 P10.6a，并把 stdout 保存为 JSON 文件。下面的占位值必须替换为实际项目、probe
路径和 SHA：

```powershell
python -B -m autospine_workbench compile-body-sway-motion-consumer-admission `
  PROJECT `
  --dynamic-seam-probe .\dynamic-seam-probe.json `
  --dynamic-seam-probe-sha256 PROBE_SHA `
  --state-root .\workspace `
  | Set-Content -Encoding utf8NoBOM .\motion-consumer-admission.json
```

输入文件必须是该命令的完整成功输出：`ok` 为 `true`、`status` 为 `compiled`，并包含
`admission`、精确 P9 地址和外层 head observation。编译器拒绝删减字段、额外字段、错误项目、
交叉引用、重复 JSON key、非 canonical JSON 和不匹配的显式 admission SHA。

如果使用的 PowerShell 不支持 `utf8NoBOM`，请用能够输出无 BOM UTF-8 的编辑器保存；不要把
UTF-16、格式化后的副本或手工摘出的 `admission` 子对象当作输入。

读取需要显式传入的 admission SHA：

```powershell
$admission = Get-Content -Raw .\motion-consumer-admission.json | ConvertFrom-Json
$admission.body_sway_motion_consumer_admission_sha256
```

## 2. 编译并发布 v3 bundle

```powershell
python -B -m autospine_workbench compile-body-sway-motion-instance-v3 `
  PROJECT `
  --admission-wrapper .\motion-consumer-admission.json `
  --admission-sha256 ADMISSION_SHA `
  --state-root .\workspace
```

成功输出为 path-free JSON，重点字段是：

- `address.motion_instance_v3_sha256`；
- `address.bundle_sha256`；
- `run_sha256`；
- `inventory`；
- `head_check.scope = prepublication_compile`；
- `head_check.permanent_authority_claimed = false`。

编译顺序固定为：严格读取 wrapper 与 P9 → 第一次 current-head observation → 纯 v3 编译及
待发布 bundle 重建 → 第二次 observation → 比较 exact identity/canonical bytes → 原子发布。
store 在任何目录写入前还会独立执行同样的 before → contract → after 门禁；成功发布后，命令
会按刚返回的双 SHA 重新读取、从 run 的精确地址重载 P9 磁盘闭包，并逐字节比较。任一门禁
漂移时不会发布成功目录；P9 在发布期间损坏或消失时，命令也不会报告成功。

相同 canonical 输入会复用相同内容地址。bundle 固定包含：

```text
body-sway-motion-consumer-admission.json
motion-instance-v3.json
run-manifest.json
```

存储地址为：

```text
<state-root>/builds/<project-id>/body-sway-motion-instance-v3/
  <motion-instance-v3-sha256>/<bundle-sha256>/
```

工作流不创建或解析 `latest`。

`run-manifest.json` 的 `authority` 只允许
`motion_instance_v3_emitted = true`。Spine adapter、runtime 等价、raster 视觉、永久 current-head
authority 与 release authority 均固定为 `false`；`release_gate.status` 固定为 `blocked`。

## 3. 按精确地址复验

把上一步输出的两个地址逐字复制：

```powershell
python -B -m autospine_workbench verify-body-sway-motion-instance-v3 `
  PROJECT `
  --motion-instance-v3-sha256 MOTION_INSTANCE_V3_SHA `
  --bundle-sha256 BUNDLE_SHA `
  --state-root .\workspace
```

验证器先检查固定库存、文件限制、bundle 地址和 run，再按 run 内显式 P9 地址加载上游，最后
重编 admission、MotionInstance v3 与 run 并逐字节比较。历史复验不会读取 current review
head；成功输出因此固定声明：

```text
head_check.scope = historical_replay
head_check.current_heads_observed = false
head_check.permanent_authority_claimed = false
```

这说明历史 bundle 可重放，不说明它仍拥有当前人工批准权。

## 常见失败

### 编译返回 `body_sway_motion_instance_v3_compile_failed`

依次检查：

1. wrapper 是否为完整 P10.6a 成功 stdout，且为 canonical UTF-8；
2. `PROJECT` 和 `--admission-sha256` 是否与 wrapper 完全一致；
3. wrapper 内精确 P9 bundle 是否仍能复验；
4. visual 或 seam review 是否在 P10.6a 之后产生了新 revision；
5. admission 是否超过 64 MiB，或 wrapper 是否超过 admission 加 2 MiB 的固定开销；
6. state root 是否与上游工件一致。

错误输出有意脱敏，不返回本地路径或内部异常。若 head 已变化，应从最新人工决定重新生成
P10.5d、P10.6a，再编译 P10.6b；不要修改旧 admission 伪装成 current。

### 验证返回 `body_sway_motion_instance_v3_verify_failed`

确认 project、v3 SHA 和 bundle SHA 来自同一次成功输出。任一文件被改写、增删、换行、改名，
或 run/P9 地址被交叉连接都会失败。验证器不会扫描相邻目录寻找“最像”的 bundle。

## 本阶段没有证明什么

P10.6b 只交付版本中立、setup-local、可严格重放的 MotionInstance v3：

- MIv2 root translation、markers 和 stepped draw order 逐值保留；
- body-sway rotation 只允许覆盖躯干四骨；
- source sampled-linear 语义被编译为 target `linear` timeline；
- release gate 仍然 blocked。

它没有证明 Spine 4.2 adapter 等价、官方 Runtime 加载、完整附件边界、raster 视觉或永久 head
authority。这些属于 P10.7。
