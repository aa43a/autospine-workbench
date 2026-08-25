# 导出、复验并运行 P6 Spine 4.2 资产

本指南面向已经取得精确 P3 mesh bundle 地址，以及可选 P5 MotionInstance bundle 地址的开发者。完成后会得到一个可复验的 Spine 4.2 五文件 bundle，并可用固定版本的官方 Spine Player 在本地浏览器中执行 runtime 加载与截图回归。

本文只处理固定的最小导出 profile：Spine JSON `4.2` 与 `@esotericsoftware/spine-player@4.2.119`。它不生成编辑器工程，不自动批准截图，也不授予 Spine Runtimes 的使用或再分发许可。

## 前提

在仓库根目录运行命令，并让本地源码优先进入模块搜索路径：

```powershell
Set-Location E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

准备以下输入：

- 一个已经通过 `verify-mesh-bundle` 的 P3 rig/bundle 双 SHA 地址；
- 需要动画时，一个已经通过 `verify-motion-retarget`、且来源正是上述 P3 bundle 的 P5 MotionInstance/bundle 双 SHA 地址；
- 一个真实、非 symlink/junction 的 `--state-root`；
- 运行浏览器门禁时，获得授权并由操作者单独安装的官方 Spine Player `4.2.119`。

命令不解析 `latest`，也不会用同项目中的其他 rig、动作或 bundle 替换失败输入。先完成 [P3/P4 编译](how-to-compile-ik-targets.md) 和 [P5 动画编译](how-to-compile-motion.md)，再进入本流程。

## 1. 导出 setup-only bundle

只给出 P3 地址即可导出 setup pose：

```powershell
python -m autospine_workbench compile-spine42 <project-id> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace
```

成功响应的 `mode` 是 `setup-only`，`clip_id` 是 `null`。记录响应中的 `skeleton_json_sha256` 与 `bundle_sha256`；它们组成后续复验和 runtime 加载所需的精确地址。

## 2. 为一个 MotionInstance 导出动画 bundle

动画导出在同一命令中增加一对 P5 地址：

```powershell
python -m autospine_workbench compile-spine42 <project-id> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --motion-instance-sha256 <motion-instance-sha256> `
  --motion-bundle-sha256 <motion-retarget-bundle-sha256> `
  --state-root .\workspace
```

`--motion-instance-sha256` 与 `--motion-bundle-sha256` 必须同时提供。每次编译只接收一个 MotionInstance，因此 `idle` 与 `wave.left` 分别发布到不同 bundle；这避免在一个导出中隐式聚合来自不同 P5 地址的动画。

编译器会严格重读 P3 原始 RGBA 图像和 P5 来源链，生成 atlas 与 Spine JSON，再发布并从新地址读回。若 P5 不是从请求中的 P3 双 SHA 生成，命令会失败，不会发布部分结果。

成功响应还包含 `source_addresses`、`output_sha256s`、各文件/报告 SHA、`summary` 与 `reused`。相同输入与编译器合同会得到相同地址；`reused=true` 表示精确 bundle 已存在且通过复验，不表示复用了一个相似或较新的输出。

## 3. 复验精确导出地址

对 setup-only 和动画 bundle 使用同一个只读入口：

```powershell
python -m autospine_workbench verify-spine42 <project-id> `
  --skeleton-json-sha256 <skeleton-json-sha256> `
  --bundle-sha256 <spine42-bundle-sha256> `
  --state-root .\workspace
```

验证器从 `run-manifest.json` 取得精确 P3/P5 来源，重新编译全部五个文件，并逐字节比较内容与请求地址。它还拒绝非 canonical JSON、错误 atlas/PNG 绑定、目录别名、缺失或额外文件、不匹配的版本与未支持特性。

两个命令成功时退出码为 `0`，并输出 `ok=true`。合同、地址或上游重建失败时输出 `ok=false` 并退出 `2`；参数缺失同样退出 `2`。自动化脚本应检查退出码和 `ok`，不要只检查目录是否存在。

## 4. 定位五文件 bundle

导出地址固定为：

```text
workspace/builds/<project-id>/spine42/<skeleton-json-sha256>/<bundle-sha256>/
├── skeleton.json
├── skeleton.atlas
├── skeleton.png
├── run-manifest.json
└── export-report.json
```

文件职责如下：

| 文件 | 用途 |
| --- | --- |
| `skeleton.json` | Spine 4.2 setup、region/mesh、draw order，以及可选的单个 MotionInstance 时间线 |
| `skeleton.atlas` | 确定性的单页、无旋转、无裁切 atlas 描述 |
| `skeleton.png` | 与 atlas 精确绑定的无损 RGBA 页面 |
| `run-manifest.json` | adapter profile、P3/P5 精确来源、源图 SHA 与 run identity |
| `export-report.json` | 跨文件、骨架、attachment、动画和导出摘要证据 |

不要就地编辑、增删或重命名这些文件。需要修改输入、adapter 或动画时，重新编译并取得新地址。

## 5. 准备固定版本的官方 runtime

官方 runtime 不进入 Git。仓库的 `workspace/runtime/` 已被忽略；也可以把包安装到仓库外的操作者自管目录。下面的离线命令要求 npm 缓存中已经有精确版本：

```powershell
npm install --offline --ignore-scripts --no-save --package-lock=false `
  --prefix workspace/runtime/spine-player-4.2.119 `
  @esotericsoftware/spine-player@4.2.119
```

传给 harness 的是包目录，而不是安装前缀：

```powershell
$runtimeRoot = Resolve-Path `
  .\workspace\runtime\spine-player-4.2.119\node_modules\@esotericsoftware\spine-player
```

Harness 会核对 package 名、`4.2.119` 版本、精确 `spine-webgl` 依赖、runtime 文件和 `LICENSE`。使用前仍须由操作者阅读官方许可证，并确认自己对运行与可能的再分发拥有所需授权。安装包或传入确认开关都不会替代这项审查。

## 6. 运行本地 runtime capture

先为 setup-only bundle 启动 loopback harness。`--export-dir` 必须指向第 4 节的精确五文件目录：

```powershell
python .\tools\run_spine42_runtime_regression.py `
  --export-dir <spine42-setup-bundle-directory> `
  --capture-dir .\workspace\runtime-captures\setup `
  --runtime-root $runtimeRoot `
  --clip setup `
  --port 0 `
  --acknowledge-spine-runtime-license
```

命令会打印形如 `http://127.0.0.1:<port>/case/setup` 的 URL。用固定 DPR 的本地浏览器打开它；页面会用官方 runtime 加载导出、应用精确姿势并回传 canvas PNG。等待：

```javascript
window.__AUTOSPINE_RUNTIME_RESULT__
```

变为 `status: "ready"`。若为 `status: "error"`，以其中的错误和 capture 目录内的 `*.actual.json` 为准，不要把页面可见当作门禁通过。

随后分别用包含对应 clip 的动画 bundle 运行固定时间点：

```powershell
python .\tools\run_spine42_runtime_regression.py `
  --export-dir <spine42-idle-bundle-directory> `
  --capture-dir .\workspace\runtime-captures\idle `
  --runtime-root $runtimeRoot `
  --clip idle `
  --time 1.0 `
  --port 0 `
  --acknowledge-spine-runtime-license

python .\tools\run_spine42_runtime_regression.py `
  --export-dir <spine42-wave-bundle-directory> `
  --capture-dir .\workspace\runtime-captures\wave-left `
  --runtime-root $runtimeRoot `
  --clip wave.left `
  --time 0.6 `
  --port 0 `
  --acknowledge-spine-runtime-license
```

默认 capture 合同固定为 `640×640`、DPR `1` 和背景 `#20242aff`。不要在批准 golden 后改变 viewport、DPR、背景、clip 时间或导出地址。

已有批准的 runtime golden 合同时，同时传入：

```powershell
  --golden-contract .\tests\goldens\p6-spine42\runtime.approved.json `
  --golden-root .\tests\goldens\p6-spine42
```

Harness 只写 `*.actual.png` 与 `*.actual.json`，不会自动创建或覆盖 `*.approved.png`。三个 case 的报告都必须是 `comparison.status="passed"`；没有传 golden 时的 `not-configured` 只证明捕获成功，不是截图回归通过。

## 故障排查

### `P5 source chain differs from the requested P3 bundle`

MotionInstance 与当前 P3 地址不配对。回到 `verify-motion-retarget` 核对 `source_addresses`，不要替换成同项目的其他 P3 bundle。

### motion 参数必须成对

setup-only 模式不传任何 motion 参数；动画模式同时传 `--motion-instance-sha256` 与 `--motion-bundle-sha256`。不要只提供其中一个。

### 精确导出地址不存在或复验失败

从成功的 compile 响应复制 `skeleton_json_sha256` 与 `bundle_sha256`。路径不能包含 `latest`、symlink、junction、大小写变体或额外文件。若内容已损坏，从可信上游重新编译；不要修补内容寻址目录。

### runtime 包被拒绝

确认 `--runtime-root` 指向 `@esotericsoftware/spine-player` 包目录，且包与 `spine-webgl` 都是精确的 `4.2.119`。Harness 不接受相邻版本，也不会从网络下载或从 CDN 回退。

### runtime capture 为 error 或 rejected

先检查 `window.__AUTOSPINE_RUNTIME_RESULT__` 和对应 `*.actual.json`。核对浏览器 DPR、固定 viewport、clip 是否存在、时间点、导出三文件 SHA 与 golden 合同。不要放宽阈值来掩盖版本、姿势或资产地址变化。

## 验收证据

P6 门禁已经在两份真实 See-through 样本上完成。以下地址由精确 P3/P5 来源重建，不是 `latest` 指针：

| 项目 | setup skeleton / bundle | idle bundle | wave.left bundle |
| --- | --- | --- | --- |
| `seethrough_output` | `61caa6a00568400ee11416f9d45ffcab9d1584657ebf5339fca3d1b8d2c77aea` / `5740a5956434b792a35ad850cdc517d77a03242436b7cf21ce8ddfe25b6a7de3` | `ca6b1e48d09aadccaa91657d75506968ce4acc9cf013587f7ff7841c0e49915e` | `4549497026c1a645674409f095a857d1443ff2e95f601802a51a1f8bcd130ce6` |
| `seethrough_output_5` | `f46662e4ab7c2e472f3441cd6c6884b75cc70c78142e994e6b01493a7a065aed` / `20a172bd26e19e5b119d74fbd39c6721377c85f2bd721038ce88d13733c85156` | `c63ef62e12a90c7358a956aae2d27bdd749195ecc77ae152ff1bf6ee39af328e` | `1a4f768379e6e3e6dac315c9662adf6903e8449aed9b5e64f2015c092d71b066` |

完整的六组 skeleton、atlas、PNG、run、report 与 bundle SHA，以及 attachment/atlas/动画指标，固定在 [真实 P6 导出合同](../tests/goldens/p6-spine42/real-exports.approved.json)。设置 `AUTOSPINE_VERIFY_REAL_P6_GOLDENS=1` 运行 `python -m unittest tests.test_p6_spine42_goldens`，会逐个从历史地址读回、重建完整上游链，并证明整个 workspace 的目录与文件哈希前后不变。

官方 runtime 门禁使用精确的 `@esotericsoftware/spine-player@4.2.119` 和合同内固定的 npm integrity。A/B 各自的 setup、`idle@1.0s`、`wave.left@0.6s` 均在 640×640、DPR 1 下成功加载；批准后第二轮比较的 differing pixels、differing ratio、MAE 与最大通道差在六例中全部为 0。合同与六张 approved PNG 位于 [runtime 截图合同](../tests/goldens/p6-spine42/runtime.approved.json) 同目录。
