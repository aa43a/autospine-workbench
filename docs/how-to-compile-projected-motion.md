# 编译并复验 P8 投影证据

本指南把一个精确的 P7 Kimodo NPZ motion bundle 与显式静态正交相机组合为 `ProjectedMotionIR v1`。输出保留二维段向量、3D/2D 长度、投影缩短、深度和可观测性，同时继续让旧 P5/P6 使用逐字节等价的 `MotionIR v1`。

P8 是证据与候选阶段，不是自动遮挡或 scale 动画阶段。它不会修改 P7、P5、P6 bundle，也不会向 Spine 写入 scale、draw order 或 attachment timeline。

## 前提

在仓库根目录运行命令，并让本地源码优先进入模块搜索路径：

```powershell
Set-Location E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

你需要：

- 一个已经通过 `verify-kimodo-motion` 的 P7 `motion_ir_sha256`；
- 与之配对的 P7 `bundle_sha256`；
- 一份符合 [CameraModel v1](../schemas/camera-model-v1.schema.json) 的独立 `camera.json`。

P8 不接受 BVH 或内建 MotionIR，也不从 P7 目录旁边猜测相机。

## 1. 声明相机

正面静态正交相机示例：

```json
{
  "format": "autospine-camera-model",
  "format_version": 1,
  "camera_id": "kimodo-front-orthographic-v1",
  "projection": "static_orthographic",
  "basis": {
    "screen_x": "+X",
    "screen_y": "-Y",
    "depth": "+Z"
  },
  "depth_positive": "away_from_camera",
  "origin": "source_root_frame0",
  "normalization": "map_reference_length",
  "reference_length_meters": 1.0
}
```

`basis` 的三个轴必须正交，并与 P7 map 的 `screen_x`、`screen_y`、`depth` 完全一致；`reference_length_meters` 也必须与 P7 map 一致。否则命令会失败，而不是重新解释旧动作。

`depth_positive` 说明相机 depth 正方向是远离还是朝向相机。它进入相机内容地址并供后续策略解释符号；P8 本身只保存证据，不根据正负值改变 draw order。

当前相机是静态正交投影，没有焦距、透视除法或逐帧相机轨道。因此这里的 foreshortening 是三维骨段相对屏幕平面的投影缩短，不是近大远小。

## 2. 编译三文件 bundle

```powershell
python -m autospine_workbench compile-projected-motion `
  .\inputs\kimodo-front.camera.json `
  --motion-clip-sha256 <p7-motion-ir-sha256> `
  --motion-bundle-sha256 <p7-motion-bundle-sha256> `
  --state-root .\workspace
```

成功响应包含：

- `projected_motion_sha256` 与 `bundle_sha256`；
- `camera_sha256`、`run_sha256` 与 `legacy_motion_sha256`；
- 三个 P7 上游 SHA；
- collapsed sample 数和最小/最大 foreshortening ratio；
- `reused`，表示同一不可变地址是否已存在。

固定地址与清单为：

```text
workspace/projected-motions/<projected-motion-sha256>/<bundle-sha256>/
├── camera.json
├── projected-motion.json
└── run-manifest.json
```

三个文件均采用 canonical JSON。bundle 地址对 domain、文件名、文件长度和文件字节做显式 framing；额外文件、大小写别名、链接、截断或竞态修改都会失败。

`projected-motion.json` 的每条 segment sample 包含：

- `projected_vector_normalized`：屏幕二维骨段向量；
- `source_length_normalized` 与 `projected_length_normalized`：L3 与 L2；
- `foreshortening_ratio = L2 / L3`；
- `depth_cosine`：骨段沿相机 depth 的有符号分量除以 L3；
- 起点、终点与中点相对 root 的 depth；
- 展开的屏幕 world angle 与 `observable`/`collapsed` 状态。

几何验证要求 `ratio² + depth_cosine² ≈ 1`。v1 的 bundle 和 legacy bridge 会拒绝 collapsed sample，不会沿用上一帧角度或制造零长度骨。

## 3. 从精确地址只读复验

```powershell
python -m autospine_workbench verify-projected-motion `
  --projected-motion-sha256 <projected-motion-sha256> `
  --bundle-sha256 <projected-bundle-sha256> `
  --state-root .\workspace
```

验证器会：

1. 只读取指定目录的固定三个文件；
2. 沿文档中的精确 P7 双 SHA 读取原始五文件 bundle；
3. 重新解码原始 NPZ，重跑矩阵 FK 与 P8 投影；
4. 重建 legacy MotionIR 和 compile run；
5. 对 canonical 字节、全部 SHA 与 bundle 地址逐项比较。

命令不解析 `latest`、不扫描替代目录，也不写 state tree。

## 4. 生成目标 Rig 的候选长度探针

先准备一个已经通过 `verify-motion-retarget` 的 P5 bundle。随后用两个精确 P8 地址和两个精确 P5 地址运行：

```powershell
python -m autospine_workbench probe-projected-scale seethrough_output `
  --projected-motion-sha256 <projected-motion-sha256> `
  --projected-bundle-sha256 <projected-bundle-sha256> `
  --motion-instance-sha256 <p5-motion-instance-sha256> `
  --motion-retarget-bundle-sha256 <p5-retarget-bundle-sha256> `
  --state-root .\workspace
```

命令严格重建 P8 和 P5 bundle，然后返回完整的 `autospine-projected-scale-probes/v1` 报告及其 SHA。每根目标骨使用：

```text
scale_x_candidate(t) = source_ratio(t) / source_ratio(frame 0)
candidate_length_px(t) = target_setup_length_px × scale_x_candidate(t)
```

报告同时绑定 P8 projected/camera/P7 地址、P5 target profile SHA 与 P3 rig/bundle SHA。同一份 P8 证据可用于不同骨长的目标 rig；scale 序列保持一致，候选像素长度随目标 setup 改变。

该命令只输出候选报告，不发布 MotionInstance v2，也不修改目标 profile 的 `positive-unit-only` 合同。`runtime_timeline_emitted=false` 和 `depth_consumption=none` 是固定语义。collapsed sample 会让整份报告失败，不能自动补帧。

## 5. 运行阶段门禁

```powershell
python -m unittest `
  tests.test_camera_model_validation `
  tests.test_projected_motion_validation `
  tests.test_kimodo_camera_projection `
  tests.test_projected_motion_legacy `
  tests.test_projected_motion_compile_run `
  tests.test_projected_motion_bundle_store `
  tests.test_projected_motion_commands `
  tests.test_projection_stage_cli `
  tests.test_projected_scale_probe `
  tests.test_p8_projected_motion_pipeline -v
```

正式 P8 gate 要求 legacy bridge 精确还原 P7 MotionIR，并让同一投影证据和候选算法通过三套不同 target rig。P5 MotionInstance 与 P6 Spine 4.2 输出仍只能包含既有 rotation/translation timeline。

## 故障排查

- `Camera basis differs`：camera 的三个有符号轴与 P7 map 不同；修正显式相机，不要改旧 bundle。
- `reference length differs`：camera 与 P7 map 的归一化尺度不同；应回到相机声明核对单位。
- `legacy compilation rejects collapsed`：至少一根映射骨在某帧投影为近零长度；v1 不允许猜测角度。
- `exact ... does not exist`：核对完整小写 SHA 和 `--state-root`；reader 不会寻找最接近的地址。
- `identities differ from canonical content`：内存对象、磁盘文件或 run provenance 被修改；从可信的 P7 地址重新编译。
- scale probe `target binding differs`：P5 target profile 与报告中的 P3/P5 身份不一致；不要把另一角色的候选长度混用。

## 当前边界与下一阶段

P8 已证明相机、投影证据、P7 legacy 等价性和三 rig 候选复用可重复；合成 fixture 仍不证明真实 Kimodo checkpoint 的动作质量。

P9 才会定义需要人工批准的消费策略：contact 驱动的 foot lock、heading/root 处理、带滞回的 depth ordering、最小 draw-order 事件，以及可选的 reviewed scale timeline。P9 必须继续把原始证据、算法候选和人工决定分开；不能直接把 P8 depth 排序或把所有骨的 foreshortening 无条件写进 Spine。
