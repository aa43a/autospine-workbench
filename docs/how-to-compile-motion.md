# 编译、重定向并复验 P5 动画

本指南面向已经取得精确 P3 mesh bundle 与 P4 IK bundle 地址的开发者。目标是把内建动作或显式映射的 BVH 编译为可复用 MotionIR，再为指定 rig 生成、发布并复验一个 P5 motion-retarget bundle。

本文只处理 P5 的版本中立动画合同。P6 的 Spine 目标版本适配与导出不在本文范围内。

## 前提

在仓库根目录运行命令，并让本地源码优先进入模块搜索路径：

```powershell
Set-Location E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

准备以下精确输入：

- 一个真实、非 symlink/junction 的 `--state-root`；
- 需要重定向时，已经分别通过 `verify-mesh-bundle` 与 `verify-ik-bundle` 的 P3/P4 双 SHA 地址；
- 使用 BVH 时，原始 `.bvh` 文件和一份人工确认的显式 map JSON；
- 足够的空间保存不可变 bundle；编译不会覆盖已有内容地址。

先阅读 [P3/P4 编译边界](how-to-compile-ik-targets.md)；不要使用 `latest`、目录扫描结果、大小写变体或手工拼接的 SHA 代替命令输出。

## 1. 识别 P5 合同与地址

P5 把“可复用动作”和“某个 rig 上的结果”分开：

| 合同 | 用途 | 是否绑定具体 rig |
| --- | --- | --- |
| [MotionIR v1](../schemas/motion-ir-v1.schema.json) | 以 humanoid role、归一化 root/IK 空间和 setup-local 旋转表示动作 | 否 |
| [motion target profile v1](../schemas/motion-target-profile-v1.schema.json) | 从精确 P3/P4 输入固化骨角色、参考长度、IK 与 mesh 证据 | 是 |
| [MotionInstance v1](../schemas/motion-instance-v1.schema.json) | 把 MotionIR 烘焙为目标 rig 的 setup-local 像素平移和角度轨道 | 是 |
| [retarget run v1](../schemas/retarget-run-v1.schema.json) | 绑定编译器配置、输入 SHA、run identity 与 instance SHA | 是 |
| [retarget report v1](../schemas/motion-retarget-report-v1.schema.json) | 记录有限数、loop closure、IK 端点与 contact 保留证据 | 是 |
| [mesh regression v1](../schemas/motion-mesh-regression-v1.schema.json) | 在采样 tick 上检查翻三角、退化、拉伸与裂缝 | 是 |

Motion bundle 使用固定内容地址：

```text
workspace/motions/<motion-ir-sha256>/<motion-bundle-sha256>/
```

内建 bundle 只包含 `motion.json` 与 `run-manifest.json`。BVH bundle 的固定清单是：

```text
source.bvh
map.json
motion.json
run-manifest.json
```

重定向结果使用另一个固定地址：

```text
workspace/builds/<project-id>/motion-instances/<instance-sha256>/<bundle-sha256>/
```

其清单固定为 `target-profile.json`、`instance.json`、`run-manifest.json`、`retarget-report.json` 和 `mesh-regression.json`。任何缺失、额外文件、非 canonical JSON、路径别名或来源不一致都会使只读复验失败。

## 2. 发布内建 idle 与 wave.left

内建动作的有效 ID 只有 `idle` 与 `wave.left`：

```powershell
python -m autospine_workbench compile-builtin-motion idle `
  --state-root .\workspace

python -m autospine_workbench compile-builtin-motion wave.left `
  --state-root .\workspace
```

当前合同的已固定地址如下；三列依次为 MotionIR、run manifest 与 bundle SHA：

| clip | `clip_sha256` | `run_sha256` | `bundle_sha256` |
| --- | --- | --- | --- |
| `idle` | `e19e0885420378c51e0a6c9cd775b880bb3708bf793ea4c87d53dce44848f85d` | `685594dd49cd5ff9bb91106babccf2bddb55d2acbed424c82f1ebdba9ef4342a` | `63c4accf690c361be8ca6146071ef95621897874d436586081c0f3fba08199ec` |
| `wave.left` | `d054364dd9d6118814ba7623e5a0716102bfa8610d3d78dbcdabbe396a82c9d1` | `be0a28ab45077e3f69ad565c6f13230d1d61c8205b86eeb9a2327fe295fe9e05` | `c9099e7302686df1936f037796194c6055e02a3bbcccc98e151c56aca63c94d1` |

只读复验内建 bundle：

```powershell
python -m autospine_workbench verify-motion-bundle `
  --clip-sha256 e19e0885420378c51e0a6c9cd775b880bb3708bf793ea4c87d53dce44848f85d `
  --bundle-sha256 63c4accf690c361be8ca6146071ef95621897874d436586081c0f3fba08199ec `
  --state-root .\workspace
```

`verify-motion-bundle` 是内建动作的既有入口。不要用它复验四文件 BVH bundle；BVH 必须使用第 4 节的 `verify-bvh-motion`。

## 3. 为 BVH 编写显式 map

BVH 编译器不会根据名称、屏幕方向或左右侧做隐式猜测。map 必须符合 [BVH map v1](../schemas/bvh-map-v1.schema.json)，并明确给出：

- 唯一 `map_id`、输出 `clip_id` 与 `loop`；
- 三个互不重复的有符号源轴，以及固定 Euler 约定；
- BVH root、源单位参考长度与 root translation policy；
- 按 canonical humanoid role 顺序排列的 source joint、aim 和 rotation policy；
- 是否检测脚接触；启用时还要给出脚 joint、地面、阈值与帧合并参数。

下面是结构示例。joint 名、轴、参考长度和阈值必须按当前 BVH 证据修改：

```json
{
  "format": "autospine-bvh-map",
  "format_version": 1,
  "map_id": "mixamo.walk.front-v1",
  "clip": {"clip_id": "walk.front", "loop": true},
  "basis": {
    "screen_x": "+X",
    "screen_y": "-Y",
    "depth": "+Z",
    "rotation_convention": "bvh_declared_channel_postmultiply"
  },
  "root": {
    "joint_name": "Hips",
    "reference_length_source_units": 100.0,
    "translation_policy": "projected_frame0_delta_normalized_reference_length"
  },
  "bones": [
    {
      "role": "humanoid.root",
      "joint_name": "Hips",
      "aim": {"kind": "joint", "joint_name": "Spine"},
      "rotation_policy": "projected_setup_local_delta"
    }
  ],
  "contact": {
    "enabled": false,
    "mode": "annotation_only",
    "interval": "half_open"
  }
}
```

要得到四肢轨道，继续把实际 BVH 关节映射到对应的 upper/lower limb role；aim 必须是该 source joint 的后代。启用 contact 后，检测结果仍只是半开区间 `[start_tick, end_tick)` 的 `annotation_only` marker。

`annotation_only` 不会锁脚、修改 root motion、重新求解 IK 或消除 foot sliding。需要这些行为时，应在后续消费端显式实现并建立独立合同。

## 4. 编译并复验 BVH motion bundle

编译命令只读取显式给出的两个输入文件，不搜索相邻 map：

```powershell
python -m autospine_workbench compile-bvh-motion `
  .\inputs\walk.bvh `
  .\inputs\walk.autospine-bvh-map.json `
  --state-root .\workspace
```

保存响应中的 `clip_sha256`、`run_sha256`、`bundle_sha256`、`raw_bvh_sha256` 与 `bvh_map_sha256`。bundle 地址同时绑定原始 BVH 字节、canonical map、编译所得 MotionIR、编译器配置和 run manifest；只改空白的原始 BVH 也会改变 bundle 地址。

随后只读复验精确四文件地址：

```powershell
python -m autospine_workbench verify-bvh-motion `
  --clip-sha256 <bvh-motion-ir-sha256> `
  --bundle-sha256 <bvh-motion-bundle-sha256> `
  --state-root .\workspace
```

复验会从已保存的 `source.bvh` 与 `map.json` 重编译 MotionIR，并要求 canonical 字节、全部来源 SHA 和请求地址一致。它不修改 state tree，也不接受内建两文件 bundle。

## 5. 编译并复验 retarget bundle

把一个精确 MotionIR bundle 与同一项目中互相配对的 P3/P4 地址一起传入：

```powershell
python -m autospine_workbench compile-motion-retarget <project-id> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --p4-profile-sha256 <p4-profile-sha256> `
  --p4-bundle-sha256 <p4-bundle-sha256> `
  --motion-clip-sha256 <motion-ir-sha256> `
  --motion-bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace
```

命令必须先严格重读三个上游 bundle，再生成 target profile、MotionInstance、retarget run、运动学报告和 mesh regression。只有两个报告均为 `passed`，五份 canonical 文档才会原子发布并从新地址重读。

记录响应中的 `target_profile_sha256`、`instance_sha256`、`run_sha256`、`report_sha256`、`mesh_regression_sha256` 和 `bundle_sha256`。然后运行：

```powershell
python -m autospine_workbench verify-motion-retarget <project-id> `
  --instance-sha256 <motion-instance-sha256> `
  --bundle-sha256 <retarget-bundle-sha256> `
  --state-root .\workspace
```

该命令只读取指定地址，并从其完整 P3、P4 与 MotionIR 来源链重建全部五份文档；它不会寻找其他 clip、rig 或 bundle 来替代失败输入。

## 6. 使用真实 A/B 输入地址

下面的地址来自已批准的 P3/P4 golden。它们是 P5 输入示例，不是预先声明的 P5 输出地址。

| 项目 | P3 rig | P3 bundle | P4 profile | P4 bundle |
| --- | --- | --- | --- | --- |
| `seethrough_output`（A） | `40f96ade2f38f93caa7610b40f02ed9b30b8782396cee0e80499724a0450e327` | `7754406b1f6834a6b5c8fedfcd4743bd294d8cc568d7ff6413673cada3d79a1d` | `9fdecdbc084ab51b54768c4bbca18fbe484ad153ed8b426d1bd2937e6526b9d0` | `9089fd1859286022288b2b79b63b461c1d60a4bdc9509f50cdd7a6834b3933c3` |
| `seethrough_output_5`（B） | `897761e75bdd7e1cd3018cdab0f793f2d3ba637d88e01ce907beb179cfe0cd77` | `21f4707eaf023d664ae8cea8b785fd8a5197187f846d6db10b9c3ef34d7c6576` | `ee522acfdf729b179b0bd7fb15d29303c724b63d3f467a6a0ba035704ea4242d` | `a98a42e614f73f0df9dd6751a2a5a042dd707d6f4acff7e3410a4d69c6bd419b` |

例如，把内建 `idle` 重定向到 A：

```powershell
python -m autospine_workbench compile-motion-retarget seethrough_output `
  --p3-rig-sha256 40f96ade2f38f93caa7610b40f02ed9b30b8782396cee0e80499724a0450e327 `
  --p3-bundle-sha256 7754406b1f6834a6b5c8fedfcd4743bd294d8cc568d7ff6413673cada3d79a1d `
  --p4-profile-sha256 9fdecdbc084ab51b54768c4bbca18fbe484ad153ed8b426d1bd2937e6526b9d0 `
  --p4-bundle-sha256 9089fd1859286022288b2b79b63b461c1d60a4bdc9509f50cdd7a6834b3933c3 `
  --motion-clip-sha256 e19e0885420378c51e0a6c9cd775b880bb3708bf793ea4c87d53dce44848f85d `
  --motion-bundle-sha256 63c4accf690c361be8ca6146071ef95621897874d436586081c0f3fba08199ec `
  --state-root .\workspace
```

对 B 或 `wave.left` 重复时，只替换表中四个目标 SHA，以及第 2 节中成对的 motion clip/bundle SHA。必须从命令响应取得新的 instance/bundle SHA；不要根据示例推测输出地址。

## 7. 执行复用与 mesh 门禁

同一个 MotionIR bundle 必须在至少三个不同 setup rig 上产生三个不同的 MotionInstance，同时保持相同 `motion_bundle_sha256`。运行合同门禁：

```powershell
python -m unittest tests.test_motion_three_rig_gate -v
```

这项测试覆盖 `idle` 与 `wave.left` 的三个不同 setup。它验证有限姿势、角色映射、来源复用和 marker 投影；不能用“同一 rig 改项目名”充当第三个 rig。接触保留结论来自每个 retarget bundle 中重新计算的 `retarget-report.json`。

每个实际项目仍要以 bundle 中的 `mesh-regression.json` 为准。A 的 P3 mesh 清单包含两个 converted target；B 的批准 P3 状态是 `reviewed-noop`。`reviewed-noop` 表示没有 P3 mesh target 可采样，不等于跳过 P3/P4 来源复验。存在 mesh target 时，任何采样 tick 的翻三角、退化、超阈值拉伸或裂缝都会拒绝发布。

## 故障排查

### `Unsupported built-in MotionIR clip`

使用精确 ID `idle` 或 `wave.left`；`wave`、`wave.right` 和大小写变体均无效。

### BVH map 与源层级不一致

逐项核对 joint 名的大小写、root、aim 后代关系、canonical role 顺序和三个有符号轴。不要通过放宽 validator 或按屏幕 x 坐标猜左右来绕过错误。

### loop 或 IK 报告失败

若 map 声明 `loop=true`，首尾姿势必须满足 loop closure。若 IK 目标不可达，MotionIR 的策略是 `reject`；应修正 map、动作范围或上游 rig，不要把 NaN、clamp 或静默丢轨当作成功。

### mesh regression 为 `rejected`

查看 `mesh-regression.json` 的首个失败 tick 与 worst metrics，再回到 P3 调整拓扑、权重或安全动作范围。P5 不会覆盖 P3 的视觉安全结论。

### 精确地址不存在或被判定为 alias

确认 `--state-root`、项目 ID 和两个 SHA 完全来自同一次成功响应。路径中不能出现 `latest`、symlink、junction、错误大小写或额外文件。若 bundle 字节已损坏，从可信上游在干净 state root 重新编译；不要就地编辑内容寻址目录。

### 用错复验命令

两文件内建 bundle 使用 `verify-motion-bundle`；四文件 BVH bundle 使用 `verify-bvh-motion`；五文件、目标相关的结果使用 `verify-motion-retarget`。

## 非目标

本流程不会导出 Spine JSON/atlas/PNG，不选择 Spine runtime 版本，不生成实时 tracking 映射，也不实现运行时 foot lock、物理或编辑器约束。通过 P5 只说明同一版本中立 clip 能可靠重定向并留下可复验的运动学与 mesh 证据；Spine adapter 属于 P6。
