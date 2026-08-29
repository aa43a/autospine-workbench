# 对照 P10.7c Spine 4.2 v3 Setup Golden

本文面向已经取得 P10.7a Spine bundle 与 P10.7b Runtime capture 精确地址的操作者。目标是把 capture 中唯一的 `setup + opaque_composite` 帧，与既有 P6 官方 Spine Runtime 批准图做零写入 RGBA 回归。命令不会启动 Runtime、扫描 `latest`/current head、修改批准图或写入 state；标准输出中的报告是临时、不可寻址的结果，不会自动成为后续 readiness 的证据。

## 1. 准备四组证据

每个项目需要：

- P3 RigIR 的 `p3_rig_sha256` 与不可变 bundle 的 `p3_bundle_sha256`；
- P6 setup-only 的 `skeleton_json_sha256` 与 `bundle_sha256`；
- P10.7a 的 `skeleton_json_sha256` 与 `bundle_sha256`；
- P10.7b capture 的 `spine42_v3_bundle_sha256` 与 `capture_bundle_sha256`；
- 批准的 P6 runtime case ID 与 PNG SHA-256。

仓库内两份既有 P6 基线为：

| 项目 | P3 rig / bundle | P6 setup skeleton / bundle | runtime case / PNG SHA-256 |
| --- | --- | --- | --- |
| `seethrough_output` | `40f96ade2f38f93caa7610b40f02ed9b30b8782396cee0e80499724a0450e327` / `7754406b1f6834a6b5c8fedfcd4743bd294d8cc568d7ff6413673cada3d79a1d` | `61caa6a00568400ee11416f9d45ffcab9d1584657ebf5339fca3d1b8d2c77aea` / `5740a5956434b792a35ad850cdc517d77a03242436b7cf21ce8ddfe25b6a7de3` | `a.setup` / `c4bf1d667096c6410719548240a050b94c64346b11549ec350ca47756cf01eab` |
| `seethrough_output_5` | `897761e75bdd7e1cd3018cdab0f793f2d3ba637d88e01ce907beb179cfe0cd77` / `21f4707eaf023d664ae8cea8b785fd8a5197187f846d6db10b9c3ef34d7c6576` | `f46662e4ab7c2e472f3441cd6c6884b75cc70c78142e994e6b01493a7a065aed` / `20a172bd26e19e5b119d74fbd39c6721377c85f2bd721038ce88d13733c85156` | `b.setup` / `d4ca9e6b852cccf09166d733c55e9148071e3d454e477e6ba9cd89aa4c746af9` |

批准合同是 [P6 导出地址合同](../tests/goldens/p6-spine42/real-exports.approved.json) 与 [P6 Runtime 截图合同](../tests/goldens/p6-spine42/runtime.approved.json)。当前文件 SHA-256 分别为：

```text
9dfee739ab25af26d8e77878bafd785c806d7a1d8dc0deb6f55662a6ecd4be22
e8d5045f66041542b6d10dc63a9b357751b16bb1e30a3174d30b65a9670b53bf
```

这两个批准合同 SHA 是操作者选择的信任根，不是命令自行发现或替操作者批准的内容。不要手工改批准合同或 PNG 来迁就新输出。批准文件变化时，必须走独立的重新批准流程，并显式更新请求中的文件 SHA。

比较算法、阈值解释、Runtime/capture 常量和 sample 哈希域还由冻结的 comparison profile 绑定。当前 profile SHA-256 为：

```text
98e12906fea7f5c9f194eac1af06deb402705392d5c5ed459b1c00878f9a92de
```

请求必须显式携带该值。维护者修改选择、像素或阈值语义时必须先更新冻结 profile；validator 会拒绝 profile 不匹配的旧请求，防止旧请求静默复用新算法。

## 2. 创建 strict canonical 请求

复制 [双样本请求模板](../examples/p10-spine42-v3-setup-regression/real-see-through.template.request.json) 为 `real-see-through.draft.json`。模板是带尾随 LF 的可读草稿，不是 canonical 请求。先确认根级 `comparison_profile_sha256` 和每条 sample 的显式 P3 rig/bundle 地址与本次证据链一致，再将每个项目中的三组全零地址替换为实际值：

- `spine42_v3_address.skeleton_json_sha256`；
- `spine42_v3_address.bundle_sha256`；
- `runtime_capture_address.capture_bundle_sha256`。

同一行的 `runtime_capture_address.spine42_v3_bundle_sha256` 必须等于 `spine42_v3_address.bundle_sha256`。若只验收一个项目，可删除另一条 sample，但保留数组按 `project_id` 升序。然后生成无 BOM、无尾随换行、key 顺序固定的 canonical 请求：

```powershell
python -B .\tools\canonicalize_spine42_v3_setup_regression_request.py `
  .\examples\p10-spine42-v3-setup-regression\real-see-through.draft.json `
  --output .\examples\p10-spine42-v3-setup-regression\real-see-through.request.json
```

不要直接把可读 draft 传给比较命令；canonicalizer 会同时检查字段、SHA、sample 顺序和 capture→P10.7a 地址闭合。

请求 Schema 是 [spine42-v3-setup-regression-request-v1.schema.json](../schemas/spine42-v3-setup-regression-request-v1.schema.json)。Schema 负责公开结构；Python validator 另外检查 canonical bytes、完整 SHA、排序和地址依赖。

## 3. 执行只读比较

在项目根目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -B -m autospine_workbench compare-body-sway-spine42-v3-setup-golden `
  --manifest .\examples\p10-spine42-v3-setup-regression\real-see-through.request.json `
  --p6-export-contract .\tests\goldens\p6-spine42\real-exports.approved.json `
  --runtime-golden-contract .\tests\goldens\p6-spine42\runtime.approved.json `
  --state-root .\workspace `
  --document-only
```

命令会依次证明：

1. 请求锁定的两个批准合同与磁盘字节 SHA 完全一致；
2. 请求显式声明的 P3 rig/bundle 与 P6 setup-only、P10.7a 三者相同；
3. 两代导出的 atlas/texture SHA 相同；P6 与 P10 skeleton SHA 不要求相同；
4. P10.7b capture 与 P10.7a bundle、run、重新生成的 capture plan 完全一致；
5. setup case 是 `animation=null`、`tick=0`，且只有一个不透明合成图；
6. Runtime 为 `@esotericsoftware/spine-player@4.2.119`，捕获为 640×640、DPR 1、`#20242aff`；
7. 批准 PNG 字节 SHA 正确，并按批准合同中的阈值计算 RGBA 差异。

## 4. 读取结果

退出码含义：

| 退出码 | 含义 |
| --- | --- |
| `0` | 输入可信，所有 sample 的像素指标通过 |
| `1` | 输入可信，但至少一个 sample 超过批准阈值 |
| `2` | 请求、文件、精确地址、来源绑定或内部合同无效 |

报告 Schema 是 [spine42-v3-setup-regression-report-v1.schema.json](../schemas/spine42-v3-setup-regression-report-v1.schema.json)。重点查看：

- `comparison_profile_sha256`：本次执行采用的冻结比较语义；
- `samples[].source`：P3、P6、P10.7a、P10.7a run document、raster metrics、capture plan/session/manifest 的精确身份；
- `actual` 与 `approved`：PNG/RGBA SHA、尺寸，以及固定的 setup case、`opaque_composite` artifact、`animation=null`、`tick=0`；
- `metrics`、`thresholds`、`reason_codes`：差异与拒绝原因；
- `samples[].comparison_sha256`：单个 sample 全部对比结论的 domain-separated 内容身份；
- `setup_regression_report_sha256`：整份报告的 domain-separated 内容身份；它只是内容自哈希，不证明证据真实或来自可信执行。

报告真实性必须通过精确地址重新读取并重放 P3、P6、P10.7a、run document、P10.7b capture、批准合同和 PNG 才能建立，不能只看两个自哈希。当前命令已执行这套 exact evidence replay，但只把报告打印到标准输出。

报告即使 `status=passed`，`release_gate.status` 仍是 `blocked`。它只证明一个固定 setup 帧与操作者所选批准图的 bounded equivalence，不证明连续动画安全，也不授予 publish 或 release authority。将比较结果写成可寻址、不可变、可重新验证的 comparison bundle，是接入 readiness v2 前仍待实现的明确前置条件；在该 bundle 合同落地前，不要把临时输出复制成 readiness 通过证据。

## 故障排查

### 命令返回退出码 2

先核对请求是否仍为 canonical JSON、合同文件 SHA 是否变化，以及 P6/P10/capture 是否属于同一项目和 P3。命令不会自动寻找相邻 bundle，也不会从 `latest` 或 current head 补齐地址。

### `status=rejected`

查看 sample 的 `reason_codes` 和四项 metrics。不要放宽请求中的阈值——请求根本不允许自定义阈值；阈值只能来自批准的 P6 golden。应回查 P10.7a setup 变换、draw order、atlas、viewport 或 capture harness 的变化。

### 真实样本尚无 P10.7a/capture 地址

`wave-left-v1` 的 A/B P9 reviewed-motion 双地址已经 exact replay 通过；先按 [readiness 审计](how-to-audit-spine42-v3-readiness.md)把这些地址写入新的 canonical 请求，并关闭剩余 seam blocker，再按 [P10.7b Runtime 捕获](how-to-capture-spine42-v3-runtime.md)生成精确 capture。A 可直接进入 seam 人审；B 虽然 P9 通过，仍被四条下肢关系不可观测阻塞。fixture 只能验证机制，不能替代真实样本验收。
