# 复核并发布 Kimodo 动作策略

本指南同时面向普通操作者和需要独立复验 exact CLI 链的开发者。普通操作者只需选择项目、查看动作、处理异常并执行一次最终人工确认；工作台会从本地 review package 自动加载正式 policy、Foot/Depth candidates，重算 SHA-256，运行交叉预检，再由本机 Python 编译 decision 与 reviewed policy、原子发布 P9 reviewed-motion bundle，并按返回的精确地址立即复验。下载的 review input 只是备份和审计副本，不再是普通流程继续发布的必需交接文件。开发者仍可使用下文 CLI 独立重放同一过程。

本流程不会自动批准 heading、scale、附件切换、Depth 事件、`rejected_*`、证据缺失、非有限值或超安全阈值项。正式 handoff 文档使用 `--document-only`；Foot/Depth 候选同时保留默认 CLI envelope，因为其中的 `report_sha256` 是复核台绑定同一次结果所必需的身份。

## 普通操作者：默认自动流程

启动工作台并打开 [Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html)。建议按以下顺序完成：

1. 在“项目 / 动作”中确认目标。存在推荐项时页面会自动选择并加载；切换项目时始终按该选项对应的 exact package 读取，不会把 A/B 文件混用。
2. 等待“身份与预检通过”。服务端会读取 package 中固定文件，重算 policy、Foot、Depth 与 candidate inventory 身份，再由页面执行同一 candidate preflight。普通用户不需要选择 JSON 文件或填写 SHA-256。
3. 拖动时间轴查看角色足点、校正曲线和重点窗口。启用“拖动时采用安全建议”后，一次拖动会把经过的、尚未决定且符合当前安全规则的 Foot candidates 作为一组可撤销的辅助决定；也可点击“一键采用全部安全建议”。重点窗口只是接触边界、极值、p95、过零或跳变的视觉导航，本身既不批准也不排除候选。
4. 查看“需要处理的异常”。自动采用必须同时满足：类型为 Foot、`state=candidate`、observations 完整且全部数值有限、correction ratio 与 residual 均不超过各自合同上限的 80%。Depth、`rejected_limit`、`rejected_conflict`、缺证、非有限值和超阈值项不会被安全结果覆盖；`adjust` 始终需要明确输入最终值。
5. 检查自动覆盖数量和异常数量，必要时撤销最近一次辅助操作。确认结果后执行页面上的最终采用。这一次明确动作把辅助结果采纳为 v1 的 `human` review input，并提交给与当前 exact package 绑定的本地 adoption 入口。
6. 等待成功或幂等复用回执，再点击“进入接缝复核”。链接只携带当前 exact `package_id`；服务端会重放 package 与共享 P3 来源、复验 P3 bundle，并自动加载 Seam candidate。普通用户无需下载文件、记录双 SHA 或抄写 P3/P5 地址。

这里的“自动”覆盖文件选择、SHA 绑定、低风险 Foot 重复操作，以及确认后的本地编译、内容寻址发布和 exact verify。Motion Policy Decision v1 的合同仍是 **human adoption**：页面不会零点击发布，也不会授予 seam、官方 Runtime 或 release authority。选择项目、预检通过、拖完时间轴或候选达到 100% 覆盖，都不等于最终人工采纳；只有最后一次明确确认才允许调用 adoption 入口。

如需审计外部文件、处理未登记 package 或排查身份错误，再展开“专业模式：手动导入 JSON 与 SHA”。专业模式不是普通流程的必经步骤。

## 1. 开发者：固定输入地址

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

### 专业模式：手动导入三文件与 SHA

默认项目选择器读取本地 `workspace/reviews/<motion>/<project>/` 中已经登记的 exact package，并自动完成正式 policy、Foot report、Depth report 与三份 SHA 的装载。只有 package 未登记、需要复核外部副本或排查身份问题时，才展开专业模式：

1. 加载 `autospine-depth-pair-policy-proposal` 草案时，页面会完整显示 pair、slot/role、setup front、滞回参数、exact P8/P5/P3 地址和草案限制。只有明确批准后，才会把草案投影为严格正式 policy；页面丢弃草案专用 `proposal` 字段，固定 `review` 为 `approved/human`，并只序列化一次。正式 policy 先通过 Python `policy_identity` preflight，再原样下载。
2. 加载既有正式 policy 时，页面把 `File.text()` 原文作为 `policy_json` 送入同一 loopback 服务，不先经过 JavaScript parse/stringify。成功后页面显示并自动填入 Python canonical policy SHA；不要从文件名或相邻结果猜测身份。
3. 加载 Foot/Depth `.envelope.json` 时，页面可读取 envelope 的 `report_sha256`，但仍由 Python 对内嵌 standalone report 重算。若使用 standalone report，须提供生成它的同一次 CLI envelope 中的 SHA；`--document-only` 输出本身不携带 SHA。
4. 点击校验后，页面把三份原文和声明 SHA 送入 `candidate_inventory` preflight。服务端重验完整 standalone 合同，并检查 project/clip、tick schedule、P8/P5/P3 source chain、Depth policy 绑定与候选 ID inventory。全部身份和摘要一致后才显示候选。
5. 专业模式与默认模式共享同一视觉证据、辅助决定、逐项异常和最终采用步骤。手工导入不会降低门禁，也不会允许用编辑 JSON 或手改 SHA 绕过绑定。

`rejected_limit` / `rejected_conflict` Foot 项不能 accept。Foot adjust 要明确填写最终 X/Y；Depth adjust 必须从当前 pair 的两个 slot 里选择最终 front。Root release 只能引用报告列出的 unconstrained ticks。辅助采用只写入当前页面的、带来源标记且可撤销的草稿，不覆盖已有人工或批量决定；最终 adoption 要求 100% 精确覆盖、全局字段有效和一次明确人工采纳。加载 package、切换项目或输入身份变化会使旧异步结果和草稿预览失效，必须基于当前快照重新校验。

默认项目流程先调用两个只读接口；最终人工确认后再调用一个本地写入口。通常不需要手工调用：

| 资源 | 作用 |
| --- | --- |
| `GET /api/motion-policy/review-packages` | 列出本地 exact packages，并返回确定性的推荐 package ID |
| `GET /api/motion-policy/review-packages/{package_id}` | 按完整 ID 读取并重验该 package；响应不含本地路径 |
| `POST /api/motion-policy/review-packages/{package_id}/adoptions` | 接收与当前页面快照对应的严格四字段 human review input；重新读取 exact package，编译 decision/reviewed policy，原子发布 P9 bundle，按双 SHA 精确复验并返回 path-free 结果 |

推荐 ID 只是默认界面选择，不是批准状态。完整 package ID 绑定项目、动作、clip、policy/Foot/Depth 身份与 candidate inventory；任一内容变化都产生不同 ID，页面不会按 mtime 或 `latest` 回退。

Adoption 正文是严格 wrapper：`format=autospine-motion-policy-adoption-request`、`format_version=1`、`intent=motion-policy-adoption-v1`、与 URL 完全相同的 `package_id`，以及只含 `review`、`decisions`、`root_release_keys`、`draw_order_loop_reset` 的 `review_input`。多余字段、package ID 不一致或不完整决定都会被拒绝。成功回执固定为 `autospine-motion-policy-adoption-receipt` v1；只有 `status=passed`、`verification.replayed_from_exact_upstreams=true`，且 `address` 中同时包含 `project_id`、`motion_instance_v2_sha256` 与 `bundle_sha256` 时，页面才显示发布完成。

身份与候选预检使用以下 zero-write POST 合同：

| `operation` | 请求中的 operation 专属字段 | `passed` 响应 |
| --- | --- | --- |
| `policy_identity` | `policy_json` 原文字符串 | `identities` 只含 Python `policy_sha256`，不含 inventory |
| `candidate_inventory` | `policy_json`、`foot_candidates_json`、`depth_candidates_json` 原文字符串，以及 `declared` | `identities` 含 policy/foot/depth 三 SHA；`inventory` 恰含四项计数与 `candidate_ids_sha256`，后者是 Python 排序后的完整 candidate ID 字符串清单之 canonical JSON SHA-256 |

两类请求的 `format` 都是 `autospine-motion-policy-preflight-request`，`format_version=1`。`declared` 必须恰含 `policy_sha256`、`foot_candidates_sha256`、`depth_candidates_sha256`。成功响应固定为 `autospine-motion-policy-preflight-result` v1，并携带 `status=passed`、`operation`、`project_id`、`clip_id` 与上述身份；它不是可持久化 P9 工件。

`POST /api/motion-policy/preflight` 只接受 loopback authority、精确同源 `Origin`、`Content-Type: application/json` 和 `X-Autospine-Intent: motion-policy-preflight-v1`；若存在 `Sec-Fetch-Site`，只能是 `same-origin` 或 `none`。外层请求总上限为 48 MiB；内层 policy 原文限 1 MiB，foot/depth 原文各限 16 MiB。该入口零写入，不读取或返回本地路径，不创建 revision，不保存人工决定，也不发布或批准任何状态。

最终采用入口要求 `X-Autospine-Intent: motion-policy-adoption-v1`，只接受 URL 中的完整 package ID 和正文中的严格 human review input。服务端不会信任浏览器缓存的 policy、候选、P3/P5 地址或声明 SHA，而是重新按 package ID 读取和验证固定证据，再调用与 CLI 相同的领域编译器、不可变 store 和 exact reader。相同 canonical 输入可以安全复用相同内容地址；package 已变化、决定未穷尽、身份交叉绑定失败或发布后无法精确复验时均 fail closed。成功响应只返回 path-free 身份、P9 双 SHA 与复验状态。回执的 Seam 链接只传 `package_id`，后端再次闭合 package→P3 exact 链，浏览器不会构造 Manifest/P3 SHA。P9 成功不会被提升为 seam、Runtime 或 release authority。CLI 仍会拒绝同样的不匹配输入，可用于独立专业复验。不要编辑 candidate JSON 或手工改写 SHA 来绕过绑定。

## 5. 专业复验路径：记录人工决定

普通流程已经在最终确认后完成本节到第 8 节，并把 review input 作为可选备份下载。只有需要审计备份、复验外部副本、排查身份问题或在无浏览器环境中重放时，才手工执行以下 CLI。

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

## 6. 专业复验路径：编译 reviewed policy

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

## 7. 专业复验路径：预览 MotionInstance v2 与 Spine 4.2 v2

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

## 8. 专业复验路径：发布并复验 reviewed bundle

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

普通流程的一次最终 human adoption 现在会闭合 exact address、候选/决定分离、root correction、draw order、MotionInstance v2、六文件 bundle 发布和 exact replay；CLI 保留为独立专业复验路径。P9 成功仍未关闭以下门禁：

- `wave-left-v1` 的两个项目已于 2026-08-30 分别完成人工 adoption，并通过 P9 exact replay；可进入下游的双 SHA 与完整上游身份集中记录在 [pilot handoff](pilots/kimodo-wave-left-v1.md)；
- A（`seethrough_output`）的下一步是静态 seam 人审、P10.5c reviewed set 与后续动态 seam 门禁；
- B（`seethrough_output_5`）的左右 pelvis-leg 与 leg-foot 四条关系受长裙/分层限制而不可观测；在修复上游资产/语义或建立版本化 partial 合同前，不能伪造完整下肢 seam 通过，也不能宣称通用腿部动画可用；
- 动态 draw order/foot correction 在官方 Spine runtime 中的固定截图回归；
- heading 或 scale timeline 的人工决定与 runtime 消费合同；
- attachment switch、deform、runtime IK 和物理。

出现 stale cross-chain、重复 JSON key、NaN/Infinity、大小写别名、symlink/junction、额外文件或 byte limit 错误时，不要编辑内容寻址目录。修复源文档，在干净地址重新运行本指南；verifier 不会搜索“看起来可用”的旧产物。
