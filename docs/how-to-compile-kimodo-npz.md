# 编译 Kimodo SOMA77 NPZ

本指南把一份已经导出的 Kimodo SOMA77 NPZ 编译为版本中立 MotionIR，并发布为可重建验证的五文件 motion bundle。随后可沿既有 P5/P6 命令把同一动作重定向到不同二维 rig，再导出 Spine 4.2 bundle。

这是正式 P7 NPZ 边界。它不会运行 Kimodo、下载 checkpoint，也不会把未知 NPZ 当作可信输入猜测解释。

## 前提

在仓库根目录运行命令，并让本地源码优先进入模块搜索路径：

```powershell
Set-Location E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

准备三份彼此独立的文件：

- Kimodo 原始 `.npz`，不重存、不改 ZIP 顺序；
- 符合 [Kimodo NPZ source v1](../schemas/kimodo-npz-source-v1.schema.json) 的 sidecar；
- 符合 [Kimodo NPZ map v1](../schemas/kimodo-npz-map-v1.schema.json) 的显式投影映射。

可从 [source 模板](../examples/kimodo/soma77-source.template.json) 与 [正面映射示例](../examples/kimodo/soma77-front.map.example.json) 开始。模板中的 `replace`、全零 SHA、长度和帧数只是待填写值；不能直接用于真实文件。

## 1. 固定原始文件身份

先计算原始 NPZ 的字节长度和 SHA-256：

```powershell
$npzPath = (Resolve-Path .\inputs\kimodo-wave.npz).Path
$npzBytes = [IO.File]::ReadAllBytes($npzPath)
$npzSha = [Convert]::ToHexString(
  [Security.Cryptography.SHA256]::HashData($npzBytes)
).ToLowerInvariant()

[pscustomobject]@{
  sha256 = $npzSha
  byte_length = $npzBytes.Length
}
```

把结果写入 sidecar 的 `raw_npz.sha256` 与 `raw_npz.byte_length`。`frame_count` 和有理帧率必须来自同一次可信生成记录；不要根据文件名或相邻文件猜测。当前最多接受 4096 帧和 128 MiB 原始文件。

推荐在生成时记录完整 producer provenance：

```json
{
  "status": "recorded",
  "implementation": "nv-tlabs/kimodo",
  "repository_revision": "<40-or-64-lowercase-hex>",
  "model_id": "Kimodo-SOMA-RP-v1.1",
  "checkpoint_revision": "<40-or-64-lowercase-hex>",
  "checkpoint_manifest_sha256": "<64-lowercase-hex>",
  "generation_request_sha256": "<64-lowercase-hex>",
  "seed": 42,
  "sample_index": 0
}
```

如果历史导出确实缺少这些证据，只能明确写 `status=unavailable` 和允许的原因码；这表示“来源无法完整复现”，不会被伪装成已记录。`recorded` 只把 metadata 中的 digest 纳入内容地址，workbench 不会读取或认证外部 checkpoint manifest/generation request；操作者仍要保存对应原件和许可证记录。

SOMA77 的固定 definition SHA 只覆盖 77 个 joint 名与 parent index，不覆盖官方 neutral/rest geometry。sidecar 因此必须显式保留：

```json
{
  "definition_scope": "joint_names_and_parents",
  "rest_geometry_policy": "source_frame0_unverified"
}
```

这表示编译器从当前动作 frame 0 反推 rest offset，但不会把它认证成官方 T-pose。需要官方 rest geometry 的任务必须另建 profile 与 digest，不能沿用本 profile 的名称冒充。

## 2. 声明精确数组 profile

P7 v1 只接受 little-endian float32、C-order NPY v1/v2 和 canonical bool，不调用 `numpy.load`，也不支持 pickle/object array。ZIP 只接受根目录下的精确成员名、stored/deflated 压缩和无 comment、无加密、无路径别名的清单。

`core-v1` 的成员是：

```text
posed_joints.npy       [T,77,3]   <f4
global_rot_mats.npy    [T,77,3,3] <f4
local_rot_mats.npy     [T,77,3,3] <f4
foot_contacts.npy      [T,C]      |b1
root_positions.npy     [T,3]      <f4
```

`complete-v1` 还必须恰好包含：

```text
smooth_root_pos.npy       [T,3] <f4
global_root_heading.npy   [T,2] <f4
```

`C` 只能是已声明的 4 点或 6 点接触布局。额外数组、缺失数组、重复/大小写冲突成员、非有限 float、非 0/1 bool、Fortran order、Zip64 或超过资源上限都会 fail closed。资源上限是原始 NPZ 128 MiB、总解压 128 MiB、单 NPY 64 MiB、单 NPY header 10,000 bytes。

完整 profile 会保存 `smooth_root_pos` 和 `global_root_heading` 原始证据，并检查范围与 heading 单位长度；P7 v1 的 root 轨道仍明确来自 `root_positions`，contact 仍只生成 annotation marker。

## 3. 明确投影与角色映射

复制映射示例后至少修改：

- `map_id`：任何投影、比例、contact 或角色映射变化都应使用新 ID；
- `clip.clip_id` 与 `clip.loop`；
- `basis`：三个屏幕/深度轴必须是互不重复的有符号 X/Y/Z；
- `root.reference_length_meters`：用于把 root 位移规范化，不能照抄合成示例；
- `bones`：只保留已经确认的 SOMA77 joint/aim 与 canonical role；
- `contact`：其 4/6 列顺序必须与 sidecar 完全一致。

正面示例采用：

```text
screen X = Kimodo +X
screen Y = Kimodo -Y
depth    = Kimodo +Z
```

canonical role 与 SOMA joint/aim 家族是固定映射，不能把整个 Left/Right branch 对调后仍保留原 role。需要镜像时必须在未来的显式 side-remap policy 中建模；P7 v1 不做隐式镜像。

一致性门以 `local_rot_mats + root_positions` 为重建真值，并用 `global_rot_mats` 与 `posed_joints` 逐帧交叉验证。SO(3)、global matrix 与 position 容差均固定为 `5e-4`，heading norm 容差为 `5e-3`；这些参数、compiler 1.1.0 和算法 profile 都写入 run manifest。

投影使用显式有符号正交 basis、segment `atan2`、最近 mapped parent 抵消、frame-0 setup baseline、有理 FPS 的 half-up 微秒 tick 和五位小数量化。它不会直接删除矩阵的 Z 分量，也不会把目标二维 rig 的骨长写进 MotionIR。

## 4. 编译并发布五文件 bundle

```powershell
python -m autospine_workbench compile-kimodo-motion `
  .\inputs\kimodo-wave.npz `
  .\inputs\kimodo-wave.source.json `
  .\inputs\kimodo-wave.map.json `
  --state-root .\workspace
```

成功响应会返回以下完整身份；保存 `clip_sha256` 与 `bundle_sha256`，不要用 `latest` 或目录扫描替代它们：

- `clip_id`、`source_id`、`map_id`；
- `raw_npz_sha256`、`raw_npz_byte_length`；
- `source_sha256`、`map_sha256`、`array_inventory_sha256`；
- `motion_ir_sha256`、`clip_sha256`、`run_sha256`、`bundle_sha256`；
- `source_kind` 与 `reused`。

固定 bundle 清单恰好是：

```text
workspace/motions/<clip-sha256>/<bundle-sha256>/
├── source.npz
├── sidecar.json
├── map.json
├── motion.json
└── run-manifest.json
```

其中 `source.npz` 保留原始字节；另外四份 JSON 采用 canonical 编码。重复发布同一输入会复用同一地址，改动任一输入字节、解释、映射、编译器版本或容差配置都会改变地址或明确失败。

## 5. 从精确地址只读复验

```powershell
python -m autospine_workbench verify-kimodo-motion `
  --clip-sha256 <motion-ir-sha256> `
  --bundle-sha256 <kimodo-motion-bundle-sha256> `
  --state-root .\workspace
```

复验会严格读取固定五文件清单，从 `source.npz`、`sidecar.json` 和 `map.json` 重新解码、检查矩阵/位置证据、重编译 MotionIR，并要求 canonical 字节和全部哈希交叉绑定。它不写 state tree，也拒绝把内建或 BVH bundle 当成 Kimodo bundle。

## 6. 运行合成门禁

```powershell
python -m unittest `
  tests.test_kimodo_npz_contracts `
  tests.test_kimodo_npz_reader `
  tests.test_kimodo_npz_compiler `
  tests.test_motion_bundle_kimodo `
  tests.test_motion_kimodo_commands `
  tests.test_p7_kimodo_npz_pipeline -v
```

正式 pipeline gate 会检查 root、代表性左右肢体旋转和双脚 contact，并要求同一个 motion source 在三个不同 setup rig 上产生三个不同的 P5/P6 地址。命令路径对一次编译只执行三次完整 FK：首次生成、发布合同重建、最终安全读回；持久化层不再为同一已验证合同重复做多次语义重建。

## 7. 继续 P5 重定向和 P6 导出

把上一步的两个 motion 地址传给既有命令：

```powershell
python -m autospine_workbench compile-motion-retarget <project-id> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --p4-profile-sha256 <p4-profile-sha256> `
  --p4-bundle-sha256 <p4-bundle-sha256> `
  --motion-clip-sha256 <motion-ir-sha256> `
  --motion-bundle-sha256 <kimodo-motion-bundle-sha256> `
  --state-root .\workspace
```

P5 通过后再按 [Spine 4.2 导出指南](how-to-export-spine42.md) 编译 P6。详细的 P5 地址合同见 [编译、重定向并复验 P5 动画](how-to-compile-motion.md)。

## 故障排查

- `raw NPZ identity differs`：sidecar 的 SHA/长度不是当前原始字节；不要就地修改内容寻址 bundle。
- `member inventory is incomplete or unexpected`：核对 core/complete profile 与 4/6 contact 布局；不要保留额外数组。
- `local rotation hierarchy differs` 或 `posed joint evidence`：local/global/posed/root 不属于同一动作快照，回到导出端修复。
- `bone role differs from the pinned SOMA77 mapping`：map 的 role、character side 与 joint/aim 家族不一致；不要通过改 validator 绕过。
- 精确地址不存在：从成功响应复制两个小写 SHA，并核对 `--state-root`；verifier 不会寻找“最接近”的 bundle。

## 当前验收边界

正式 P7 的自动测试使用确定性的合成 SOMA77 NPZ，覆盖 4/6 contact、矩阵与位置矛盾、恶意 ZIP/NPY、可复现发布、三套不同 rig 的 P5 重定向以及 P6 adapter/bundle reader。它证明合同与几何链路可重复，不证明官方 exporter 或真实 Kimodo checkpoint 的动作质量。

在把真实动作列为已验收之前，还需要加入固定上游 revision 产生的 official-exporter NPZ fixture，并提供带 recorded provenance 的真实 checkpoint NPZ、干净 state 重编译、选定帧 3D/2D 人工对照和固定 Spine Player 截图。当前也尚未以 Windows/Linux 双平台 golden 证明临界 `atan2`/量化输入的逐字节一致性；若用于跨平台发布，应先补该门禁。

P7 v1 尚未执行 foot lock、heading 驱动转身、透视缩短 scale、动态 draw order、附件切换或关键帧压缩；contact 当前只是可保留的半开区间证据。`smooth_root_pos` 只做有界有限数检查，`global_root_heading` 只做单位方向检查，两者都不会改写 MotionIR root/rotation。
