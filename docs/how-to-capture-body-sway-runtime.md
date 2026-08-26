# 捕获并封存 body-sway 官方 runtime 证据

本文说明如何把一个已通过 P10.2 结构探针的 body-sway 决定，重新编译为临时 Spine 4.2 预览，并用本机 Chrome/Chromium 捕获固定姿势 PNG。命令只产生 `captured_unreviewed` 证据，不会自动批准动画或解除发布门禁。

## 前置条件

准备以下输入：

- P10 candidate、人工 decision 和 P10.2 probe report 三个 canonical JSON 文件；
- 同一项目的 Layer Manifest、P3、P5 和 P9 七个完整 SHA；
- Windows 本机一个明确路径的 Google Chrome 或 Chromium；当前 runner 不在其他操作系统上启动浏览器；
- 由操作者在仓库外安装的 `@esotericsoftware/spine-player@4.2.119` 包目录。

runtime 包必须包含精确版本的 `package.json`、`spine-player.min.js`、`spine-player.min.css` 和 `LICENSE`。工具不会下载 runtime，也不会从 CDN 回退。`LICENSE` 文件存在不代表已经取得授权；运行前仍需由操作者确认自己的使用权限。

当前 harness 的威胁模型是可信的单用户本机：服务只绑定 loopback，并校验 Host 与同源 POST，但不把同一台机器上的恶意进程视为隔离边界。Windows 驱动会从首次 snapshot 前到最终 exact replay 后持续持有浏览器文件句柄，阻止随后打开的写入、重命名和删除操作；它还会在恢复主线程前查询已启动进程的映像路径并重新哈希 launcher 文件。这不是对内存中已映射 PE 页的规范化密码学哈希，也不声称抵抗预先持有可写句柄的同用户攻击者。不要在不可信的共享主机上运行捕获命令。

Windows 捕获器为了在恢复 Chrome 主线程前把完整进程树放入可关闭的 Job Object，会固定传入 `--no-sandbox`；Chrome 自身的 sandbox 子 Job 与该归属模型不兼容。这个选择不是一般浏览器安全建议，而是一个被 capture profile 明文记录的测试专用降级：`chromium_sandbox` 为 `disabled-for-owned-job`，`input_trust` 只允许精确固定的 runtime 与编译器生成的本地资产，`content_boundary` 只允许 loopback、CSP 和零外部资产。不得用该驱动打开任意 URL、第三方 HTML、用户脚本或外部资源；发布门禁不会因为进程 smoke 或截图成功而解除。

## 运行捕获命令

在项目根目录执行：

```powershell
$runtimeRoot = Resolve-Path `
  .\workspace\runtime\spine-player-4.2.119\node_modules\@esotericsoftware\spine-player
$chrome = Resolve-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe'

python -m autospine_workbench capture-body-sway-runtime <project-id> `
  --candidates <idle-behavior-candidates.json> `
  --decision <idle-behavior-decision.json> `
  --probe-report <body-sway-probe-report.json> `
  --layer-manifest-sha256 <sha256> `
  --p3-rig-sha256 <sha256> `
  --p3-bundle-sha256 <sha256> `
  --motion-instance-sha256 <sha256> `
  --motion-retarget-bundle-sha256 <sha256> `
  --motion-instance-v2-sha256 <sha256> `
  --reviewed-motion-bundle-sha256 <sha256> `
  --runtime-root $runtimeRoot `
  --browser-executable $chrome `
  --state-root .\workspace `
  --acknowledge-spine-runtime-license
```

也可以把许可确认设为精确环境值 `1`：

```powershell
$env:AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED = '1'
```

`true`、`yes`、带空格的 `1` 或仅存在 `LICENSE` 文件都不会被视为确认。

## 读取结果

成功时，stdout 是单个 canonical JSON 对象，主要字段包括：

- `status: "captured_unreviewed"`；
- preview、capture、artifact set 和 bundle SHA；
- 固定 case 数与浏览器 family/version；
- content-addressed 发布目录；
- `release_gate.status: "blocked"` 及未关闭的原因。

固定库存只包含一个 canonical capture manifest 和 `captures/*.png`。默认地址为：

```text
workspace/builds/<project>/body-sway-runtime-captures/
  <temporary-preview-sha>/<bundle-sha>/
```

同一组精确字节再次发布时只会完整回读后复用；缺文件、多文件、大小写别名、路径 alias 或字节变化都会失败，不会覆盖旧证据。

## 运行真实浏览器 smoke

仅验证浏览器进程、loopback POST、PNG 解码、Job Object 清理和 profile 释放时，可以运行不含官方 runtime 的进程 smoke：

```powershell
$env:AUTOSPINE_REAL_CHROME = $chrome
python -B -m unittest tests.test_body_sway_real_chrome_smoke
```

这个测试使用 test-only `SpinePlayer` stub，不证明官方 Spine runtime 兼容性。

要验证实际 `4.2.119` runtime 的 setup 和组合姿势，必须同时提供已授权 runtime，并显式确认许可：

```powershell
$env:AUTOSPINE_REAL_CHROME = $chrome
$env:AUTOSPINE_SPINE42_RUNTIME_ROOT = $runtimeRoot
$env:AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED = '1'
python -B -m unittest tests.test_body_sway_licensed_runtime_smoke
```

## 结果不能证明什么

捕获成功只证明固定浏览器、固定 runtime 和固定 case 产生了可验证 PNG。它仍不证明：

- 人工视觉质量已经通过；
- 离散采样之间的连续时间安全；
- 未标注 attachment 接缝没有裂缝；
- 当前幅度适合所有角色；
- 可以生成 MotionInstance v3 或发布 Spine 动画。

下一步必须对固定 capture bundle 做逐 case 人工视觉复核；复核决定要绑定 capture、artifact set 和 bundle 的完整 SHA，不能按目录扫描或使用 `latest`。
