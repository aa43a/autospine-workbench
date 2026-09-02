# 自动分析 P10.4b v2 身体摆动结构安全

本文面向普通操作员和需要精确重放的维护者，说明如何从一个已完成、当前仍获批准的
P10.3c v2 Runtime 复核任务，自动生成 P10.4b1 v2 九档幅度候选和 P10.4b2 v2
连续预览模型证明。

普通流程只需要完整 `job_id`。不要选择项目或 JSON，不要复制 SHA，也不要把冻结 v1
命令的参数填入本流程。

## 前置条件

开始前应满足：

- official Runtime job 已完成且拥有完整 execution/capture 凭据；
- P10.3c v2 current head 为 `sampled_visual_approved`；
- P10.4a v2 可以从同一 job 重放 current admission；
- 对应的 P10.1、P10.2、CaptureFraming 与 Preview v2 来源没有改变。

P10.4a 页面显示“准入检查通过”后，才会出现“继续 P10.4b v2 自动安全分析”。

## 在页面中自动运行

点击 P10.4a 成功结果中的下一步按钮，或打开：

```text
http://127.0.0.1:8765/body-sway-safety-analysis-v2.html?job_id=<完整 job ID>
```

页面会自动执行以下只读流程：

1. 读取 job 的当前分析入口状态；
2. 重放 P10.4a v2 admission；
3. 恢复尚未结束的 active run，或为新的 terminal/no-run 访问创建下一次分析；
4. 计算 `0/8…8/8` 九档离散结构点；
5. 对全部相邻 Preview v2 tick 和统一 gain `λ∈[0,1]` 做有界区间证明；
6. 在分析结束前重新检查 current visual-review head；
7. 密封两个 canonical v2 文档，并在页面显示无本机路径的内容地址技术回执。

入口本身会快速返回。精确 admission 重放和 CPU 密集的连续证明在独立、低优先级 worker
子进程中执行，不占用 HTTP 服务进程；完整证明仍可能需要较长时间，但页面轮询和其它 API
应保持可响应。进度进入 `continuous_boxes` 时，页面会显示“区间盒证明心跳”，用于说明有界
区间细分仍在推进；随后 `continuous_validation` 会按同一总盒数显示第二遍精确重算进度。
两者都由 worker 当前可读的 JSONL 消息立即转发，不再等待固定大小缓冲区填满，操作者无需
刷新或重启。

页面可以安全刷新：已存在的 queued/running run 会继续执行和轮询。子进程只发布严格绑定当前
run 的 staged amplitude/continuous 工件；父进程独立读取、重验后才追加唯一的 `completed`
事件。子进程失败、退出或被终止时不会发布部分完成态，也不会把 staged 工件当作通过。

页面“技术详情”只显示两份结果的 `format`、`format_version`、`sha256` 和 `size_bytes`。
完整 canonical 文档可能包含合法的逻辑资源字段，因此只允许专业 CLI 在本机输出，不通过普通
HTTP 页面传输。

## 阅读四条证据轨道

结果页把容易混淆的四个范围分开显示：

1. **九档离散结构点**：显示 `0/8…8/8` 在固定 Preview v2 sample ticks 上的
   FK、动态视口 containment、mesh 和共享索引结构状态。
2. **相邻时间连续区间**：显示每对相邻 tick 在 `time × λ` 闭区间上的结构证明。
   `indeterminate` 表示预算内尚不能证明，是有效完成结果，不是运行错误。
3. **人工视觉证据**：只标记当前 `8/8`，即 100% reviewed gain。其它八档没有获得
   official Runtime 人工视觉批准。
4. **可发布安全范围**：始终显示不可用。结构证明不能自动变成视觉范围或发布许可。

如果全部相邻区间都获得 `continuous_structural_certified`，顶层状态才会成为
`continuous_preview_model_structural_certified`，表示该 run 锁定的 Preview v2 数学模型在统一
`λ∈[0,1]` 上的连续结构安全。它仍不声明 official Runtime
连续等价、视觉幅度范围、attachment 间接缝、MotionInstance v3 或 release authority。

## 使用专业 CLI 精确重放

CLI 同样只接受一个完整 job ID：

```powershell
cd E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -B -m autospine_workbench compile-body-sway-safety-analysis-v2 `
  <完整-job-id> `
  --workspace .. `
  --state-root .\workspace
```

默认 stdout 是 path-free 摘要，包含：

- job、package、project、clip 和 P10.4a admission 身份；
- amplitude/continuous 两份文档 SHA；
- 九档数量、连续区间摘要、claims 和 release gate。

需要审计完整 canonical 文档时增加 `--documents`：

```powershell
python -B -m autospine_workbench compile-body-sway-safety-analysis-v2 `
  <完整-job-id> --workspace .. --state-root .\workspace --documents
```

命令不写入 state，也不扫描 `latest`。退出码 `0` 表示分析成功完成；此时顶层状态仍可能是
`indeterminate`。退出码 `2` 表示 exact job、admission、source 或 current-head 闭合失败，错误
JSON 不暴露内部路径和底层异常。

## 失败与重试

常见失败包括：

- job 不存在、未完成或 capture event chain 不闭合；
- P10.3c current decision 已改变、被拒绝或不再是当前 head；
- Preview v2、world viewport、P10.1、P10.2 或 CaptureFraming 来源发生变化；
- 分析期间出现新的人工 revision；
- canonical source、幅度候选或连续证明不能精确重放。

失败页会保留本次不可变 failure receipt。点击“创建新的分析尝试”时，页面先显示二次确认，
说明将重新读取 current admission、不会复用失败尝试的部分输出；确认后才创建新的 attempt。
旧 failure receipt 和事件历史不会被覆盖。来源改变时应返回 P10.3c/P10.4a，沿新 current chain
重新采集或复核；不要反复重试已经明确失效的旧来源。

## 与冻结 v1 的边界

以下命令继续只服务冻结 v1 历史链：

- `compile-body-sway-amplitude-envelope`
- `compile-body-sway-continuous-proof`

它们使用 v1 admission、schema、hash domain 和显式地址参数，不能消费 P10.4a/P10.4b v2。
新 v2 合同只复用经过固定测试的底层采样、几何与区间数学，不复用 v1 authority 或输出身份。

样本 A 的 current P10.5c v1 静态接缝集已经闭合，不需要再次重建或提交六项静态决定。
P10.4b v2 完成后的下一项是 P10.5d v2：它必须显式消费本次 P10.4b v2 proof 与当前
P10.5c v1 静态集，并保持与冻结 P10.5d v1 的版本隔离。发布门禁在动态接缝、Runtime 与视觉
证据闭合前持续为 `blocked`。当前专业 CLI 操作见
[编译并复验 P10.5d v2 动态接缝结构证据](how-to-compile-body-sway-dynamic-seam-v2.md)；普通
server/job/UI 自动入口也已交付。P10.4b 完成态可一键携带 exact
`job_id+safety_run_id` 打开 `body-sway-dynamic-seam-v2.html`，页面自动解析 current
P10.5c；真实样本 A 仍须等待本次 P10.4b run 完成并重启服务后执行。
