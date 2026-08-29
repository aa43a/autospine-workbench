# 复核并发布 Kimodo 动作策略

本指南面向已经发布 P3 mesh、P5 retarget、P7 Kimodo NPZ 和 P8 projected-motion bundle 的开发者。目标是把脚接触与深度证据转为人工批准的 root correction 和 draw order，预览 MotionInstance v2/Spine 4.2 v2，再发布并只读复验一个不可变 P9 bundle。

本流程不会自动批准 heading、scale 或附件切换。正式 handoff 文档使用 `--document-only`；Foot/Depth 候选同时保留默认 CLI envelope，因为其中的 `report_sha256` 是复核台绑定同一次结果所必需的身份。

## 1. 固定输入地址

开始前记录同一来源链上的完整地址，不要使用目录扫描结果、缩写 SHA 或 `latest`：

| Stage | 必须固定的地址 |
| --- | --- |
| P3 | `PROJECT`、`p3_rig_sha256`、`p3_bundle_sha256` |
| P5 | `PROJECT`、`motion_instance_sha256`、`motion_retarget_bundle_sha256`；bundle 内还固定 target profile |
| P7 | `motion_sha256`、`motion_bundle_sha256` |
| P8 | `projected_motion_sha256`、`projected_bundle_sha256` |
| P9 | 发布后得到 `PROJECT`、`motion_instance_v2_sha256`、`reviewed_motion_bundle_sha256` |

P3、P5 和 P8 必须已经由各自 exact reader 通过。Candidate 命令会重读精确 P3/P5/P8 地址；后续 decision/policy 通过 candidate SHA 保留这条链。P9 bundle verifier 会从 run manifest 重读并重建精确 P3/P5，同时检查已封存的 candidate 字节，但不重读 P8 bundle。任何命令都不会从相邻目录寻找替代输入。

在 PowerShell 会话中设置源码与地址变量：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$StateRoot = (Resolve-Path .\workspace).Path
$Project = "seethrough_output"

$P3Rig = "<64-hex-p3-rig-sha256>"
$P3Bundle = "<64-hex-p3-bundle-sha256>"
$P5Instance = "<64-hex-motion-instance-sha256>"
$P5Bundle = "<64-hex-motion-retarget-bundle-sha256>"
$P7Motion = "<64-hex-kimodo-motion-sha256>"
$P7Bundle = "<64-hex-kimodo-motion-bundle-sha256>"
$P8Motion = "<64-hex-projected-motion-sha256>"
$P8Bundle = "<64-hex-projected-motion-bundle-sha256>"
```

## 2. 安全写入 UTF-8 JSON

Windows PowerShell 5 的重定向和 `Out-File` 可能写入 UTF-16 或带 BOM 的 UTF-8。使用显式的 UTF-8 no-BOM encoder 保存命令 stdout：

```powershell
function Write-Utf8NoBom {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Text
  )
  $FullPath = [System.IO.Path]::GetFullPath($Path)
  $Parent = [System.IO.Path]::GetDirectoryName($FullPath)
  $null = [System.IO.Directory]::CreateDirectory($Parent)
  $Encoding = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText($FullPath, $Text, $Encoding)
}

function Read-CanonicalCliReport {
  param([Parameter(Mandatory = $true)][string]$EnvelopePath)
  $Report = (& python -c `
    "import json,sys; value=json.load(open(sys.argv[1],encoding='utf-8')); print(json.dumps(value['report'],ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')))" `
    $EnvelopePath) -join "`n"
  if ($LASTEXITCODE -ne 0) { throw "CLI envelope extraction failed" }
  return $Report
}
```

每次调用 CLI 后先检查 `$LASTEXITCODE`，再写文件。不要把错误 wrapper 当成下一阶段输入。`Read-CanonicalCliReport` 只从已成功的默认 envelope 提取并 canonical 序列化 `report`；不要用 PowerShell 的 JSON round-trip 重写候选，因为它可能改变数值类型。

## 3. 生成并检查 source evidence

先保留 Kimodo 的 contact、smooth root 和原始 heading 证据。这份文档不产生候选或运行时 timeline：

```powershell
$PolicyEvidence = (& python -m autospine_workbench compile-kimodo-policy-evidence `
  --motion-sha256 $P7Motion `
  --motion-bundle-sha256 $P7Bundle `
  --projected-motion-sha256 $P8Motion `
  --projected-bundle-sha256 $P8Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "policy evidence compile failed" }
Write-Utf8NoBom .\review\kimodo-policy-evidence.json $PolicyEvidence
```

若已经有人审阅并批准 `KimodoPolicyMap v1`，可把原始两分量 heading 映射为可复核 yaw evidence：

```powershell
$HeadingEvidence = (& python -m autospine_workbench compile-heading-evidence `
  --policy-map .\review\kimodo-policy-map.json `
  --motion-sha256 $P7Motion `
  --motion-bundle-sha256 $P7Bundle `
  --projected-motion-sha256 $P8Motion `
  --projected-bundle-sha256 $P8Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "heading evidence compile failed" }
Write-Utf8NoBom .\review\heading-evidence.json $HeadingEvidence
```

Heading 在当前 P9 仍是 evidence-only：它不会写入 root rotation、角色翻面、scale 或 Spine timeline。P8 的 foreshortening/scale probe 也仍是 evidence-only。

## 4. 生成 foot-lock 与 depth-order candidates

脚锁候选把 P8 contact schedule 与精确 P5 FK 端点组合起来。阈值是审查策略的一部分，不是自动批准：

```powershell
$FootEnvelope = (& python -m autospine_workbench probe-foot-lock $Project `
  --projected-motion-sha256 $P8Motion `
  --projected-bundle-sha256 $P8Bundle `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --max-correction-reference-ratio 0.25 `
  --max-residual-px 8 `
  --state-root $StateRoot) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "foot-lock probe failed" }
Write-Utf8NoBom .\review\foot-lock-candidates.envelope.json $FootEnvelope
$FootEnvelopeObject = $FootEnvelope | ConvertFrom-Json
$FootCandidatesSha = [string]$FootEnvelopeObject.report_sha256
$FootCandidates = Read-CanonicalCliReport `
  .\review\foot-lock-candidates.envelope.json
Write-Utf8NoBom .\review\foot-lock-candidates.json $FootCandidates
```

Depth-order 候选还需要一份人工批准的 slot pair policy。它只比较 policy 明确列出的 slot 对，不把骨骼深度冒充 raster 遮挡真值：

```powershell
$DepthEnvelope = (& python -m autospine_workbench probe-depth-order $Project `
  --policy .\review\depth-pair-policy.json `
  --projected-motion-sha256 $P8Motion `
  --projected-bundle-sha256 $P8Bundle `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --state-root $StateRoot) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "depth-order probe failed" }
Write-Utf8NoBom .\review\depth-order-candidates.envelope.json $DepthEnvelope
$DepthEnvelopeObject = $DepthEnvelope | ConvertFrom-Json
$DepthCandidatesSha = [string]$DepthEnvelopeObject.report_sha256
$DepthCandidates = Read-CanonicalCliReport `
  .\review\depth-order-candidates.envelope.json
Write-Utf8NoBom .\review\depth-order-candidates.json $DepthCandidates
```

检查每个 foot sample 的 support/state/correction/residual，并查看每个 depth event 的证据窗口、滞回状态与 proposed front slot。`$FootCandidatesSha`、`$DepthCandidatesSha` 必须是各自 envelope 中的完整小写 SHA；复核台可直接加载两个 `.envelope.json` 并暂填它们，随后仍会由 Python 对内嵌 report 重算。默认 envelope 可能包含本机输入路径，只能作为本地临时文件，不要提交或对外传递；两个不带 `.envelope` 的 path-free canonical report 才用于后续 CLI 和 handoff。`rejected_limit` 或 `rejected_conflict` 的 foot 候选不能直接 `accept`；需要 `adjust`、`reject` 或 `unobservable`。

### 使用两步人工复核台

打开 [P9 Motion Policy 两步人工复核台](http://127.0.0.1:8765/motion-policy-review.html) 后按以下顺序操作：

1. 加载 `autospine-depth-pair-policy-proposal` 草案。页面会完整显示 pair、slot/role、setup front、滞回参数、exact P8/P5/P3 地址和草案限制；只有勾选明确人工批准后，才会把草案投影为严格正式 policy。页面会丢弃草案专用 `proposal` 字段，固定 `review` 为 `approved/human`，并只序列化一次；这份同一文本先作为 `policy_json` 通过 Python `policy_identity` preflight，成功后才原样下载为 `depth-pair-policy.json`。页面不会预选或自动批准。
2. 若加载的是既有正式 policy，页面会把它的 `File.text()` 原文作为 `policy_json` 发送到同一 loopback 服务，不先经过 JavaScript parse/stringify；因此 `1.0`、负零、非 ASCII 键和对象顺序不会在 Python 读取前被浏览器改写。若正式 policy 来自第 1 步，则 preflight 与下载使用第 1 步唯一一次序列化所得的同一文本。只有返回 `status=passed` 且 `identities.policy_sha256` 是完整小写 SHA-256 时，页面才显示这份 **Python canonical identity**。把该值显式复制到“已批准 policy SHA-256”输入框；页面不会从草案或 candidate 替你填写。
3. 用下载的正式 policy 运行 `probe-depth-order`。重新进入或继续当前页面，加载正式 policy 与上一步保存的 Foot/Depth `.envelope.json`；页面会暂填 envelope 的完整小写 `report_sha256`，点击校验后仍由 Python 重算。若改用 standalone report，则必须自行填写同一次默认 CLI envelope 中的 SHA；`--document-only` 输出本身不携带 SHA，不能凭文件名或相邻结果猜测。
4. 点击加载候选时，页面把 `policy_json`、`foot_candidates_json`、`depth_candidates_json` 三份原文和三份声明 SHA 发送到 Python `candidate_inventory` preflight。服务端 inner strict decoder 会解开受支持的 CLI envelope，重新验证完整 standalone 合同并重算 report SHA；envelope 自带的 `report_sha256`、请求中的 declared SHA 与重算值必须三者一致。随后服务检查 project/clip、tick schedule、P8/P5/P3 source chain，以及 policy 与 Depth candidates 的内嵌 policy SHA、hysteresis、pair 顺序、slot/role 和 setup front。只有响应 identity 逐项等于当前输入快照、inventory 计数一致、Python 候选 ID 清单摘要与浏览器待展示清单摘要一致且 `status=passed` 时，页面才显示候选。浏览器生成的 candidate ID 只是供人工表单使用；Python 摘要负责阻止同计数但不同 ID 的清单误解锁，最终合同权威仍是 CLI exact 编译。
5. 先在“视觉证据”查看全片 Correction X/Y、maximum residual 与 correction/reference 上限利用曲线。点击重点窗口或拖动帧滑杆，可在角色 setup 合成图上比较当前足点、候选校正后足点和目标锚点；同一帧的完整数值仍在表格中提供。重点窗口来自接触/状态边界、极值、p95、过零和校正跳变，只负责排序，不是通过阈值，也不会生成决定。
6. 在“批量草稿”显式选择一个或多个连续证据段，再选择 `accept`、`reject` 或 `unobservable` 并填写 reason code。页面先冻结并显示将覆盖的精确 candidate ID 数量；操作者确认后才写入内存草稿。覆盖已有草稿需要第二次确认，最近一次批量填写可以撤销。页面不会预选证据段、action 或 reason，也不会提供批量 `adjust`；需要调整 X/Y 或 Depth front slot 的候选必须在“逐项例外与完整数字”中处理。
7. `rejected_limit` / `rejected_conflict` foot 项不能 accept。Foot adjust 要人工填写最终 X/Y；空白或只有空格的数字会被拒绝，不会按零处理。Depth adjust 必须从当前 pair 的两个 slot 里选择最终 front。Root release 只能在报告列出的 unconstrained ticks 上显式启用；revision 和 loop reset 也不预填。只有全部精确候选都有有效决定、全局字段有效且勾选最终人工确认后，页面才下载严格四字段的 `motion-policy-review-input.json`。批量草稿在下载时仍逐 candidate 展开，不改变 CLI 合同。随后仍必须运行 `compile-motion-policy-decision`；preflight 和浏览器表单都不是 Python CLI exact 编译/发布链的替代品。加载文件或 preflight 期间若任一文件、声明 SHA 或 generation 发生变化，旧异步结果和批量预览都会失效，必须基于当前快照重新校验。

页面会自动使用以下 zero-write HTTP 合同；通常不需要手工调用：

| `operation` | 请求中的 operation 专属字段 | `passed` 响应 |
| --- | --- | --- |
| `policy_identity` | `policy_json` 原文字符串 | `identities` 只含 Python `policy_sha256`，不含 inventory |
| `candidate_inventory` | `policy_json`、`foot_candidates_json`、`depth_candidates_json` 原文字符串，以及 `declared` | `identities` 含 policy/foot/depth 三 SHA；`inventory` 恰含四项计数与 `candidate_ids_sha256`，后者是 Python 排序后的完整 candidate ID 字符串清单之 canonical JSON SHA-256 |

两类请求的 `format` 都是 `autospine-motion-policy-preflight-request`，`format_version=1`。`declared` 必须恰含 `policy_sha256`、`foot_candidates_sha256`、`depth_candidates_sha256`。成功响应固定为 `autospine-motion-policy-preflight-result` v1，并携带 `status=passed`、`operation`、`project_id`、`clip_id` 与上述身份；它不是可持久化 P9 工件。

`POST /api/motion-policy/preflight` 只接受 loopback authority、精确同源 `Origin`、`Content-Type: application/json` 和 `X-Autospine-Intent: motion-policy-preflight-v1`；若存在 `Sec-Fetch-Site`，只能是 `same-origin` 或 `none`。外层请求总上限为 48 MiB；内层 policy 原文限 1 MiB，foot/depth 原文各限 16 MiB。该入口零写入，不读取或返回本地路径，不创建 revision，不保存人工决定，也不发布或批准任何状态。浏览器只负责本地文件读取、人工表单、candidate ID 展示和 generation/snapshot guard；Python preflight 负责进入表单前的 canonical identity 与完整合同交叉验证，最终 CLI 仍会再次拒绝不匹配的 policy/candidate SHA。不要编辑 candidate JSON 或手工改写 SHA 来绕过绑定。

## 5. 记录人工决定

不要修改 candidate JSON。新建 `motion-policy-review-input.json`，并满足以下规则：

- `review` 必须是 `approved`、`human`，且 revision 至少为 1；
- `decisions` 必须按 `candidate_id` 排序，并穷尽两份 candidate 文档中的每个候选；
- `accept`、`reject`、`unobservable` 的 `payload` 为 `null`；
- foot `adjust` 使用 `final_correction_xy_px`，depth `adjust` 使用 pair 内的 `final_front_slot`；
- `root_release_keys` 只能引用 unconstrained foot tick；未列出的 tick 使用零 correction；
- loop clip 若以非 setup draw order 结束，只有明确批准 reset 才能编译。

用 UTF-8 no-BOM 方法保存 review input 后，生成与 exact candidates 绑定的决定文档：

```powershell
$Decision = (& python -m autospine_workbench compile-motion-policy-decision `
  --foot-candidates .\review\foot-lock-candidates.json `
  --depth-candidates .\review\depth-order-candidates.json `
  --review-input .\review\motion-policy-review-input.json `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "motion policy decision compile failed" }
Write-Utf8NoBom .\review\motion-policy-decision.json $Decision
```

Candidate 算法或上游地址变化后必须重新审查；旧决定的 SHA 绑定会变 stale，不会静默套用。

## 6. 编译 reviewed policy

Reviewed policy 把人工决定投影为完整 root-correction schedule 和 full back-to-front slot permutations：

```powershell
$ReviewedPolicy = (& python -m autospine_workbench compile-reviewed-motion-policy $Project `
  --foot-candidates .\review\foot-lock-candidates.json `
  --depth-candidates .\review\depth-order-candidates.json `
  --decision .\review\motion-policy-decision.json `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "reviewed policy compile failed" }
Write-Utf8NoBom .\review\reviewed-motion-policy.json $ReviewedPolicy
```

这一步仍是版本中立策略，不是 Spine 文件，也不会生成 attachment switch、deform 或 runtime IK。

## 7. 预览 MotionInstance v2 与 Spine 4.2 v2

先生成只读 MotionInstance v2 handoff，检查 root translation、完整 draw-order key 和 loop closure：

```powershell
$MotionV2 = (& python -m autospine_workbench compile-motion-instance-v2 $Project `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --reviewed-policy .\review\reviewed-motion-policy.json `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "MotionInstance v2 compile failed" }
Write-Utf8NoBom .\review\motion-instance-v2.preview.json $MotionV2
```

再生成 Spine 4.2 adapter v2 的只读预览报告：

```powershell
$SpinePreview = (& python -m autospine_workbench export-spine42-v2 $Project `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --reviewed-policy .\review\reviewed-motion-policy.json `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Spine 4.2 v2 preview failed" }
Write-Utf8NoBom .\review\spine42-v2.preview.json $SpinePreview
```

预览中的 loader-isomorphic draw-order audit 重放 Spine 4.2 loader 的 offset 解释，用于发现 adapter 排列错误。它不是官方 runtime 加载结果，也不是 raster truth、截图 golden 或美术验收。

## 8. 发布并复验 reviewed bundle

发布命令不会读取预览出来的 MotionInstance v2 文件；它会从 exact P5 与 reviewed policy 自己重编译 v2，再由 Store 完整重编 policy/v2。固定六文件清单为：

```text
foot-lock-candidates.json
depth-order-candidates.json
motion-policy-decision.json
reviewed-motion-policy.json
motion-instance-v2.json
run-manifest.json
```

发布 canonical report：

```powershell
$Publication = (& python -m autospine_workbench publish-reviewed-motion-bundle $Project `
  --foot-candidates .\review\foot-lock-candidates.json `
  --depth-candidates .\review\depth-order-candidates.json `
  --decision .\review\motion-policy-decision.json `
  --reviewed-policy .\review\reviewed-motion-policy.json `
  --p3-rig-sha256 $P3Rig `
  --p3-bundle-sha256 $P3Bundle `
  --motion-instance-sha256 $P5Instance `
  --motion-retarget-bundle-sha256 $P5Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "reviewed-motion bundle publish failed" }
Write-Utf8NoBom .\review\reviewed-motion-publication.json $Publication
```

从 report 的 `address` 读取 P9 v2/bundle SHA，然后只读重放：

```powershell
$Published = $Publication | ConvertFrom-Json
$P9V2 = $Published.address.motion_instance_v2_sha256
$P9Bundle = $Published.address.bundle_sha256

$Verification = (& python -m autospine_workbench verify-reviewed-motion-bundle $Project `
  --motion-instance-v2-sha256 $P9V2 `
  --reviewed-motion-bundle-sha256 $P9Bundle `
  --state-root $StateRoot `
  --document-only) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "reviewed-motion bundle verify failed" }
Write-Utf8NoBom .\review\reviewed-motion-verification.json $Verification
```

物理地址是 `builds/<project>/reviewed-motion-instances/<motion-instance-v2-sha256>/<bundle-sha256>/`。reader 只接受这三个显式地址分量，逐文件单次读取固定清单，并从 run 中解析 exact P3/P5 后完整重编；不存在 `latest`、目录扫描或替代 bundle 回退。

## 9. 正确认识每类工件

| 类型 | 作用 | 是否有应用权限 |
| --- | --- | --- |
| Evidence | P7/P8 数组、投影、heading、contact 与深度事实 | 否 |
| Candidate | foot correction 或 slot-front 的算法提议 | 否 |
| Decision | 人工对每个 candidate 的 accept/adjust/reject/unobservable 选择 | 是，但尚未形成 runtime timeline |
| Reviewed policy | 从 exact decision 编译出的 root/draw-order timeline | 是，版本中立 |
| Reviewed bundle | evidence-derived candidates、decision、policy、MotionInstance v2 与 run 的不可变复验快照 | 不新增权限，只封装已批准结果 |

P9 通过新增 MotionInstance v2 与 Spine adapter v2 承载动态策略；MotionInstance v1、P5/P6 v1 bundle 和既有 Spine adapter v1 的 canonical hash 保持不变。不要用 v2 输出覆盖或伪装 v1 地址。

## 10. 当前验收边界

结构闭环已经覆盖 exact address、候选/决定分离、root correction、draw order、MotionInstance v2、Spine v2 preview 和六文件 bundle 重放。仍未关闭的门禁包括：

- `wave-left-v1` 已有已复验的 P7/P8、A/B P5、共享 policy evidence、正式 depth policy 以及两组 foot/depth candidates；两组 candidate inventory preflight 均通过，但每个项目仍缺 119 个 Foot 人工决定和 P9 reviewed asset fixture；
- 动态 draw order/foot correction 在官方 Spine runtime 中的固定截图回归；
- heading 或 scale timeline 的人工决定与 runtime 消费合同；
- attachment switch、deform、runtime IK 和物理。

出现 stale cross-chain、重复 JSON key、NaN/Infinity、大小写别名、symlink/junction、额外文件或 byte limit 错误时，不要编辑内容寻址目录。修复源文档，在干净地址重新运行本指南；verifier 不会搜索“看起来可用”的旧产物。
