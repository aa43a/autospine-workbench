# 编译 P10.6a v2 动作消费准入

本文是面向本地工作流操作者的 How-to。它把一个已经发布并认证的 P10.5d v2 动态接缝
bundle，转换为零写入、版本中立的 setup-local 动作消费准入。

普通操作者不需要选择 JSON 文件，也不需要手工寻找 P9 文件。命令只接收项目 ID 和
P10.5d v2 的 probe/bundle 两个完整 SHA-256；本机会按这对精确地址读取固定三文件 bundle，
再从它的 source closure 自动定位并复验精确 P9 reviewed-motion bundle。

## 开始前确认

必须同时满足：

- P10.5d v2 已完成，并且 probe 状态是认证通过；
- 已取得同一结果回执中的完整 probe SHA 和 bundle SHA；
- 对应 P9 reviewed-motion bundle 仍可按 source closure 中的双 SHA 精确读取；
- P10.3c v2 visual head 与 P10.5b/P10.5c seam head 仍是 current；
- 本机工作目录和 state root 属于同一工作流实例。

如果真实 A 的 P10.4b/P10.5d 还没有完成，不要使用测试 fixture、旧 v1 probe 或全零 SHA
代替。当前机制已经交付，不代表真实样本已获得 P10.6a v2 凭据。

## 运行命令

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$Project = "<project-id>"
$ProbeSha = "<p10.5d-v2-probe-sha256>"
$BundleSha = "<p10.5d-v2-bundle-sha256>"

python -B -m autospine_workbench `
  compile-body-sway-motion-consumer-admission-v2 `
  $Project `
  --dynamic-seam-probe-sha256 $ProbeSha `
  --dynamic-seam-bundle-sha256 $BundleSha `
  --workspace . `
  --state-root .\workspace
```

这里没有 `--dynamic-seam-probe <file>` 参数。命令不会扫描 `latest`、相邻目录或文件名，
也不会把同项目的其他 bundle 当作替代品。

成功时退出码为 `0`，stdout 是 canonical、path-free JSON。顶层主要字段包括：

- `ok=true`、`status=compiled`；
- `project_id` 与 `clip_id`；
- `dynamic_seam_address.probe_sha256` 与 `bundle_sha256`；
- `reviewed_motion_address.motion_instance_v2_sha256` 与
  `reviewed_motion_bundle_sha256`；
- `body_sway_motion_consumer_admission_v2_sha256`；
- 完整 `admission` 与本次编译窗口的 `head_observation`。

失败时退出码为 `2`，stdout 使用稳定且不暴露本机路径的响应：

```json
{"error_code":"body_sway_motion_consumer_admission_v2_failed","message":"Body-sway motion-consumer admission v2 failed.","ok":false,"status":"error"}
```

## 命令自动完成的检查

执行顺序固定为：

```text
P10.5d v2 probe/bundle 双 SHA exact read
                    ↓
固定三文件 inventory 与完整语义重放
                    ↓
从 source closure 读取 P9 双 SHA并 exact replay
                    ↓
before：复查 current visual-v2 与 seam-v1 heads
                    ↓
pure core：构造 unit-gain setup-local motion domain
                    ↓
after：再次复查相同 current heads
                    ↓
before/after identity 与 canonical bytes 完全一致
                    ↓
detached replay + admission SHA
```

任何地址缺失、字节篡改、project/clip/P3/target/timing 交叉串线、P10.5d 未认证、P9
不一致或 current head 漂移都会 fail closed。命令全程零写入，不创建 bundle、revision
或 `latest` 指针。

## 输出中的动作域

成功 admission 固定选择 unit gain，并组织以下版本中立数据：

- P10 Preview v2 的 sample ticks；
- setup-local、sampled-linear rotation tracks；
- MotionInstance v2 原有 root translation；
- 原有 contact markers 与 stepped draw order；
- 独立 source、base-channel、motion-domain 和 head-observation seals。

这些字段让后续 timeline compiler 能精确消费同一动作，但它们本身不是新的动画工件。

## v1 与 v2 不可混用

| 入口 | 输入 | 状态 |
| --- | --- | --- |
| `compile-body-sway-motion-consumer-admission` | P10.5d v1 probe 文件与显式 SHA | 冻结，只保留历史重放 |
| `compile-body-sway-motion-consumer-admission-v2` | 项目 ID 与 P10.5d v2 probe/bundle 双 SHA | 当前 v2 精确地址入口 |

v2 使用独立 format/profile/hash domain。不能把 v2 bundle 交给 v1 命令，也不能修改 v1
Schema 或旧 admission 使其看起来支持 v2。

## 成功不代表什么

P10.6a v2 只声明：精确 P10.5d v2/P9 来源已闭合、编译期间 current heads 未变化，且
setup-local timeline compilation 可以进入下一阶段。它明确不代表：

- 已生成 MotionInstance v3 或需要一个 MotionInstance v4；
- 已生成 Spine timeline、adapter、atlas 或图片；
- attachment overlap 或完整边界连续已经验证；
- raster、人工视觉或官方 Runtime 已通过；
- current-head 观察具有永久效力；
- timeline 可发布或拥有 release authority。

这份 admission 本身不授予 release authority。即使后续 P10.6b v2 已能生成
MotionInstance v3，overlap、完整边界、raster、版本匹配的 Spine adapter、官方 Runtime
和发布凭据仍保持 `blocked`。

## 下一步

保留完整成功 stdout 和 admission SHA 供审计。冻结的 P10.6b v1 compiler 仍只消费
P10.6a v1 wrapper，不能直接接收 v2 admission；版本隔离的 P10.6b v2
bundle/run/reader 已交付，并继续输出 `format_version = 3` 的 MotionInstance payload。
下一步按[编译并复验 P10.6b v2 MotionInstance v3](how-to-compile-motion-instance-v3-v2.md)
使用项目 ID 与 P10.5d probe/bundle 双 SHA 完成编译，再进入 P10.7a v2 source adapter
与自动化 UI。不会仅为来源合同升级而创建 MotionInstance v4。

真实 A 只有在当前 P10.4b 完成、真实 P10.5d v2 bundle 生成且本命令实际成功后，才具备
这条后续链的输入。P10.6a v2 的单元测试或 fixture 不能代替这份真实凭据。
