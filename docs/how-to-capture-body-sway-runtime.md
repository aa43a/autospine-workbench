# 运行 P10.3 官方 Runtime 自动采集

本文面向普通操作员，说明如何从已复核的 body-sway 动作包启动一次官方 Spine Player 采集。页面会自动读取项目、动作包、当前 P10.1 决定、CaptureFraming 和 Preview v2；不需要选择 JSON 文件或填写 SHA-256。

采集成功只会得到 `captured_unreviewed` 的精确证据。它不会自动批准画面，也不会解除发布门禁。

## 开始前

请确认：

- 项目的 P10.1 身体摆动决定已经保存；
- P10.2 结构探针没有基础动作阻塞项；
- 当前 CaptureFraming 已有人工 `accept` 或 `adjust` 决定；
- 本机已按授权要求安装 Spine Player `4.2.119`，并安装 Chrome；
- 你有权在本项目中使用该 Spine Runtime。

样本 A 的 CaptureFraming 已接受 revision 1。六个旧 job 分别在不固定的 case 处失败；每个失败 job 都作为不可变历史保留，且没有发布部分 execution 证据。execution v2 runner `1.1.0` 随后已完成 job `d7150fa1…` 的 43/43 采样并发布完整 execution；该 job 尚未提交 P10.3c 人工视觉 revision。

## 1. 打开采集页

启动工作台后，打开：

[http://127.0.0.1:8765/body-sway-runtime-capture.html](http://127.0.0.1:8765/body-sway-runtime-capture.html)

页面会自动完成以下工作：

1. 列出具备当前 P10.1 和 CaptureFraming 的项目/动作包，并尽量选择唯一可用项。
2. 读取当前 P10.1、framing、source、plan 和 report 身份。
3. 编译 package-centric Preview v2，并校验它绑定的 world viewport、采样时刻和完整 cases。
4. 校验固定的本地 Spine Player 与 Chrome 环境。

普通操作员不需要复制 Preview SHA、execution bundle SHA 或 artifact SHA。这些身份由工作台在后续步骤中自动传递。

## 2. 检查 Runtime 环境

当前固定 profile 使用：

- `@esotericsoftware/spine-player@4.2.119`；
- 包内 `package.json`、`spine-player.min.js`、`spine-player.min.css` 和 `LICENSE` 的精确字节；
- 本机 Chrome 的精确可执行文件与版本；
- 工作区内固定的 Runtime 目录 `runtime/spine-player-4.2.119/node_modules/@esotericsoftware/spine-player`。

页面会显示每项校验结果。缺文件、版本不符、字节变化或 Chrome 不可用时，不要手工绕过；按页面提示修复环境后重新读取。

`LICENSE` 文件存在不等于已经取得使用授权。工作台不会下载 Runtime、不会从 CDN 回退，也不会替操作者判断许可。

## 3. 显式确认并启动

1. 阅读许可说明，勾选“我确认拥有使用该 Spine Runtime 的权限”。
2. 点击运行按钮。
3. 在二次确认弹窗中核对项目、动作包和当前 revision，再确认启动。

取消弹窗不会创建 job，也不会写入决定。许可勾选不会跨运行替你自动确认；每次真实执行都需要二次确认。

## 4. 查看异步进度

采集以可恢复查询的异步 job 运行。页面会显示当前阶段、进度、事件和 job ID。刷新页面后可按同一 job 继续查询，不需要重新提交。

可能看到的阶段包括：

- 排队与 exact replay；
- Preview v2 编译与 Runtime 环境复核；
- 官方 Runtime 捕获；
- execution bundle 封存；
- 完成、取消、中断或失败。

失败页会根据不可变事件链显示安全诊断：停止阶段、错误类别、已完成样本数，以及能够确定时的“下一个未完成样本序号”。该序号只定位续跑边界，不等于已经证明该样本本身有问题。原始异常、本地路径和命令行不会通过 HTTP 暴露。

失败或服务关闭造成的中断都不会自动重试。当前页面没有主动取消运行中 job 的按钮。检查原因后，由操作者重新确认并创建一次新的 job。未完整封存的截图不会作为可复核的 execution 发布。

### 六次历史失败与 runner 1.1.0 completed job

六次真实 job 的失败位置并不固定。复盘确认旧 execution v2 浏览器驱动仍携带冻结 v1 使用的
`--dump-dom` 和 `--virtual-time-budget`，它们与异步 `collector-terminal` 完成信号冲突；另外，
截图已经提交后，主动关闭浏览器进程树可能与 stdout reader 的退出发生竞争，从而把已完成的
collector 回调误报为失败。

新的 P10.3 v2 execution runner `1.1.0` 使用以下生命周期：

- `page_lifetime=collector-terminal`，以 exact collector callback 已提交作为页面完成条件；
- execution v2 命令移除 `--dump-dom` 和 `--virtual-time-budget`；
- 仅当 exact 截图已经提交，并且 stdout 异常来自 runner 主动 teardown 时，才容忍 reader 关闭异常；
- 提交前的 stdout 读取失败、输出超限、reader 未退出、pipe 无法关闭、Runtime 报错或截图未提交仍然 fail closed；
- 新失败 job 继续保存 path-free 的精确 `failure_code`，不把异常文本、本地路径或命令行写入公开事件。

这些变化只作用于 P10.3 execution v2。冻结的 P10.3 v1 driver、地址和复核语义保持不变。runner
上述修正已经由 runner 1.1.0 的 43/43 completed job 覆盖真实执行路径。它只证明该次固定采样完整封存，不能代替 P10.3c 人工视觉决定。

## 5. 完成后进入 P10.3c

完成的 job 会生成不可变 execution bundle，并显示“进入视觉复核”入口。页面只携带完整 `job_id`；服务端从不可变 completed job 自动解析以下四段精确地址：

- project；
- Preview v2；
- execution bundle；
- artifact set。

点击入口即可进入 P10.3c v2。不要从构建目录猜测 `latest`，也不要手工改写地址。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 没有可选动作包 | 先完成 P10.1、P10.2 和 CaptureFraming；刷新项目列表。 |
| Runtime 校验失败 | 检查固定 4.2.119 包的必需文件与版本；不要用其他版本冒充。 |
| Chrome 校验失败 | 安装或恢复标准 Chrome，并重新读取环境。 |
| 点击运行后没有 job | 检查许可勾选与二次确认是否都完成。 |
| job 中断或失败 | 查看失败卡中的阶段、错误类别和未完成样本序号；系统不会自动重试，修复后重新显式启动。 |
| 看到历史六次失败 job | 这是不可变运行历史，不要删除或改写；选择 runner 1.1.0 的 completed job 进入复核。 |
| job 已完成但仍显示发布阻塞 | 正常。还必须完成 P10.3c 时间轴人工复核，后续门禁也仍存在。 |

## 安全与证据边界

捕获器只用于可信的单用户 loopback 工作台和固定本地资产。它不会打开第三方 URL，也不把进程 smoke 或测试 stub 当作官方 Runtime 证据。

六次失败 execution 没有产生可进入 P10.3c 的部分证据。当前 completed execution 只能证明：固定 Preview v2、固定 Runtime/Chrome profile 和固定 cases 产生了可验证的采样图像。它不能证明：

- 人工视觉质量已经通过；
- 离散采样之间连续安全；
- 所有接缝与遮挡都安全；
- 当前幅度适合其他角色；
- 动画已经可以发布。

下一步按[复核 P10.3c 官方 Runtime 采样帧](how-to-review-body-sway-runtime.md)沿时间轴判断。页面会预填本地通过草稿以减少点击，但系统绝不会据此自动提交或批准。
