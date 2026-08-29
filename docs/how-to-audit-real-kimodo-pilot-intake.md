# 审计真实 Kimodo Pilot 输入

本文是面向动作资产操作者的 How-to。目标是在发布 P7/P8 工件之前，把一份真实 Kimodo NPZ、解释 sidecar、显式 map、camera，以及 sidecar 声明的 checkpoint manifest 和 generation request 原件闭合为一份确定性的零写入报告。

该入口只回答“这六份精确输入内容是否具备进入 P7/P8 编译的结构条件”。它不认证外部 checkpoint 的真实性，不评价动作质量，不生成投影，不执行 P9 人审，也不授予发布或 release 权限。

## 准备文件

在仓库根目录准备六份彼此显式的输入：

- 原始 Kimodo SOMA77 `.npz`，不得为了整理而重新保存；
- `source.json`，其 `producer.status` 必须是 `recorded`；
- `map.json`，明确 clip、loop、basis、reference length、bone 与 contact 映射；
- `camera.json`，basis 与 reference length 必须和 map 相同；
- 生成该动作所使用的 checkpoint manifest 原始字节；
- 生成请求的原始字节。

可从 [source 模板](../examples/kimodo/soma77-source.template.json)、[正面 map 示例](../examples/kimodo/soma77-front.map.example.json) 和 [正面 camera 示例](../examples/kimodo/soma77-front.camera.example.json) 开始。模板中的占位值不能直接作为真实输入。

sidecar 中以下两个字段必须是对应原件逐字节 SHA-256：

```text
producer.checkpoint_manifest_sha256
producer.generation_request_sha256
```

审计器把两份原件当作有界 opaque bytes。它验证内容身份，但不猜测或重写 Kimodo 仓库外部格式。

## 运行审计

先让本地源码包可见：

```powershell
Set-Location E:\proj\unusual\localset\autospine-workbench
$env:PYTHONPATH = (Resolve-Path .\src).Path
```

再运行：

```powershell
python -B -m autospine_workbench audit-kimodo-pilot-intake `
  .\inputs\kimodo-wave.npz `
  .\inputs\kimodo-wave.source.json `
  .\inputs\kimodo-wave.map.json `
  .\inputs\kimodo-wave.camera.json `
  --checkpoint-manifest .\inputs\provenance\checkpoint.manifest `
  --generation-request .\inputs\provenance\generation-request.json
```

成功时默认输出的 `intake.status` 为 `eligible_for_p7_p8_compile`；使用 `--document-only` 时该字段位于顶层。报告会逐字节固定原始 NPZ 和两份 opaque provenance 原件，并以 canonical JSON 身份固定 sidecar、map 与 camera；同时记录 recorded producer、P7 内存编译得到的 MotionIR/run 身份，以及 camera/map 准入结果。相同 canonical 输入、compiler 与算法 profile 必须得到相同报告哈希；只改变 JSON 空白不会改变 canonical 身份。报告不包含本机路径。

如果只需要 canonical report：

```powershell
python -B -m autospine_workbench audit-kimodo-pilot-intake `
  .\inputs\kimodo-wave.npz `
  .\inputs\kimodo-wave.source.json `
  .\inputs\kimodo-wave.map.json `
  .\inputs\kimodo-wave.camera.json `
  --checkpoint-manifest .\inputs\provenance\checkpoint.manifest `
  --generation-request .\inputs\provenance\generation-request.json `
  --document-only
```

命令没有 `--state-root`，不会创建、发布或修改工件。失败响应使用固定错误码，不回显私有输入路径。

## 正确解释 claims

成功报告只允许以下三个正向结论：

- 原始 NPZ 和两份 provenance 原件的字节摘要已经闭合，三份 JSON 输入的 canonical 身份已经固定；
- P7 结构编译已经在内存中通过；
- P8 camera 输入与 map 已经通过准入。

以下结论始终为 `false`：checkpoint authenticity、动作质量批准、P8 投影已生成、P9 已复核、release authority。报告哈希只是内容身份，不能复制到 readiness 请求中冒充 P7/P8/P9 bundle 地址。

## 审计通过后的顺序

1. 用同一 NPZ、sidecar 和 map 执行 `compile-kimodo-motion`，保存返回的 P7 双 SHA。
2. 用 `verify-kimodo-motion` 从精确地址重放 P7。
3. 用同一 camera 和 P7 双 SHA 执行 `compile-projected-motion`，再用精确地址复验 P8。
4. 为两份目标 rig 分别重新编译 P5 retarget；既有 builtin idle/wave 地址不能作为真实 Kimodo 地址复用。
5. 生成 P9 foot-lock/depth-order 候选，停在人工复核点，完成决定后再发布 reviewed-motion bundle。

P7 的文件合同见[编译 Kimodo SOMA77 NPZ](how-to-compile-kimodo-npz.md)，P8 见[编译并复验投影证据](how-to-compile-projected-motion.md)，P9 见[复核 Kimodo 动作策略](how-to-review-kimodo-motion-policy.md)。

## 常见失败

| 现象 | 应对方式 |
| --- | --- |
| producer 是 `unavailable` | 回到生成端补齐真实 revision、checkpoint、request、seed 与 sample 记录；不要把历史未知来源改名为 recorded |
| provenance 摘要不一致 | 核对原件是否被格式化、换行转换或替换；以实际原始字节重新计算 SHA，并生成新的 sidecar |
| NPZ 与 sidecar 不一致 | 核对 NPZ SHA、长度、帧数、FPS 和数组 profile 是否来自同一次导出 |
| camera 与 map 不一致 | 显式统一 signed basis 和 reference length；不要让程序猜视角或比例 |
| P7 内存编译失败 | 按 P7 指南检查数组 inventory、dtype、SOMA77 FK、矩阵/关节一致性和 contact 布局 |

## 当前工作区状态

真实运行的 `wave-left-v1` 已用 recorded 六输入通过本页审计，并完成 P7/P8 与绑定到 A/B 的 P5 发布和 exact reader 复验；唯一身份记录见 [Kimodo `wave-left-v1` Pilot Handoff](pilots/kimodo-wave-left-v1.md)。它尚未形成绑定到 A/B 的 P9 reviewed-motion 地址，也不认证 checkpoint 或批准动作质量。对后续新 pilot 仍须逐一提供上述六份输入；测试夹具、builtin `idle`/`wave.left`、既有 intake 报告或全零模板都不能替代。
