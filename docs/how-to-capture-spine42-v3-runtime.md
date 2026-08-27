# 捕获并复核 P10.7b Spine 4.2 v3 Raster 证据

本文面向负责 P10.7b 的本地操作者。目标是把一个精确的 P10.7a 五文件 bundle
交给官方 `@esotericsoftware/spine-player@4.2.119`，捕获固定采样帧，复验不可变证据，
再把人工判断编译为独立 decision。

本流程只覆盖 capture plan 中的离散 case 和 setup attachment inventory。即使全部指标与
人工决定通过，也不证明连续时间安全，不产生永久 current-head authority、可发布 Spine
timeline 或 release authority。

## 1. 准备精确输入

先按[编译并复验 P10.7a Spine 4.2 v3](how-to-compile-spine42-v3.md)取得：

- 项目 ID；
- `skeleton_json_sha256`；
- `spine42_v3_bundle_sha256`，也就是 P10.7a 输出中的 `bundle_sha256`。

不要填写 `latest`、缩写 SHA，或从目录中自动选择一个 bundle。P10.7b 会先按这两个完整
SHA 重放 P10.7a 来源链；地址不存在、内容被修改或跨项目接线时会直接失败。

还需要：

- Windows 本机的 Google Chrome 或 Chromium 可执行文件；
- 操作者有权使用的官方 `@esotericsoftware/spine-player@4.2.119` 包目录；
- 足够存放全部 PNG 的 state root。单个 bundle 的捕获上限为 512 MiB。

仓库不会从 CDN 回退，也不会把 `LICENSE` 文件存在解释为已经取得授权。运行 capture 前，
操作者必须根据自己的 Spine 许可确认有权使用该 runtime。工具记录确认值与 runtime 文件
摘要，但这些记录不替代法律或商业许可审查。

## 2. 检查 Runtime 与浏览器路径

在项目根目录打开 PowerShell：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

$runtimeRoot = Resolve-Path `
  .\workspace\runtime\spine-player-4.2.119\node_modules\@esotericsoftware\spine-player
$chrome = Resolve-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe'

(Get-Content -Raw (Join-Path $runtimeRoot 'package.json') | ConvertFrom-Json).version
Test-Path (Join-Path $runtimeRoot 'dist\iife\spine-player.min.js')
Test-Path (Join-Path $runtimeRoot 'dist\spine-player.min.css')
Test-Path (Join-Path $runtimeRoot 'LICENSE')
```

版本必须精确为 `4.2.119`。实际文件布局由命令的 runtime 输入验证器检查；以上命令只是
运行前快速排错。不要用 `4.3.x`、`latest`、CDN 文件或 test stub 替代正式证据输入。

## 3. 捕获并发布不可变证据

```powershell
python -B -m autospine_workbench capture-body-sway-spine42-v3-runtime <project-id> `
  --skeleton-json-sha256 <skeleton-json-sha256> `
  --spine42-v3-bundle-sha256 <spine42-v3-bundle-sha256> `
  --runtime-root $runtimeRoot `
  --browser-executable $chrome `
  --state-root .\workspace `
  --acknowledge-spine-runtime-license
```

也可以用精确环境值 `1` 完成同一项确认：

```powershell
$env:AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED = '1'
```

不要把仅存在环境变量、`true`、`yes` 或 runtime 自带的 `LICENSE` 文件当作确认。

捕获器会：

1. 重放精确 P10.7a bundle；
2. 固定 runtime profile、viewport、DPR、case 与 attachment inventory；
3. 为每个 case 捕获 opaque composite、transparent composite 和每个 setup attachment isolate；
4. 以 `alpha >= 1` 的二值掩码从 PNG 字节计算 isolate union、missing/extra/xor、边界、裁切和 isolate 非空指标；
5. 把 manifest、metrics 与全部 PNG 发布到内容寻址目录后按精确地址读回。

成功输出中应保存以下字段：

- `address.skeleton_json_sha256`；
- `address.spine42_v3_bundle_sha256`；
- `capture_plan_sha256`；
- `raster_metrics_sha256`；
- `address.capture_bundle_sha256`；
- 浏览器 family/version、case/attachment/artifact 数和 `summary.metrics_status`。

默认地址为：

```text
workspace/builds/<project-id>/spine42-v3-runtime/
  <spine42-v3-bundle-sha256>/<capture-bundle-sha256>/
```

固定库存包括：

```text
capture-manifest.json
metrics.json
captures/...
```

manifest 会绑定 runtime JS/CSS、`package.json`、`LICENSE`、浏览器可执行文件、捕获计划和
P10.7a 来源摘要。它的状态仍是 `captured_unreviewed`，`release_gate.status` 仍是
`blocked`。

## 4. 按精确地址复验

```powershell
python -B -m autospine_workbench verify-body-sway-spine42-v3-runtime <project-id> `
  --spine42-v3-bundle-sha256 <spine42-v3-bundle-sha256> `
  --capture-bundle-sha256 <capture-bundle-sha256> `
  --state-root .\workspace
```

verify 不启动浏览器，也不扫描 `latest`。它会校验固定目录库存、重算 capture bundle、PNG
和 metrics 摘要，并重放 manifest 指向的精确 P10.7a 来源。成功只表示这份历史 sampled
evidence 可按字节复验；它不重新取得 current-head authority。

## 5. 准备 Raster 人工复核候选

```powershell
python -B -m autospine_workbench prepare-body-sway-spine42-v3-raster-review <project-id> `
  --spine42-v3-bundle-sha256 <spine42-v3-bundle-sha256> `
  --capture-bundle-sha256 <capture-bundle-sha256> `
  --state-root .\workspace
```

prepare 是只读操作。它会从精确 capture 生成 candidate，列出：

- 每个固定 case 的 opaque composite、指标状态与 `evidence_sha256`；
- 每个 setup attachment 在全部 case 中的 isolate、边界与裁切证据；
- `metrics_status`、candidate SHA 和保持 blocked 的 release gate。

把完整 canonical candidate 保存为 UTF-8 JSON，并逐项打开它引用的 `captures/...` PNG。
不要只看总指标；透明边缘、遮挡顺序、极值姿势和 loop 邻近帧仍需要人工判断。

## 6. 编写并提交完整人工决定

创建一个 UTF-8 JSON 输入，覆盖 candidate 中全部 case 与 attachment。每行的 ID 和
`evidence_sha256` 必须逐字复制：

```json
{
  "reviewer_id": "reviewer-01",
  "notes": "逐项检查固定帧轮廓、遮挡和 attachment isolate。",
  "case_decisions": [
    {
      "case_id": "<case-id>",
      "evidence_sha256": "<case-evidence-sha256>",
      "action": "approve",
      "notes": ""
    }
  ],
  "attachment_decisions": [
    {
      "attachment_key": "<slot-id>::<attachment-id>",
      "evidence_sha256": "<attachment-evidence-sha256>",
      "action": "approve",
      "notes": ""
    }
  ]
}
```

`action` 只能是 `approve`、`reject` 或 `unobservable`。后两者必须填写非空备注；任一
非 approve 行或 raster metrics 未通过，整体状态都会是 `sampled_raster_rejected`。

```powershell
python -B -m autospine_workbench submit-body-sway-spine42-v3-raster-review <project-id> `
  --spine42-v3-bundle-sha256 <spine42-v3-bundle-sha256> `
  --capture-bundle-sha256 <capture-bundle-sha256> `
  --candidate .\review\spine42-v3-raster-candidate.json `
  --review-input .\review\spine42-v3-raster-review.json `
  --state-root .\workspace
```

需要在同一 candidate 上追加一轮决定时，再提供上一份完整 decision：

```powershell
python -B -m autospine_workbench submit-body-sway-spine42-v3-raster-review <project-id> `
  --spine42-v3-bundle-sha256 <spine42-v3-bundle-sha256> `
  --capture-bundle-sha256 <capture-bundle-sha256> `
  --candidate .\review\spine42-v3-raster-candidate.json `
  --review-input .\review\spine42-v3-raster-review-r2.json `
  --previous-decision .\review\spine42-v3-raster-decision-r1.json `
  --state-root .\workspace
```

submit 会先按 project、P10.7a bundle 与 capture bundle 地址重放 candidate，再要求
`--candidate` 字节与重建结果一致；它随后只编译并验证 path-free decision，不发布 revision，
也不会自动确认操作者实际查看过图片。请把 stdout 作为 UTF-8 canonical JSON 显式保存和
审计；该文件可直接作为下一轮的 `--previous-decision`。即使结果为
`sampled_raster_approved`，它也只覆盖该 capture plan 的离散 case 与完整 setup attachment
inventory；continuous runtime raster safety、永久 head、publishable timeline 与 release
authority 仍保持 false/blocked。

## 7. 真实样本验收清单

P10.7b 基础设施可用不等于真实角色验收已经完成。进入后续 attachment switch 前，至少对
两份真实 See-through 样本分别完成：

1. 生成并复验各自的 P10.7a 精确 bundle；
2. 使用已授权的官方 `4.2.119` runtime 完整捕获，不能使用 stub；
3. 确认 setup 与既有 P6 golden 没有未批准变化；
4. 复验 capture bundle，并逐 case、逐 attachment 完成人工决定；
5. 保存各自的 candidate、review input 和 decision，记录任何 reject/unobservable 原因。

缺少任一真实 P10.7a 输入时，应把该样本记录为 prerequisite missing，而不是用 fixture、旧
P10.3 capture 或另一角色的通过结果替代。结构差异 fixture 可以验证工具链，但不能替代两份
真实样本的视觉结论。

## 常见失败

- runtime 版本、JS/CSS、`package.json` 或 `LICENSE` 不匹配：使用精确 `4.2.119` 包并重新检查路径；
- 未确认许可：传入显式 flag 或精确环境值 `1`，同时保留独立许可审查记录；
- P10.7a 地址错误：先运行 `verify-body-sway-spine42-v3`，不要扫描目录寻找替代输入；
- 浏览器启动或回调失败：确认 Chrome 路径、Windows 环境和本机安全软件日志；
- metrics rejected：检查 transparent composite 与 isolate union 的 missing/extra/xor、裁切和空 isolate，不要直接改成通过；
- review 输入被拒绝：确认全部行覆盖、ID/证据 SHA 未改写，并为 reject/unobservable 填写备注；
- 旧 decision 无法追加：确认 previous decision 与同一 candidate 绑定且 revision 连续。

捕获期间只应加载编译器生成的本地资产。loopback、CSP 和浏览器进程隔离属于本机测试边界，
不是面向不可信输入或多用户主机的安全沙箱。
