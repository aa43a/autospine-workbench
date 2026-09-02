# 编译并复验 P10.5d v2 动态接缝结构证据

本文面向维护者和专业操作者，说明如何用显式内容地址把一个 P10.4b v2 连续结构证明与一个
P10.5c v1 静态 ReviewedSeamAnchorSet 组合为不可变 P10.5d v2 bundle。

普通用户自动入口已经交付。P10.4b v2 完成页会携带 exact `job_id` 和 `safety_run_id` 打开：

```text
http://127.0.0.1:8765/body-sway-dynamic-seam-v2.html?job_id=<JOB_ID>&safety_run_id=<SAFETY_RUN_ID>
```

页面会自动解析同一角色 current P10.5c，不要求选择项目、文件或填写 SHA。以下 CLI 仍保留给
需要显式内容地址复验的专业操作者；它不会扫描 `latest`，也不会猜测项目或静态接缝集。

## 使用自动页面

1. 在已完成的 P10.4b v2 结果页点击“开始 P10.5d v2 动态接缝分析”。
2. 页面自动创建或恢复 append-only attempt，并在独立 BelowNormal worker 中运行分析。
3. 等待父进程完成 exact readback 和最终 current-head recheck；只有这些检查通过才显示完成回执。
4. 若失败，页面保留不可变失败回执；点击新建 attempt 时必须在确认弹窗中再次确认，旧 attempt
   和部分结果不会被覆盖或复用。

页面显示的是 anchor residual 与非 Raster gap proxy。Overlap 仍为 `not_evaluated`；Raster、
official Runtime、视觉质量和 release authority 仍为 blocked。

## 前置条件

准备以下五项精确输入：

1. 项目 ID，例如 `seethrough_output`；
2. 已完成 P10.4b v2 safety-analysis run 的完整 run ID；
3. 该 run 的 continuous proof SHA-256；
4. current P10.5c v1 reviewed set SHA-256；
5. 同一 reviewed set 的 bundle SHA-256。

这些输入必须闭合到同一个 project、clip、Manifest、P3/RigIR 与 current review chain。历史
P10.5c 地址即使仍可精确读取，也不能替代编译时的 current head。

在项目根目录准备 Python 模块路径：

```powershell
cd E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

## 编译并发布

运行：

```powershell
python -B -m autospine_workbench compile-body-sway-dynamic-seam-probe-v2 `
  <PROJECT> `
  <P10_4B_V2_RUN_ID> `
  --continuous-proof-sha256 <CONTINUOUS_PROOF_SHA256> `
  --reviewed-set-sha256 <REVIEWED_SET_SHA256> `
  --reviewed-set-bundle-sha256 <REVIEWED_SET_BUNDLE_SHA256> `
  --workspace .. `
  --state-root .\workspace
```

命令执行以下门禁：

1. 按 run ID 和 continuous proof SHA 精确读取 P10.4b v2 结果；
2. 按 set/bundle 双 SHA 精确读取 P10.5c v1；
3. 建立 path-free P10.5d v2 source closure，并重算 probe；
4. 在分析前、发布前和发布后共观察三次 current visual/seam heads；
5. 只有 `before = prepublish = postpublish` 时才接受发布；
6. 发布后立即按 probe/bundle 双 SHA exact-readback。

成功 stdout 的 `status` 为 `compiled`，并返回 `probe_sha256`、`bundle_sha256`、上游地址、
probe 摘要、claims、release gate 和三次 head observation。`reused=true` 只表示相同 canonical
内容已存在，不表示跳过输入复验或获得新的 authority。

## 固定三文件 inventory

每个 bundle 只包含以下三个文件：

| 文件 | 内容 |
| --- | --- |
| `body-sway-dynamic-seam-source-v2.json` | P10.4b v2、P10.5c v1、Manifest/P3/RigIR 与 review 身份的 path-free source closure |
| `body-sway-dynamic-seam-probe-v2.json` | 每段、每关系和每个 reviewed anchor pair 的结构分析结果 |
| `bundle-manifest.json` | 文件 SHA/大小、project/clip、probe/bundle 身份和历史 authority 边界 |

bundle 使用 `project_id + probe_sha256 + bundle_sha256` 精确寻址。probe 中的 anchor residual
和 gap proxy 是结构工程代理；overlap 明确为 `not_evaluated`。它们不是 attachment raster
边界、视觉接缝质量或 official Runtime 等价结论。

## 复验历史 bundle

使用编译回执中的双 SHA：

```powershell
python -B -m autospine_workbench verify-body-sway-dynamic-seam-bundle-v2 `
  <PROJECT> `
  --probe-sha256 <PROBE_SHA256> `
  --bundle-sha256 <BUNDLE_SHA256> `
  --state-root .\workspace
```

成功 stdout 的 `status` 为 `verified`。reader 会重读固定 inventory、逐字节验证 manifest、source、
probe、文件 SHA 和 framed bundle SHA，并重放 source/probe 语义 validator。

verify 是历史 exact-bytes 复验：它明确返回 `current_head_checked=false` 和
`permanent_current_authority_claimed=false`。它不会读取当前 visual/seam head，也不能把过去一次
编译时有效的 head observation 延长为永久 authority。需要消费 current 结果时必须重新运行
compile 路径。

## 结果边界

- 退出码 `0` 表示命令完成，不保证 probe 获得动态接缝认证；`probe_status` 仍可能为
  `indeterminate`。
- 退出码 `2` 表示输入、current head、编译、发布或 exact readback 未闭合；命令只输出固定、
  path-free 错误，不应从部分目录推断成功。
- 无论 probe 状态如何，official Runtime、raster/视觉接缝、MotionInstance v3、可发布 timeline
  和 release authority 都保持 blocked。
- CLI、内容寻址 store/exact reader、server/job/UI 自动入口与 BelowNormal worker 已交付；真实
  样本 A 仍须等待当前 P10.4b run 完成并重启服务后执行。
