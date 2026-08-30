# 审计两份真实样本的 Spine 4.2 v3 就绪状态

本文是一个只读 How-to。它帮助操作者从两份真实 See-through 项目的精确 Layer Manifest/P3 地址开始，逐项确认 P9、接缝复核、MotionInstance v3、Spine 4.2 v3、官方 Runtime capture 和 sampled raster 人工决定是否已经具备。readiness v1 已冻结，其第八项仍固定为 missing；已交付的 P10.7c setup golden 对照使用独立命令和合同。审计会运行只读 pure replay compiler/validator 来复验请求中明确声明的工件；它不会扫描 `latest` 或 current review head，不会替你运行外部阶段、官方 Runtime、发布或写入，也不会授予发布权。

## 运行现有真实样本基线

在项目根目录打开 PowerShell，并设置源码路径：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench audit-body-sway-spine42-v3-readiness `
  --manifest .\examples\p10-spine42-v3-readiness\real-see-through.request.json `
  --state-root .\workspace `
  --document-only
```

去掉 `--document-only` 时，stdout 会增加 `ok`、`mode` 和请求的 domain-separated `request_sha256` 外层包装；审计内容位于 `readiness`。保留该参数时，stdout 只包含 canonical readiness report。

有效请求即使仍有 blocker，命令也以退出码 `0` 返回，并通过业务字段 `status=blocked_prerequisites_or_review` 表示未就绪。请求文件读取失败、不是 strict canonical JSON、请求合同无效或审计自身的内部合同失败时，命令才以退出码 `2` 返回固定脱敏错误。格式合法但声明的 artifact 缺失、损坏或不可重放时，相应 checkpoint 会报告 `source_mismatch`，业务状态保持 blocked，命令仍退出 `0`；不要把退出码 `0` 当成真实样本已验收。

## 请求文件合同

请求和报告的 Draft 2020-12 结构分别见 [`spine42-v3-readiness-request-v1.schema.json`](../schemas/spine42-v3-readiness-request-v1.schema.json) 与 [`spine42-v3-readiness-report-v1.schema.json`](../schemas/spine42-v3-readiness-report-v1.schema.json)。Schema 只表达公开结构；canonical bytes、domain/self-hash、依赖闭合、精确地址重放和权限边界仍由 Python 语义 validator 负责。

示例文件 [real-see-through.request.json](../examples/p10-spine42-v3-readiness/real-see-through.request.json) 已固定当前两份真实项目的已审计 Layer Manifest/P3 地址：

| 项目 | Layer Manifest SHA-256 | P3 rig SHA-256 | P3 bundle SHA-256 |
| --- | --- | --- | --- |
| `seethrough_output` | `ed1e2458cd22b75c51f13656feb86ecf55682508b62413c980c3035743e8faa7` | `40f96ade2f38f93caa7610b40f02ed9b30b8782396cee0e80499724a0450e327` | `7754406b1f6834a6b5c8fedfcd4743bd294d8cc568d7ff6413673cada3d79a1d` |
| `seethrough_output_5` | `45b5f2a90c55866a17c83a01e7ae46e9bd2bed51b4a918d60690a574f14bff51` | `897761e75bdd7e1cd3018cdab0f793f2d3ba637d88e01ce907beb179cfe0cd77` | `21f4707eaf023d664ae8cea8b785fd8a5197187f846d6db10b9c3ef34d7c6576` |

2026-08-30，两个项目的真实 P9 reviewed-motion bundle 已分别通过 exact reader 重放：

| 项目 | P9 MotionInstance v2 SHA-256 | P9 reviewed-motion bundle SHA-256 |
| --- | --- | --- |
| `seethrough_output` | `3c7bb6efcdb91d3ad3c1984ae19159a2ceb2b7aa8f0b88fc405d63956bd59823` | `b347c56a217b4cc844da3f115f100ae8b1352389207f357824ba322bdb46649c` |
| `seethrough_output_5` | `706225aca7359f46daf0c318e186252b36c44650cd1539eb667e40f50e715754` | `39076c3589b046268b01c6c85bb0f7393403d2d0973ae417ef78271b649d0e96` |

同日，样本 A 的 P10.5b revision 1 已由操作者确认，P10.5c 静态接缝集已发布并通过 exact replay：

| 项目 | P10.5c reviewed-set SHA-256 | P10.5c bundle SHA-256 |
| --- | --- | --- |
| `seethrough_output` | `47656c2510e98b7598937a2c3315cd8f6e05274162160cf11a07cc167ed0e4d9` | `fb8886cf1dcbff5d0ccb1fc36c6a087d93ad4e87678169dbad435e9e30e1adbe` |

仓库自带的示例文件是冻结的 baseline，仍故意把以下五组下游地址和 raster 人工决定全部设为 `null`。因此直接运行本节开头的示例命令仍会报告 P9 地址未声明；这不再代表当前工作区没有真实 P9。要审计最新状态，应以示例为结构起点，使用 canonical builder 生成一份新的请求，并把上表双 SHA 填入对应项目的 `reviewed_motion_address`：

- `reviewed_motion_address`：P9 的 `motion_instance_v2_sha256` 与 `bundle_sha256`；
- `reviewed_seam_anchor_set_address`：P10.5c 的 `reviewed_seam_anchor_set_sha256` 与 `bundle_sha256`；
- `motion_instance_v3_address`：P10.6b 的 `motion_instance_v3_sha256` 与 `bundle_sha256`；
- `spine42_v3_address`：P10.7a 的 `skeleton_json_sha256` 与 `bundle_sha256`；
- `runtime_capture_address`：P10.7b 的 `spine42_v3_bundle_sha256` 与 `capture_bundle_sha256`；
- `raster_review_decision`：与精确 capture 绑定、覆盖全部 case/attachment 的完整人工决定。

随着真实链交付，按依赖顺序把精确地址写入请求；不得跳级填入下游地址，也不得用测试 fixture 的 SHA 代替真实产物。`runtime_capture_address.spine42_v3_bundle_sha256` 必须等于同一行 `spine42_v3_address.bundle_sha256`，raster decision 的 source 也必须与同一 Spine/capture 地址闭合。

请求文件必须是 canonical UTF-8 JSON：字段集合精确、对象键按字典序、样本按唯一 `project_id` 升序、无缩进、无 BOM、无多余空白，并且文件末尾不能有换行。示例文件本身就是可直接读取的单行 canonical bytes；手工重新格式化或普通编辑器自动补末尾换行都会使解析 fail closed。程序化生成时应调用 `canonical_spine42_v3_readiness_request_bytes(...)`，而不是自行猜测序列化格式。

## 读取报告

每个样本固定包含八个 checkpoint：

| Checkpoint | 证明范围 | 常见下一步 |
| --- | --- | --- |
| `p3_seam_source` | 精确 Manifest/P3 能重放静态接缝候选 | 修复精确 P3 来源地址 |
| `p9_reviewed_motion` | 精确真实 Kimodo reviewed-motion bundle 可重放且绑定当前 P3 | 填入并复验当前真实 P9 双 SHA |
| `p10_5_reviewed_seam_anchor_set` | 六关系人工复核与 P10.5c bundle 已闭合 | 完成人审，或修复不可观测语义/分层 |
| `p10_6b_motion_instance_v3` | 精确 P10.6b bundle 可重放并绑定 P9/seam set | 完成 P10.0–P10.6b |
| `p10_7a_spine42_v3` | 精确五文件 Spine 4.2 v3 bundle 可重放 | 编译并填写 P10.7a 双 SHA |
| `p10_7b_runtime_capture` | 精确官方 Runtime capture 可重放并绑定 P10.7a | 在已授权环境执行 capture |
| `p10_7b_raster_review` | sampled 指标与完整人工决定闭合 | 逐 case、逐 attachment 复核 |
| `p6_setup_regression` | readiness v1 中保留的 P6 setup 对照缺口 | 使用独立 P10.7c setup regression 命令 |

`verified` 只表示该 checkpoint 的精确地址经过只读 pure replay 和合同校验；`prerequisite_missing`、`review_blocked`、`metrics_rejected` 和 `source_mismatch` 都会阻止该样本进入下一步。只有前七项均为 `verified` 时，样本状态才会成为 `ready_for_p6_setup_comparison`。readiness v1 的 Schema、哈希与 checkpoint 语义已经冻结，因此第八项仍始终报告 `p6_setup_golden_comparison_not_declared`。P10.7c 已通过独立 `compare-body-sway-spine42-v3-setup-golden` 命令交付，不能把它的结果回填或伪装成 readiness v1 的第八项；操作见[对照 P10.7c Spine 4.2 v3 Setup Golden](how-to-compare-spine42-v3-setup-golden.md)。

地址为 `null` 时，审计只报告“请求未声明该精确地址”，不会搜索 `latest` 或 current review head 来判断工件是否已存在。例如，冻结请求中 A 的 `reviewed_seam_anchor_set_address=null` 仍会得到 `reviewed_seam_anchor_set_address_not_declared`；该 reason code 不能证明 review head 为空，也不能推翻上表已经 exact replay 的 P10.5c。使用 canonical builder 生成新请求并写入该双 SHA 后，审计才会重放这项真实凭据。

## 当前两份真实样本结论

以下结论区分“真实工件已存在”与“冻结 baseline 是否声明地址”。审计只重放请求中显式声明的地址，不会自动发现工作区内容：

- A/B 的真实 P9 双 SHA 已由 `verify-reviewed-motion-bundle` 复验，均返回 `verification.status=passed` 与 `replayed_from_exact_upstreams=true`。冻结 baseline 仍为 `null`，所以直接运行它时 `p9_reviewed_motion` 仍报告 `exact_reviewed_motion_address_not_declared`；只有生成并审计显式填入上表地址的新请求，才能让 readiness checkpoint 记录这项事实。
- `seethrough_output` 的 P10.5b revision 1 与 P10.5c exact bundle 已闭合。冻结 baseline 仍未声明该双 SHA，所以直接运行它时 seam checkpoint 仍报告 `reviewed_seam_anchor_set_address_not_declared`；生成新请求后才能审计已存在的静态凭据。A 当前真实动作顺序是 P10.0/P10.1 → P10.2 → P10.3a–P10.3c → P10.4a → P10.4b1 → P10.4b2 → P10.5d，不能从静态 set 直接跳级。
- `seethrough_output_5` 的 P9 同样已经通过，但四条腿/脚关系不可观测：左右 `pelvis_leg` 缺 child role，左右 `leg_foot` 缺 parent role。P10.5c 的完整六关系合同不能把这些行自动批准；需要回到上游修复语义/分层并重新生成受内容地址约束的 Manifest/P3，或者另立、版本化并单独验收 partial seam 合同。
- 官方 Spine 4.2 Runtime/Capture 基础设施当前已存在，因此不需要把“下载 Runtime”作为第一步；A 更早的 blocker 是 P10.1–P10.5d 动作域，B 更早的 blocker 是完整静态 seam 合同。审计不会主动发现或调用该 Runtime。
- P10.7c 独立比较命令已经存在，但当前 A/B 都没有满足其请求合同所需的真实 P10.7a/capture 地址；这项能力交付不能被表述为真实双样本已通过。

建议先生成一份显式包含上述 P9 地址与 A 的 P10.5c 双 SHA 的新 canonical readiness 请求。项目 A 随后通过普通身体摆动入口显式确认 P10.1，并依次完成 P10.2、P10.3a–P10.3c、P10.4a、P10.4b1、P10.4b2 与 P10.5d；项目 B 先完成“上游修复”或“版本化 partial seam 合同”的方案评审。只有各自精确前置实际闭合后，才继续填写更下游地址并重新运行审计。

## 审计不会做什么

该命令是 exact-address、zero-write preflight：

- 不扫描或选择 `latest`，不猜测缺失地址；
- 不扫描 current review head，也不以地址为 `null` 推断 head 不存在；
- 不运行 P7–P10 外部阶段、官方 Runtime、capture 或人工作业；只读 pure replay compiler/validator 仍会在内存中重建并校验显式地址；
- 不生成或提交 seam/raster 人工决定；
- 不修改 state root，不发布 bundle；
- 不证明未采样时间、连续 Runtime raster 安全或永久 current-head authority；
- 不授予 publish、release 或可发布 Spine timeline 权限；
- 不执行 P10.7c setup golden comparison；readiness v1 的第八项保持 missing，比较必须通过[独立 P10.7c 流程](how-to-compare-spine42-v3-setup-golden.md)完成。

因此，保存 readiness report 只能作为“这次显式地址预检的结果”，不能作为发布签字或自动验收记录。
