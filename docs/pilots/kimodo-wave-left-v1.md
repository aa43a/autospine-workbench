# Kimodo `wave-left-v1` Pilot Handoff

本文是当前真实运行 pilot 的唯一身份记录，面向需要沿 exact 链继续 seam 与 P10 的维护者。它固定
`wave-left-v1` 的六输入准入、P7/P8、两个目标 P5、候选身份、已复验 P9 地址，以及样本 A 已闭合的
P10.5b/P10.5c 静态接缝身份，避免 README、路线图和操作手册重复抄写 SHA 后发生漂移。

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
| Approved depth policy identity | `f54ccb8e48a99a6df97a67b2d64de5a776f94b8bd7ba8cffe4382c7e0357c1ae` | `b1353fc5f722a10f83f98df7e67820310ff77029ca06ba2841937836d3b3324a` |
| Depth candidate report | `766837d64859fb27815dc084069116f7737505a17a578735116b655d89cb4ab7` | `1d1e13cc45b4f952c2c3bcd95bbcd8ec79be36df429102a2fc5392b95fb6c7a4` |
| Candidate ID inventory | `909c80506d6f869df7c94445bc1ab8d841c6ae37a2ca7b9d72237f0f30f29f1e` | `898ce987c04bf7b35b8f5bfe23aa6f9eb13a62b1d64b0fe8ef34b79ed84debd3` |
| P9 review package ID | `a933df26a457be609c6c30f08ad8ad0284ad2f2a02bd655163ebb6e7775764c0` | `5278cae0594a4f63a3b7029e4198a1cfc9b59beb06f7843d649653bfef1dede7` |
| P9 MotionInstance v2 | `3c7bb6efcdb91d3ad3c1984ae19159a2ceb2b7aa8f0b88fc405d63956bd59823` | `706225aca7359f46daf0c318e186252b36c44650cd1539eb667e40f50e715754` |
| P9 reviewed-motion bundle | `b347c56a217b4cc844da3f115f100ae8b1352389207f357824ba322bdb46649c` | `39076c3589b046268b01c6c85bb0f7393403d2d0973ae417ef78271b649d0e96` |
| Seam 自动入口状态 | `manual_review_required`：6 条待人审，0 条不可观测 | `blocked_unobservable`：2 条可人审，4 条不可观测 |

P3、P4、P7 与两个 P5 均已按 exact 地址复验；重复 P5 编译返回 `reused=true`。A/B
各得到 `120` 个 foot sample：`119` 个 `candidate`、`1` 个 `unconstrained`，且本轮阈值
下没有 `rejected_limit` 或 `rejected_conflict`。候选使用
`max_correction_reference_ratio=0.25`、`max_residual_px=8`，这两个值属于本次审查策略，
不是跨角色的视觉安全常量。

候选与授权历史文件位于 `workspace/reviews/wave-left-v1/<project>/`。保留的历史
`depth-pair-policy.proposal.json` 故意使用 proposal format 和
`pending_human_review`，正式 validator 必须拒绝它；表中的 SHA 只是草案文件身份，不是
`depth_pair_policy_sha256`。首轮草案每个项目只比较 character-left 挥动手与 face，以限制
人工复核规模。在 2026-08-29 批准前，操作者按要求在复核页面查看 exact source、slot/role、
setup front 与滞回参数，再显式下载正式 approved policy。

批准前，两份草案还经过了只读 test-only preflight：在内存中投影为正式字段后，分别重新加载 exact
P8/P5/P3 并通过 `require_depth_pair_policy(..., inputs=...)`，证明 source、slot/role、setup
front 与全帧可观测性结构兼容。当时的历史预检没有保存 approved policy，也没有生成 depth candidates，
不能代替人工批准。工作台现已另有生产级 loopback-only、zero-write Python preflight，可从原始
JSON 文本重算正式 policy identity 与完整 candidate inventory；它同样不升级这两份 proposal 的
`pending_human_review` 状态。

2026-08-29，操作者在 P9 复核页分别批准 A/B 草案；下载的正式 policy 经 strict JSON、正式
validator 和生产 `policy_identity` preflight 通过，与各自草案相比只发生允许的 proposal→formal
投影。随后从表中固定的 P3/P5/P8 exact 地址生成两份 depth candidate report：每份均有 1 个 pair、
120 个 sample、0 个切换 event。Python `candidate_inventory` 对两组 policy/foot/depth 原文、三份
声明 SHA、完整 schedule、source/policy 交叉绑定和 candidate ID 清单复算均为 `passed`。每个项目
当前需要决定 119 个 Foot 候选，另有 1 个 unconstrained sample；没有 Depth event 需要决定。
复核台从 `workspace/reviews/wave-left-v1/<project>/` 发现两份 exact package，按项目选择加载并重算上述身份；推荐项只是确定性起点，不会按下载文件名或 mtime 猜测。120 个时间样本会显示为曲线、重点窗口和角色足点叠加。操作者拖动时间轴或点击“一键采用”时，页面只为尚未决定、`state=candidate`、observations 完整有限且 correction ratio/residual 均不超过合同上限 80% 的 Foot candidates 写入带 provenance 且可撤销的辅助草稿；Depth、`rejected_*`、缺证、非有限值和超阈值项不会自动批准。重点窗口只是视觉提示，不改变这项判定。

2026-08-30，操作者分别完成 A/B 的最终 human adoption。本机服务从各自 exact package 重新编译 decision、reviewed policy 与 MotionInstance v2，发布六文件 reviewed-motion bundle，并立即按表中的双 SHA 读回。随后独立运行 `verify-reviewed-motion-bundle`，两项目均返回 `verification.status=passed` 与 `replayed_from_exact_upstreams=true`。因此本 pilot 的 P9 人工决定与 exact reviewed-motion 地址已经闭合；这项结论只适用于表中固定的两个项目、当前 clip 和当前候选身份。

## 样本 A 的静态接缝凭据

2026-08-30，操作者完成样本 A 的 P10.5b 最终确认；同一 package-bound 流程随后发布 P10.5c，
并从精确上游读回复验：

| 地址 | SHA-256 / revision |
| --- | --- |
| P9 review package | `a933df26a457be609c6c30f08ad8ad0284ad2f2a02bd655163ebb6e7775764c0` |
| P10.5b candidate | `8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6` |
| P10.5b decision | `111d7da8589204e300b9aa8067b1f69baf938ca6f2cd715961b0b506fb55f680` |
| P10.5b revision | `1` |
| P10.5c reviewed set | `47656c2510e98b7598937a2c3315cd8f6e05274162160cf11a07cc167ed0e4d9` |
| P10.5c bundle | `fb8886cf1dcbff5d0ccb1fc36c6a087d93ad4e87678169dbad435e9e30e1adbe` |

该组凭据只证明样本 A 的六条 setup 静态 locator 已通过人工决定、内容寻址发布与 exact replay。
它不证明 P10.1 身体摆动已经批准，也不证明动作中的接缝、官方 Runtime、连续 raster 安全或发布权。

## 权限与质量边界

这份 handoff 只允许声明：该组 recorded 输入已经闭合、P7 结构编译与 exact replay 通过、
显式相机的 P8 投影与 exact replay 通过、A/B 的 P5 目标重定向结构与 exact replay 通过，
表中两个 P9 reviewed-motion bundle 已从精确上游重放通过，以及样本 A 上表 P10.5b/P10.5c
静态接缝身份已经闭合。
它不授予或证明：

- 外部 checkpoint authenticity、模型或素材许可；
- 广泛动作集的质量验收，或目标角色上的视觉质量；
- P5 在目标角色上的 raster、接缝或作品质量；
- 样本 A 的动态 seam、样本 B 的完整静态 seam、官方 Spine Runtime、连续 raster 安全、
  publishable timeline 或 release authority。

intake report SHA、P7/P8 bundle 地址和 P5 地址都不能替代表中的 P9 双 SHA 填入
readiness 请求。任何输入、map、camera、compiler 或算法 profile 变化都必须生成新地址，不能
沿用本 handoff 的人工结论。

## 下一步

1. 项目 A（`seethrough_output`）打开 `idle-behavior-review.html`。页面自动选择确定性 P9 package，并由服务端 exact replay P3/P5/P9、准备 P10.0 候选；普通用户不选择文件或填写 SHA。推荐参数只是 `unvalidated_draft`，必须看图、播放并最后明确确认，才能形成 P10.1 revision。目前不能声称 P10.1 已通过。
2. 项目 B（`seethrough_output_5`）虽然 P9 已通过，但左右 `pelvis_leg` 与 `leg_foot` 四条关系不可观测。必须修复 See-through 分层/语义并生成新内容地址，或另立明确禁止通用腿部动画的版本化 partial seam 合同；不得把 P9 成功改写成完整下肢 seam 通过。
3. A 的 P10.1 确认后依次完成 P10.2、P10.3 与 P10.4b2，再将该精确动作域与既有 P10.5c 双 SHA 组合为 P10.5d；静态 set 不能直接证明动态 seam。
4. 为 readiness v1 生成新的 strict canonical 请求并显式写入表中 P9 双 SHA 与 A 的 P10.5c 双 SHA。仓库自带的 baseline 请求仍把下游字段设为 `null`，不会自动发现这些地址。
5. 在相应 P10.5d 合同关闭后继续 P10.6–P10.7a、官方 Runtime capture、sampled raster 人审与独立 P10.7c setup golden 对照。
