# 编译并复验 P10.6b v2 MotionInstance v3

本文是面向本地工作流操作者的 How-to。目标是从一个精确 P10.5d v2 bundle 自动闭合
P10.6a v2 与 P9，发布 MotionInstance v3，并按内容地址复验三文件 bundle。

普通操作者不需要选择 JSON 文件、保存 P10.6a stdout，或手工填写 admission/P9 SHA。
compile 只接收项目 ID 与 P10.5d v2 的 probe/bundle 双 SHA；verify 只接收项目 ID 与
MotionInstance v3/bundle 双 SHA。

## 开始前确认

必须同时满足：

- P10.5d v2 已成功发布认证 probe；
- 已取得同一 P10.5d v2 回执中的完整 probe SHA 与 bundle SHA；
- bundle source closure 引用的 P9 reviewed-motion bundle 仍可精确读取；
- P10.3c v2 visual head 与 P10.5b/P10.5c seam head 仍是 current；
- 命令使用产生上游工件的同一 `--state-root`。

如果真实 A 尚未实际生成 P10.5d v2 bundle，不要使用测试 fixture、旧 v1 地址或全零 SHA
代替。P10.6b v2 机制已经交付，不表示真实 A 已形成这份凭据。

先确认两个命令已注册：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench compile-body-sway-motion-instance-v3-v2 --help
python -B -m autospine_workbench verify-body-sway-motion-instance-v3-v2 --help
```

## 1. 编译并发布

在仓库根目录执行：

```powershell
$Project = "<project-id>"
$ProbeSha = "<p10.5d-v2-probe-sha256>"
$DynamicBundleSha = "<p10.5d-v2-bundle-sha256>"

python -B -m autospine_workbench `
  compile-body-sway-motion-instance-v3-v2 `
  $Project `
  --dynamic-seam-probe-sha256 $ProbeSha `
  --dynamic-seam-bundle-sha256 $DynamicBundleSha `
  --workspace . `
  --state-root .\workspace
```

该入口没有 P10.5d、P10.6a 或 P9 文件参数，也不接收 admission SHA。命令不会扫描
`latest`、下载相邻文件，或把同一项目的其他 bundle 自动当作替代品。

成功时退出码为 `0`，stdout 是 path-free JSON。重点保留：

- `address.motion_instance_v3_sha256`；
- `address.bundle_sha256`；
- `run_sha256`；
- `inventory`；
- `reused`；
- `head_check.scope = compile_time_and_prepublication`；
- `verification.status = passed`。

内部顺序为：

```text
P10.5d v2 probe/bundle 双 SHA exact read
                    ↓
从 source closure 自动 exact-read P9
                    ↓
before current visual-v2/seam-v1 heads
                    ↓
P10.6a v2 pure core、seal 与 detached replay
                    ↓
after current heads；identity/bytes 必须一致
                    ↓
编译 MotionInstance v3 payload
                    ↓
store 再次执行 prepublication before/after head gate
                    ↓
原子发布并按刚生成的双 SHA exact readback
```

任一地址缺失、固定 inventory 改变、跨项目或 clip 串线、P9 篡改、非 canonical JSON、
非有限数、head 漂移或发布后读回不一致都会 fail closed。

固定 inventory 为：

```text
body-sway-motion-consumer-admission-v2.json
motion-instance-v3.json
run-manifest-v2.json
```

存储地址为：

```text
<state-root>/builds/<project-id>/body-sway-motion-instance-v3-v2/
  <motion-instance-v3-sha256>/<bundle-sha256>/
```

同一 canonical 输入会收敛到相同内容地址，并通过 `reused` 告知是否复用了既有目录。

## 2. 按精确地址复验

把 compile 成功输出中的两个地址逐字复制：

```powershell
$MotionInstanceSha = "<motion-instance-v3-sha256>"
$BundleSha = "<p10.6b-v2-bundle-sha256>"

python -B -m autospine_workbench `
  verify-body-sway-motion-instance-v3-v2 `
  $Project `
  --motion-instance-v3-sha256 $MotionInstanceSha `
  --bundle-sha256 $BundleSha `
  --state-root .\workspace
```

verify 不选择文件，不读取 current head。它从 `run-manifest-v2.json` 的精确地址重载
P10.5d v2 与 P9，重建 P10.6a v2 admission、MotionInstance v3 与 run，再比较固定库存、
canonical bytes 和 bundle 地址。成功输出固定声明：

```text
head_check.scope = historical_replay
head_check.current_heads_observed = false
head_check.permanent_authority_claimed = false
```

这只证明历史字节可重放，不说明旧的人审结论仍是 current。

## v1 与 v2 来源链不可混用

| 入口 | 来源合同 | 文件选择 |
| --- | --- | --- |
| `compile-body-sway-motion-instance-v3` | 冻结 P10.6a v1 wrapper | 需要完整 wrapper 文件 |
| `compile-body-sway-motion-instance-v3-v2` | P10.5d/P10.6a v2 exact-address chain | 不选择文件 |

两条路径生成的 setup-local payload 都保持 `format_version = 3`。版本变化发生在 admission、
source closure、bundle 地址域和 run manifest；不得让冻结 v1 reader/command 静默接受 v2
bundle，也不需要仅因来源升级创建 MotionInstance v4。

## 常见失败

compile 失败时退出码为 `2`：

```json
{"error_code":"body_sway_motion_instance_v3_v2_compile_failed","message":"Body-sway MotionInstance v3 v2 compilation failed.","ok":false,"status":"error"}
```

依次确认：P10.5d 双 SHA 是否来自同一回执、project/state root 是否正确、上游 P9 是否仍可
读取，以及 visual/seam head 是否在执行期间产生新 revision。head 已变化时应沿 current chain
重新生成 P10.5d v2；不要修改旧 bundle 或 admission。

verify 失败使用 `body_sway_motion_instance_v3_v2_verify_failed`。确认项目、MIv3 SHA 和 bundle
SHA 来自同一次成功输出。验证器不会搜索相邻目录寻找“最接近”的工件。

## 本阶段明确没有证明什么

MotionInstance payload 仍是版本中立 v3：MIv2 root translation、markers 和 stepped draw order
逐值保留，rotation overlay 只允许躯干四骨，source sampled-linear 被编译为 target `linear`。

`run-manifest-v2.json` 只允许 `motion_instance_v3_emitted = true`。以下能力仍为
`false/blocked`：

- attachment area overlap 与完整 attachment 边界连续；
- dynamic seam safety；
- raster 或人工视觉质量；
- 官方 Runtime 等价；
- 永久 current-head authority；
- Spine adapter、publishable timeline 与 release authority。

下一开发项是让 P10.7a v2 source adapter 和自动化 UI 显式消费这条 v2 地址链。现有冻结
P10.7a v1 source contract 不能被当作 v2 adapter；在新 adapter、Runtime/raster 和人工门禁完成
前，不得把 P10.6b v2 成功解释为可发布 Spine 动画。
