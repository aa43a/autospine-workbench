# Kimodo `wave-left-v1` Pilot Handoff

本文是当前真实运行 pilot 的唯一身份记录，面向需要继续 P9 人审的维护者。它固定
`wave-left-v1` 的六输入准入、P7/P8、两个目标 P5 和候选交接地址，避免 README、路线图
和操作手册重复抄写 SHA 后发生漂移。

## 已闭合的证据

| 项目 | SHA-256 |
| --- | --- |
| 原始 Kimodo NPZ | `9b3b9e991370538e48b139ba618bcd8f52502835689bd828df7068dc3fc6c582` |
| Pilot intake report | `95f65a78683ff6fbcea8644f15244f2e57d2d8d8e77b74503b84d501a19d8307` |
| P7 MotionIR | `f67a9e9beae9d1292c0bd16bcb03024692ea43179be4ceeaf4ca413690636a93` |
| P7 bundle | `7d564a7f26e4a21a8f7d1e85e0d3875a8996ce191e8f4eea56d65856a786451f` |
| P7 compile run | `5fd8378eccf199b59e16502a71045ccfaf2e8045b35d08b580f829c430bc35a9` |
| P8 ProjectedMotionIR | `24608181e658a188aa6e05e5639b1c511dd9ce7fafcbc56d074815ec9c3a3195` |
| P8 bundle | `0e0275f8508e291c4f21b851b8a515ba635b24429c348ed7f15c40dea3150634` |
| P8 compile run | `5f7d05000bec92a1b9535d7392f5a48c1e0d83d27d23e5b2589225346d57fdf2` |
| P9 共享 Kimodo policy evidence | `32ba523e852dd13cbca97775b02aaa03b86e4a1d43534d71e02375aead4b1b07` |

六输入 intake 已得到 `eligible_for_p7_p8_compile`，随后 P7/P8 均已按上述 exact 地址发布并
通过各自 reader 复验。P8 的 collapsed sample 数为 `0`；全部已映射骨段的
`foreshortening_ratio` 范围为 `0.691123702`–`0.999703849`。

## 两个目标的 P5 与候选交接

| 地址 | `seethrough_output` | `seethrough_output_5` |
| --- | --- | --- |
| P3 rig | `40f96ade2f38f93caa7610b40f02ed9b30b8782396cee0e80499724a0450e327` | `897761e75bdd7e1cd3018cdab0f793f2d3ba637d88e01ce907beb179cfe0cd77` |
| P3 bundle | `7754406b1f6834a6b5c8fedfcd4743bd294d8cc568d7ff6413673cada3d79a1d` | `21f4707eaf023d664ae8cea8b785fd8a5197187f846d6db10b9c3ef34d7c6576` |
| P4 profile | `9fdecdbc084ab51b54768c4bbca18fbe484ad153ed8b426d1bd2937e6526b9d0` | `ee522acfdf729b179b0bd7fb15d29303c724b63d3f467a6a0ba035704ea4242d` |
| P4 bundle | `9089fd1859286022288b2b79b63b461c1d60a4bdc9509f50cdd7a6834b3933c3` | `a98a42e614f73f0df9dd6751a2a5a042dd707d6f4acff7e3410a4d69c6bd419b` |
| P5 target profile | `e20fd4c297c2e047a987456b3275fd3c5b9c5a6944d0c17059cb865e81b81301` | `7d2f76c318d84f30519013db552828394aab1a48739154cc687c743e1de830b2` |
| P5 MotionInstance | `1ce78189d2b71d01d2f6806da4ed6727c347f7e80f84605402b5f70cb7a0c89b` | `b0bb6b154543de19c4153aa3cf93f35ed9f055d9077ea5cc4a1d535985768d9a` |
| P5 bundle | `cd8717839fe66165f6b32cded0569c82497dc5e79d953c230fa5c905a02dc902` | `9acce5424a3d54cad51791695d787fc7f808a9c5dd59997354681c0162eacd2e` |
| Foot candidate report | `0d747347d7c4558239e2d9ea25eded676497d441e4f29c2433a57941cc296ccc` | `f845b74acd61ed0503505e55a7187f4a831b44ed4bf1b4faaf53336d4caf2bbf` |
| Pending depth proposal file | `3d0ebe51ac1ca0de9ee73a1880a61e781c7504ee9dfb067c308c9549a7267fe3` | `60dc9235fc56df2648cf1ce140fd54a1bd3c0de621528cf8b9ba25e9e3c9623b` |

P3、P4、P7 与两个 P5 均已按 exact 地址复验；重复 P5 编译返回 `reused=true`。A/B
各得到 `120` 个 foot sample：`119` 个 `candidate`、`1` 个 `unconstrained`，且本轮阈值
下没有 `rejected_limit` 或 `rejected_conflict`。候选使用
`max_correction_reference_ratio=0.25`、`max_residual_px=8`，这两个值属于本次审查策略，
不是跨角色的视觉安全常量。

候选文件位于 `workspace/reviews/wave-left-v1/<project>/`。其中
`depth-pair-policy.proposal.json` 故意使用 proposal format 和
`pending_human_review`，正式 validator 必须拒绝它；表中的 SHA 只是草案文件身份，不是
`depth_pair_policy_sha256`。首轮草案每个项目只比较 character-left 挥动手与 face，以限制
人工复核规模。操作者必须在复核页面查看 exact source、slot/role、setup front 与滞回参数，
再显式下载正式 approved policy。

两份草案还经过了只读 test-only preflight：在内存中投影为正式字段后，分别重新加载 exact
P8/P5/P3 并通过 `require_depth_pair_policy(..., inputs=...)`，证明 source、slot/role、setup
front 与全帧可观测性结构兼容。该历史预检没有保存 approved policy，也没有生成 depth candidates，
不能代替人工批准。工作台现已另有生产级 loopback-only、zero-write Python preflight，可从原始
JSON 文本重算正式 policy identity 与完整 candidate inventory；它同样不升级这两份 proposal 的
`pending_human_review` 状态。

## 权限与质量边界

这份 handoff 只允许声明：该组 recorded 输入已经闭合、P7 结构编译与 exact replay 通过、
显式相机的 P8 投影与 exact replay 通过，以及 A/B 的 P5 目标重定向结构与 exact replay 通过。
它不授予或证明：

- 外部 checkpoint authenticity、模型或素材许可；
- 广泛动作集的质量验收，或目标角色上的视觉质量；
- P5 在目标角色上的 raster、接缝或作品质量；
- P9 foot-lock/depth-order 人工决定或 reviewed-motion bundle；
- seam、官方 Spine Runtime、连续 raster 安全、publishable timeline 或 release authority。

intake report SHA 不是 P7/P8 bundle 地址；P7/P8 地址也不能作为 P9 reviewed-motion 地址填入
readiness 请求。任何输入、map、camera、compiler 或算法 profile 变化都必须生成新地址，不能
沿用本 handoff 的人工结论。

## 下一步

1. 分别人工检查并批准或修改两份 depth-pair policy proposal，并以生产 Python `policy_identity`
   preflight 取得正式 canonical SHA；preflight 通过仍不等于批准。
2. 用批准后的 exact policy 生成各目标 depth-order candidates，再以 Python `candidate_inventory`
   重算 policy/foot/depth 三 SHA、完整合同与交叉 source/policy 绑定。
3. 在 P9 复核页穷尽 foot/depth 决定，用 CLI 编译 decision 与 reviewed policy。
4. 发布并复验各项目的 P9 reviewed-motion bundle；只有取得 P9 exact 地址后，才能继续
   回填 readiness 和后续 P10 链。
