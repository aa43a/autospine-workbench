# 编译并复验 P10.7a Spine 4.2 v3 Bundle

本指南用于把一个精确的 Body-sway `MotionInstance v3` bundle 编译为固定
Spine 4.2 profile，并发布为五文件、内容寻址的不可变 bundle。完成本步骤只证明
adapter 产物可重建；不会自动授予官方 Runtime、raster 视觉、永久审批或发布权。

## 1. 准备输入

先在项目根目录启动一个 PowerShell，并让源码包可见：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

需要准备三项值：

- 项目 ID；
- P10.6b 输出的 `motion_instance_v3_sha256`；
- P10.6b 输出的 `bundle_sha256`。

如果尚未生成这两个地址，先按 [MotionInstance v3 编译指南](how-to-compile-motion-instance-v3.md)
完成 P10.6b。compile 时，当前 visual/seam review head 还必须与 MIv3 绑定的来源一致；
历史地址有效不代表它仍能作为当前发布输入。

不要填写 `latest`，也不要从目录扫描结果中猜一个地址。编译器会从该 MIv3 地址向上
重放精确 P9、P5、P3、RigIR 与源 PNG；任一来源缺失或交叉绑定不一致都会失败。

## 2. 编译并发布

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3 <project-id> `
  --motion-instance-v3-sha256 <motion-instance-v3-sha256> `
  --motion-instance-v3-bundle-sha256 <motion-instance-v3-bundle-sha256>
```

命令会依次：

1. 按精确地址重放 MIv3 → P9 → P5/P3；
2. 在编译前后检查 visual 与 seam 当前 head；
3. 用显式 adapter v3 profile 生成 Spine JSON、atlas 与 PNG；
4. 原子发布五文件 bundle；
5. 按新地址重新读取，并从完整上游再次重建全部字节。

相同输入再次运行时只会复用完全相同的内容地址。成功 JSON 中需要保存：

- `address.skeleton_json_sha256`；
- `address.bundle_sha256`。

如果原子重命名完成后，父目录同步或最后一次 current-head 检查失败，命令仍返回失败；
内容寻址目录可能作为可复验缓存留在磁盘。目录存在不代表本次发布成功，也不会获得
current-head 或 release authority。只有随后完整检查全部通过时才允许复用该缓存。

默认地址结构为：

```text
workspace/builds/<project-id>/spine42-v3/
  <skeleton-json-sha256>/<bundle-sha256>/
```

固定库存为：

```text
skeleton.json
skeleton.atlas
skeleton.png
run-manifest.json
export-report.json
```

## 3. 复验历史 Bundle

```powershell
python -B -m autospine_workbench verify-body-sway-spine42-v3 <project-id> `
  --skeleton-json-sha256 <skeleton-json-sha256> `
  --bundle-sha256 <bundle-sha256>
```

verify 只读取这个历史地址，不读取当前 visual/seam head。它会从 run manifest 中取得
精确 MIv3 地址，再重放 P9/P5/P3 和源图，逐字节比较五个文件。

## 4. 如何理解成功结果

成功的 `run-manifest.json` 只允许：

```text
spine_adapter_emitted = true
```

以下能力仍为 `false`：

- `official_runtime_loaded`；
- `raster_visual_quality`；
- `persistent_current_head_authority`；
- `publishable_spine_timeline`；
- `release_authority`。

`release_gate.status` 因此仍是 `blocked`。P10.7a 不运行或捆绑官方 Spine Runtime，
也不把有限帧结构检查冒充完整 attachment 边界或连续 raster 证明。
run/report 的通过只表示结构能力与哈希库存自洽；它本身不证明时间线数值或 atlas 像素
来自上游。该来源一致性由 compile/verify 的完整上游重建和五文件逐字节比较保证。

## 5. 常见失败

- `body_sway_spine42_v3_compile_failed`：MIv3/P9/P5/P3 任一精确来源缺失、head 漂移、能力不支持或发布后读回不一致；
- `body_sway_spine42_v3_verify_failed`：地址错误、文件被改动、run/report 与 skeleton 不一致，或上游无法精确重建；
- 未知 timeline、attachment、constraint 或 interpolation：adapter 会直接拒绝，不会静默丢弃。

下一阶段 P10.7b 需要操作者明确确认已授权的
`@esotericsoftware/spine-player@4.2.119`，再完成官方 Runtime 加载、固定帧 capture、
完整 attachment 边界 raster 指标与人工批准。没有这组外部证据时不能解除发布门禁。
