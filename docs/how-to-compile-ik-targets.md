# 编译并验证两骨 IK 目标

本指南用于从一个已经严格验证的 P3 mesh bundle 生成 P4 离线 IK 目标，并复验其不可变证据。它面向在本仓库中继续开发或执行阶段验收的工程人员。

P4 只产生版本中立的两骨目标合同和 setup-local 求解结果，不生成 Spine runtime IK constraint，也不替代 P3 的网格视觉安全门禁。

## 前提

准备以下输入：

- 一个安全可读的 state root；
- 项目 ID；
- 精确的 P3 `rig_sha256`；
- 与该 rig 配对的精确 P3 `bundle_sha256`。

P3 地址必须已经通过 `verify-mesh-bundle`。不要传入目录别名、大小写变体或名为 `latest` 的路径。

## 1. 编译并发布 P4 bundle

在仓库根目录运行：

```powershell
python -m autospine_workbench compile-ik-targets <project-id> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace
```

命令依次执行以下门禁：

1. 严格读取指定的 P3 bundle，并复验其 P2 来源、mesh、探针和视觉证据。
2. 从 setup FK 几何生成 `arm.left`、`arm.right`、`leg.left` 和 `leg.right` 四个手柄。
3. 运行 setup、可达中点、过远、过近和目标重合数值探针。
4. 发布仅包含 `profile.json` 与 `probes.json` 的 canonical bundle。
5. 从发布地址严格重读，再与内存编译结果逐项比较。

成功响应的 `status` 为 `passed`，并包含：

- `p3_source`：完整 9 项 P3 身份；
- `profile_sha256` 与 `probes_sha256`；
- `bundle_sha256` 与精确 `path`；
- `summary=handles=4`。

同一输入和算法重复运行会收敛到同一地址。算法或探针改变会产生新哈希，不会改写旧证据。

## 2. 只读复验精确地址

保存编译响应中的 profile 与 bundle SHA，然后运行：

```powershell
python -m autospine_workbench verify-ik-bundle <project-id> `
  --profile-sha256 <p4-profile-sha256> `
  --bundle-sha256 <p4-bundle-sha256> `
  --state-root .\workspace
```

复验命令不会发布、修复或发现工件。它只接受给定双 SHA 地址，并执行以下检查：

- 目录和文件名精确匹配，且没有 symlink、junction、大小写别名或额外文件；
- 两份 JSON 是有限、无重复键的 canonical 内容；
- profile、probes、bundle 和完整 P3 来源身份相互绑定；
- 当前代码从精确 P3 来源重建的 profile 与 probes 与保存字节完全一致。

成功返回退出码 `0`。领域合同、地址或证据失败返回退出码 `2`，并输出 `status=error`；命令不会用其他 bundle 代替失败地址。

## 3. 正确解释可达范围

每个手柄的 `kinematic_reach` 是由两段骨长决定的闭合距离范围：

- `minimum_px = |proximal_length - distal_length|`；
- `maximum_px = proximal_length + distal_length`。

目标过远或过近时，solver 会把目标投影到该范围边界，并在报告中保留 requested 与 resolved 目标。目标重合或骨长退化也必须得到有限结果或明确错误，不能产生 NaN。

该范围只证明骨链在数学上可求解。P3 的 mesh 动作探针仍是极值姿势是否出现翻三角、裂缝或明显视觉破坏的权威边界。P5 在编译动作时必须同时服从这两个合同。

## 4. 运行真实样本回归

普通测试只检查批准合同的结构和语义：

```powershell
python -m unittest tests.test_p4_ik_goldens -v
```

要从本地两份精确 P3 bundle 重建，并证明复验前后 state tree 未变化，显式启用真实门禁：

```powershell
$env:AUTOSPINE_VERIFY_REAL_P4_GOLDENS = "1"
python -m unittest tests.test_p4_ik_goldens -v
```

批准文件位于 `tests/goldens/p4-ik/`。测试不会自动更新这些文件；任何预期变化都必须先审查算法、完整身份链和数值差异，再单独批准。
