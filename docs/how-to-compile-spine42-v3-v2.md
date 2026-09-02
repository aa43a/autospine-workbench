# 自动生成并复验 P10.7a v2 Spine 4.2 v3 Adapter

本指南说明如何把已完成的 P10.6b v2 MotionInstance v3 转成可精确重放的 Spine 4.2
adapter bundle。普通操作者使用自动页面；只有排障、历史地址复验或脚本集成才需要 CLI。

## 普通操作：从 P10.6b 继续

1. 在 P10.6b v2 页面等待 MotionInstance v3 显示“已完成”。
2. 点击“继续生成 Spine 4.2 v3 Adapter”。不要另开一个没有参数的页面。
3. 新页面会自动携带 `job_id`、`safety_run_id`、`dynamic_run_id` 和
   `motion_run_id`，校验唯一来源并创建第一次 attempt。
4. 等待页面显示“Spine adapter 已发出”和“精确读回通过”。刷新页面会恢复同一任务，
   不会创建重复 attempt。
5. 查看“已密封文件”和“已完成与仍阻塞”。到此停止；当前页面不会启动外部 Runtime。

自动入口是
[P10.7a v2 Spine Adapter 页面](http://127.0.0.1:8765/spine42-v3-v2.html)，但必须从
completed P10.6b 页面进入。它不要求选择项目、文件或填写 SHA-256。

## 失败后如何处理

失败回执是不可变历史，不会被覆盖。

- 页面显示“失败，可重试”时，先检查来源和本地服务，再点击“确认并创建新 attempt”。
- 确认框取消后不会写入任何新 attempt。
- 页面显示终止失败时，返回 P10.6b 检查上游；系统不会用部分结果继续。
- 不要把旧 attempt 的地址与新 attempt 的结果混合使用。

## 成功后得到什么

每个成功 bundle 固定包含五个文件：

1. `skeleton.json`：Spine 4.2 v3 adapter 输出；
2. `skeleton.atlas`：附件区域与纹理页映射；
3. `skeleton.png`：透明纹理页；
4. `run-manifest.json`：v2 来源合同、输出身份和能力边界；
5. `export-report.json`：结构校验与阻塞门禁报告。

内容地址由项目、`skeleton_json_sha256` 和 `bundle_sha256` 组成，位于独立
`spine42-v3-v2` namespace。v2 使用自己的 source contract、adapter profile、skeleton hash、
run/report 合同和地址域，不会静默复用冻结 v1 地址。compile 发布后会按上述精确地址读回；
历史 verify 会从完整上游重建五个文件，不扫描 `latest`，也不读取 current heads。

## 如何解释成功

成功只授予：

```text
spine_adapter_emitted = true
```

它不表示以下事项已经通过：

- attachment overlap 或完整边界连续；
- 动态接缝安全；
- 官方 Spine Runtime 加载或 Runtime 等价；
- Raster 视觉质量；
- 永久 current-head authority；
- 可发布 Spine timeline 或 release authority。

因此 `release_gate` 固定为 `blocked`。现有 P10.7b v1 capture/reader 只接受冻结
P10.7a v1 地址，不能消费这里的 v2 skeleton/bundle SHA。下一开发项是 P10.7b v2
runtime-source bridge；它仍须由操作者明确授权官方 Runtime，且不会由本页面自动运行。

## 专业 CLI：编译

先在仓库根目录设置源码路径：

```powershell
$env:PYTHONPATH = "src"
```

从 P10.6b v2 成功回执复制项目 ID、MotionInstance v3 SHA 与 bundle SHA：

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3-v2 `
  <PROJECT> `
  --motion-instance-v3-sha256 <MOTION_INSTANCE_V3_SHA256> `
  --motion-instance-v3-bundle-sha256 <MOTION_INSTANCE_V3_BUNDLE_SHA256> `
  --workspace . `
  --state-root .\workspace
```

compile 只接受项目与 P10.6b v2 双 SHA，不接受 JSON 文件。它会重放
MotionInstance v3 → P9 → P5/P3 → RigIR/源 PNG，检查 current heads，发布五文件 bundle，
再执行 exact readback。相同 canonical 输入会收敛到相同 skeleton/bundle SHA。

## 专业 CLI：历史复验

从 compile 回执复制 `skeleton_json_sha256` 和 `bundle_sha256`：

```powershell
python -B -m autospine_workbench verify-body-sway-spine42-v3-v2 `
  <PROJECT> `
  --skeleton-json-sha256 <SKELETON_JSON_SHA256> `
  --bundle-sha256 <BUNDLE_SHA256> `
  --state-root .\workspace
```

verify 只接受项目与 P10.7a v2 双 SHA。它按历史精确地址重建来源、run、report 和五文件
inventory；不观察 current heads，因此只证明该历史产物仍可逐字节复验，不授予当前审批权。

查看完整参数：

```powershell
python -B -m autospine_workbench compile-body-sway-spine42-v3-v2 --help
python -B -m autospine_workbench verify-body-sway-spine42-v3-v2 --help
```

## 常见错误

- 页面提示缺少精确任务 ID：返回 completed P10.6b v2 页面，从“继续”按钮重新进入。
- CLI 报 compile failed：确认输入来自同一项目的 P10.6b v2 回执，而不是 v1。
- CLI 报 verify failed：检查项目、skeleton SHA 和 bundle SHA 是否来自同一 v2 回执。
- 想进入官方 Runtime：不要把 v2 SHA 填入旧 P10.7b v1 命令；等待版本匹配的 v2 bridge。

合同和信任边界见[架构说明](architecture.md)，能力状态见[功能参考](capability-reference.md)，
后续顺序见[开发路线](development-roadmap.md)。
