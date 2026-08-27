# 编译 P10.5a 静态接缝锚点候选

P10.5a 从一份精确 Layer Manifest 和一份精确 P3 mesh bundle 编译
`SeamAnchorCandidates v1`。它只回答“哪些 attachment 接触位置值得人工比较”，
不会替操作者接受锚点，也不会读取动作、clip、P10 body-sway 或 runtime capture。

## 前置条件

准备同一项目的三个完整地址：

- `layer_manifest_sha256`；
- P3 `rig_sha256`；
- P3 `bundle_sha256`。

编译器会重新读取并验证不可变 Layer Manifest 与 P3 bundle，随后校验十项静态
source 身份：P3 的九项 source SHA，加上 attachment image set SHA。项目、画布、
manifest、RigIR、PNG 或 bundle 只要有一项交叉绑定不一致，命令就会失败。

## 运行只读编译

在仓库根目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -m autospine_workbench compile-seam-anchor-candidates <project-id> `
  --layer-manifest-sha256 <layer-manifest-sha256> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace
```

默认 stdout 是不含本地路径的摘要，包含 candidate SHA、计数、claims 和仍为
`blocked` 的 release gate。加入 `--document-only` 会输出 canonical candidate
document；两种模式都不会写入 state tree。

失败统一返回退出码 `2`、`seam_anchor_candidates_failed` 和固定错误消息。详细异常
保留在进程内 cause 链中，不会把本地目录打印到公共 CLI 输出。

## 如何阅读候选

文档固定包含六条关系，顺序不能改变：

1. 左/右 `torso_arm`；
2. 左/右 `pelvis_leg`；
3. 左/右 `leg_foot`。

每条关系只会是：

- `review_required`：至少有一个可比较的 candidate option；
- `unobservable`：没有可用 candidate，并带明确原因。

编译器从 setup alpha 的 8 连通接触 lobe 取共同像素，沿接触 bbox 主轴做固定
分位采样。一个 candidate 有 2–4 对锚点；region locator 使用 Q4096 attachment-local
坐标，mesh locator 使用 Q65535 重心坐标，并在量化后重新选择最小包含三角形。
锚点必须在父、子 attachment 上分别严格有序，连接段不能相交或相触。

v1 支持 `region-region`、`region-mesh` 和 `mesh-region`。`mesh-mesh` 不会被
物化；gap、预算耗尽、采样点不足或 locator 无法表示只会生成 unavailable 证据，
不会偷偷放置 fallback locator。

relationship reason 必须覆盖所有 option reason。reason 词表、status/contact/
sampling/type 矩阵、候选锚点上限及 option/relationship evidence hash 都由独立
validator 重算；即使攻击者重签 evidence hash，也不能把生成器不可能产生的状态
伪装成有效候选。

## 算法身份与资源边界

generator `1.1.0` 内嵌 canonical algorithm profile 及其 SHA。profile 覆盖：

- 六条关系、角色 token、左右与 neutral-side 规则；
- alpha threshold、逐 attachment/全局 run 上限；
- contact/lobe 连通性、最小面积/比例与 gap；
- relationship pair、option、intersection run、common-alpha pixel 和文档上限；
- sampling、locator 量化、mesh shared-edge 和 pair 非相交策略。

编译时从实际导入的行为常量重建 profile。因此行为参数变化会改变 candidate SHA，
旧人工决定不能静默套用到新算法输出。输入还在复制、PNG 解码和 alpha 展开前执行
layer、attachment、字节、像素、JSON 节点/深度与 pending-stack 预算；任一全局预算
耗尽都会 fail closed 或把相关 option 标为 unavailable。

## 真实样本回归

当前批准投影为：

| 项目 | 状态 | candidate / unavailable option | 锚点对 | candidate SHA |
| --- | --- | ---: | ---: | --- |
| `seethrough_output` | 6 条需复核 | 9 / 0 | 36 | `8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6` |
| `seethrough_output_5` | 2 条需复核、4 条不可观测 | 2 / 0 | 8 | `f53d049df823b2507db5cafa7e0d06bf97519e6bf0494bbfb53c5911d37d2a37` |

普通测试固定两个项目的顺序、唯一性、三段输入地址、关系投影和计数。显式只读重放
真实 bundle：

```powershell
$env:AUTOSPINE_VERIFY_REAL_SEAM_GOLDENS = "1"
python -m unittest tests.test_seam_anchor_goldens
```

## 本阶段不会交付什么

P10.5a 不保存 candidate、不创建 revision，也不生成 reviewed anchor set、动态接缝
证明、MotionInstance v3 或 Spine timeline。所有 human-selection、dynamic seam、
runtime、视觉质量和发布 claims 均固定为 `false`。

P10.5b 已把 candidate SHA 和 option evidence SHA 绑定到独立人工决定，支持
`accept`、`adjust`、`reject` 与 `unobservable`，并以 revision/CAS 保存完整历史；
操作见[复核 P10.5b 静态接缝锚点](how-to-review-seam-anchors.md)。P10.5c 才能从当前
人工决定编译 `ReviewedSeamAnchorSet`；P10.5d 再把它接入与 P10.4b2 相同动作域的
动态接缝探针。
