# 编译 Kimodo SOMA77 BVH

本指南面向已经完成 P3 mesh 与 P4 IK 复核的开发者。目标是把一份 Kimodo SOMA77 BVH 原样编译为内容寻址的 MotionIR，经目标 rig 重定向后交给 Spine 4.2 adapter。

这是 P7a 兼容性流程，不是正式 Kimodo NPZ adapter。它验证 BVH 形状、局部旋转、root 位移和既有 P5/P6 边界；不会保留 NPZ 中的脚接触、平滑 root 或 heading。

## 1. 在独立环境生成 BVH

Kimodo 的模型、CUDA 与 Hugging Face 依赖应安装在独立环境中，不要加入 workbench 服务进程。以下 PowerShell 示例固定模型、随机种子、单样本和标准 T-pose：

```powershell
kimodo_gen "A person waves while standing in place." `
  --model Kimodo-SOMA-RP-v1.1 `
  --duration 5.0 `
  --num_samples 1 `
  --seed 42 `
  --output .\kimodo-wave `
  --bvh `
  --bvh_standard_tpose
```

Kimodo 会保留默认 NPZ，并额外写出 `kimodo-wave.bvh`。模型、prompt、constraints、seed、Kimodo commit 和 checkpoint 许可证应由调用方另行记录；当前 BVH bundle 只绑定 BVH 原始字节、显式 map 和 AutoSpine 编译器身份。

官方 CLI 参数与输出规则见 [Kimodo CLI](https://github.com/nv-tlabs/kimodo/blob/main/docs/source/user_guide/cli.md)。

## 2. 准备显式 SOMA77 map

复制已审核的正面投影模板，不要让程序根据 joint 名自动猜测：

```powershell
Copy-Item `
  .\tests\fixtures\kimodo_soma77_front.map.json `
  .\inputs\kimodo-wave.autospine-bvh-map.json
```

至少逐项确认：

- `map_id` 与 `clip.clip_id` 对当前动作唯一；
- `loop` 与首尾姿势是否真的闭合；
- `screen_x=+X`、`screen_y=-Y`、`depth=+Z` 是否匹配当前正交视图；
- `reference_length_source_units` 是否来自当前 BVH 的实际厘米尺度；
- `root.joint_name` 保持为 `Hips`；
- 15 个直接角色仍对应当前 SOMA77 hierarchy；左右 hip pseudo-bone 被折叠进最近的已映射 canonical ancestor；
- contact 当前保持关闭。

模板中的 `reference_length_source_units=100` 只属于合成测试夹具，不能当成所有 Kimodo 角色的固定人体尺度。修改 basis、参考长度、角色或 contact 参数时，也要修改 `map_id`，避免把不同语义伪装成同一个 profile。

## 3. 理解双根准入条件

Kimodo 官方 BVH 使用一个特殊但固定的层级：

```text
ROOT Root       6DOF，零 offset，全帧零通道
└─ JOINT Hips   6DOF，保存真实 root 位移与旋转
   └─ SOMA77    其余 76 joint 仅有三个旋转通道
```

AutoSpine compiler 1.1.0 接受旧的单 ROOT profile，也接受上述 `zero-wrapper-logical-root-v1`。双根输入必须同时满足：

- `Root` 只有一个直接子节点；
- `Root` offset 为零且没有 End Site；
- `Root` 的六个通道在每一帧都精确为零；
- map 的逻辑 root 与 `humanoid.root` 都显式绑定 `Hips`；
- 只有 `Root` 与 `Hips` 可以拥有 position channels；
- 至少有两帧，且全部资源限制、有限数和通道计数通过。

任一条件不符都会在 map/FK 编译前失败。compiler 不会把任意双根 BVH 猜成 Kimodo，也不会静默丢弃 wrapper 或 `Hips` 位移。官方 exporter 结构可对照 [Kimodo BVH 实现](https://github.com/nv-tlabs/kimodo/blob/main/kimodo/exports/bvh.py) 与 [SOMA77 hierarchy](https://github.com/nv-tlabs/kimodo/blob/main/kimodo/skeleton/definitions.py)。

## 4. 编译并复验 MotionIR

```powershell
python -m autospine_workbench compile-bvh-motion `
  .\kimodo-wave.bvh `
  .\inputs\kimodo-wave.autospine-bvh-map.json `
  --state-root .\workspace
```

保存响应中的：

- `raw_bvh_sha256`
- `bvh_map_sha256`
- `motion_ir_sha256` / `clip_sha256`
- `run_sha256`
- `bundle_sha256`

随后按精确地址只读复验：

```powershell
python -m autospine_workbench verify-bvh-motion `
  --clip-sha256 <motion-ir-sha256> `
  --bundle-sha256 <motion-bundle-sha256> `
  --state-root .\workspace
```

bundle 保留原始 `source.bvh`，不会先归一化或重写 Kimodo 文件。compiler 1.1.0 的 FK profile 已变为 `declared-channel-postmultiply-3d-affine-logical-root-v2`；旧 compiler 1.0.0 BVH run 会 fail loud，不能被当前 verifier 静默复用。

## 5. 重定向并导出 Spine 4.2

使用上一步的 MotionIR 双 SHA，按 [编译 MotionIR 与通用动画重定向](how-to-compile-motion.md#5-编译并复验-retarget-bundle) 生成 P5 MotionInstance。再按 [导出 P6 Spine 4.2 资产](how-to-export-spine42.md) 传入精确 P3 与 P5 地址。

当前 P7a 门禁证明同一个 Kimodo-shaped MotionIR 可以在三套不同 setup rig 上产生三个不同 MotionInstance，并生成、发布和严格读取三个 Spine 4.2 bundle。它尚未把真实 Kimodo clip 加入官方 Spine Player 截图 golden；P6 的官方 runtime 回归仍固定于既有 setup、idle 与 wave 样本。

## 6. 运行兼容性门禁

```powershell
python -m unittest `
  tests.test_bvh_motion_root `
  tests.test_kimodo_soma77_fixture `
  tests.test_p7a_kimodo_soma77_pipeline `
  -v
```

测试夹具是确定性、合成的 Kimodo-shaped SOMA77 BVH，不是 Kimodo checkpoint 生成结果。它固定官方 joint 名、77-joint hierarchy、双 6DOF root、30 Hz 和厘米尺度，并加入 `Hips` 旋转回归，证明缺失 hip pseudo-bone 时会折叠到最近已映射 canonical ancestor，不会把 root 旋转在目标 thigh 上重复计算。

## 已知边界

- MotionIR 以第 0 帧作为 setup-local delta 基线；它不会把任意动作首帧改造成 T-pose。
- 固定正面正交投影会舍弃 depth；侧身、转身和大幅出平面动作需要独立 map/profile 与视觉门禁。
- BVH 不携带 Kimodo NPZ 的 `foot_contacts`、`smooth_root_pos` 或 `global_root_heading`。
- contact template 当前显式关闭；P7a 不提供 foot lock 或滑步修正。
- 当前 Spine 适配只覆盖既有 MotionInstance rotation/root translation 合同，不生成运行时 IK、deform、动态 draw order 或物理。
- 正式 P7 NPZ adapter 必须另建 schema、sidecar、单位/坐标合同和原始数组 provenance，不能把本流程冒充 NPZ 无损导入。
