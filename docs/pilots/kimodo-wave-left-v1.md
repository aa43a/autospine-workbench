# Kimodo `wave-left-v1` Pilot Handoff

本文是当前真实运行 pilot 的唯一身份记录，面向需要沿 exact 链继续 P9、seam 与 P10 的维护者。它固定
`wave-left-v1` 的六输入准入、P7/P8、两个目标的历史 P5/P9、样本 A 的历史 P10.5b/P10.5c，以及
随后形成的 A revision 6、B revision 16 新链草案，避免 README、路线图和操作手册重复抄写 SHA 后发生漂移。

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

## 样本 A revision 6 的新链草案

2026-08-31，操作者根据旧 P10.2 动作证据明确确认
`layer-007-handwear-l: forearm.left → upper-arm.left`，并保存 override revision 6。该 revision
带有 `region-rebind-adoption-v1` provenance，绑定提出建议时的旧 Resolved/Manifest、P10.1
revision 2、候选、P3 rig 与 P9 MotionInstance v2；它没有把建议静默写回旧工件。新 Resolved、
Manifest、P2–P5 已按 revision 6 身份重建，并分别通过 P3/P4/P5 exact verifier：

| 地址 | SHA-256 / 值 |
| --- | --- |
| Override revision | `6` |
| Resolved Project | `12b6ec647e6f0e551d7c1bbcf21639fab888768910816d0d67c8f96fc3cf247b` |
| Layer Manifest | `81bc00cbd0199bbdc77914c8a226cd14ffaf2dd4d287448f9b69fdddaa417641` |
| P2 rig / bundle | `f5a909bdbbec6ea612ba50ad978c98a085a732cfa59194a324a13d43d08a4124` / `d428aee54a18761e687f3bacc4701b057704978db72a3f1b8a9ac9261a1f09ae` |
| P3 rig / bundle | `309e4ef123a45c0d86b22e0b3655dec94edbb23fc112d177a0721d75477a7ac3` / `92b398a89e12956ee37aa8f55abe9fb7d138898f7d19620cf6e53c753a75bd3b` |
| P4 profile / bundle | `2ea6e2ce10d02e1cb7950bf6c588a23a7dada5693b35f63137dc0700b085e762` / `26913a21bf69e2174fae4c61ff79c7aae71b0fe265a5db1d3a8cdadb32a4f98c` |
| P5 target profile | `a6dd6dd908d4869424fbcfc709225cc6b0dd5c53440961b49c70b17ae8360e71` |
| P5 MotionInstance / bundle | `fae376f7742488796f05bd8f1a8e24a7818222c044aa87f00333107fb6fb9d6e` / `498d287cffec06c050079066f6b8101c22e5de4cac7fe818bf845ab755d8999f` |
| Draft namespace | `wave-left-v1-r6-draft` |
| Draft ID | `667e6ecab0f50c267f4d1f0d5c9b03fd6a1f8fb1ebaf848e977cf46470227bcf` |
| Draft manifest | `69e609ed579bd1ffbe61cd1cbb77bbf1c9dbe3964a89cc8834a6d94ebc7a9263` |
| Pending Depth proposal | `b968c22ded83674faed1b41e155724843a942fc82fc455b71490194f29623b4f` |
| Foot candidate report | `dd384d948bc703bbda23a02774717e60c74d37be84dc7c61f9989c91b49e59c2` |
| 晋级后的 motion ID | `wave-left-v1-r6-p667e6ecab0f5` |

草案 proposal 使用 `hand-left-vs-face`，setup front 为 `layer-011-face`；换绑后的
`layer-007-handwear-l` 角色为 `humanoid.arm.upper.left`。草案 authority 仍明确为
`approved_depth_policy=false`、`depth_candidates_emitted=false`、`p9_adoption_emitted=false`。
Motion Policy 页面可以自动发现这份 current 草案，唯一候选时自动选择；操作者明确确认 setup
前后关系后，服务端才会生成正式 policy、Depth candidates 和新的 exact review package。
这次“草案晋级”不是最终 P9 adoption：晋级后的 Foot/Depth candidates 仍须在下一段页面中完成
候选复核和一次独立的最终 human adoption。旧 package `a933df26…`、旧 P9 双 SHA 以及由其派生的
P10.1/P10.2/P10.5c 都只保留为历史证据。

## 样本 B revision 16 的新链草案

2026-08-30，操作者又保存了样本 B 的绑定 revision 16。上表中的 P9 adoption 仍可按原字节链
精确复验，但不能授权这次新的绑定/语义身份。新链已从 revision 16 严格重建到 P5，并在独立
`wave-left-v1-r16-draft` namespace 中准备 P9 非权威输入：

| 地址 | SHA-256 |
| --- | --- |
| Layer Manifest | `947a8e3f1723d535a0f61d3dd67191252b53c4a2d9d6823e941e54d33bee5d88` |
| P2 rig / bundle | `d12837b4d8a8d71fe5ef8b9b66030268bd2809302e9f800f8344e0422825269c` / `77c6d0f8f1a0bcc3e87913529bea117b2fcac30069344ae7e1fe33d43b6233f6` |
| P3 rig / bundle | `c254a13adcf6b255fd0d51f8ad8aaa44e9d7097eadf57feb8836e61e0ad1a7ad` / `4c5d0044b64b43a995a6467dcbead52fd7d0f98d3396e3337c81070901410e63` |
| P4 profile / bundle | `39ee630756608ff819e509bbdbb928e8fdb97ea27adadf65d7b3cb4249802f4e` / `81595efe8d7f2f6ffa67ce481ff053a30adef761e32876ebf8ef9ebc038f2e6b` |
| P5 target profile | `25b99cc1cda43a458ba69419aef74d16e2cc96154b2d66f5f8b09fb075636ba8` |
| P5 MotionInstance / bundle | `61cf4b8b907269dbf40156c771b406ff80c41ac13248ec91077bde50adebf772` / `f679df13d861e53fbb9aa9e318ced08e4e7678c006679ec3a84cfe2a3ef45b51` |
| Foot candidate report | `4a53f4e67d225ad969d42954d2822fffdf1a5d1452f1578e2beabd3aca4faf9c` |
| Pending Depth proposal | `432308add08014d4749cf0904ff2c1c4f409c1e9433398ffb0b4df206803b8a1` |
| Draft manifest | `f9280c2034141a2135a5183df82710c1394e8e738c0cb889d03402c7ecec1ac7` |

P2 setup PNG/RGBA 与修正前逐字节相同；变化是能力语义：`layer-008-hand-r` 仍为
`body.arm.upper`、side `left`、绑定 `upper-arm.left`，但 P3 profile-v1 将其保持为 rigid
region。当前真实 alpha 上的临时手臂 mesh 探针在 `+15°` 已出现翻三角，且 `-30°` 拉伸超过
v1 上限，因此不能把它伪装为通过的 arm hinge；新 P3 正确结果是 `reviewed-noop`。

草案的 proposal 已从新链推导出 `humanoid.arm.upper.left`，但状态仍是
`pending_human_depth_policy_review`：没有正式 Depth policy、Depth candidates、decision 或
P9 adoption。它也可以由 Motion Policy 页面的 current draft 自动入口处理，但一次草案晋级仍不等于
最终 P9 adoption。另一个独立 blocker 是 `ankle.left=unobservable`。当前 P4/Foot v1 仍使用原启发式
骨端 `(696.2, 1582.68)`，而已审鞋口代理约为 `(701, 1435)`，两点相距约 `147.758 px`；数值探针
通过不能证明解剖脚踝、真实接触或 `leg.left` foot-lock。正式复核时不得自动批准依赖左腿足点的
root correction，直到有版本化 proxy-effector/observability 合同。

## 样本 A 旧链的静态接缝凭据

2026-08-30，操作者完成样本 A 的 P10.5b revision 1 与首个 P10.5c 发布。2026-08-31，
操作者提交 revision 2；它明确 supersede revision 1，并以 `6/6 accept`、`24` 个 anchor pairs
重新发布 P10.5c。当前精确身份如下：

| 地址 | SHA-256 / revision |
| --- | --- |
| P9 review package | `a933df26a457be609c6c30f08ad8ad0284ad2f2a02bd655163ebb6e7775764c0` |
| P10.5b candidate | `8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6` |
| P10.5b decision | `e80a07afc009276a6073684d8ce5a1bbf253cda9286bcc1f1ef8c95ef9669612` |
| P10.5b revision | `2`（supersedes revision 1） |
| P10.5b summary | `6/6 accept`；`24` anchor pairs |
| P10.5c reviewed set | `d801bdd2d60675242ece25aa5ed043cc2be1da6fea43c322c6377d1b93a8c8e1` |
| P10.5c bundle | `66318839656b1f5ad5c89aa49286f4c9a0bcb25e81434d0a9ba8af210a8c7ce9` |

被取代的历史 revision 1 仍可按精确地址复验，但不再具有 current-head authority：decision
`111d7da8589204e300b9aa8067b1f69baf938ca6f2cd715961b0b506fb55f680`、reviewed set
`47656c2510e98b7598937a2c3315cd8f6e05274162160cf11a07cc167ed0e4d9`、bundle
`fb8886cf1dcbff5d0ccb1fc36c6a087d93ad4e87678169dbad435e9e30e1adbe`。

revision 2 凭据只证明旧 P3/P9 链的六条 setup 静态 locator 已通过人工决定、内容寻址发布与
exact replay。A revision 6 已改变 Manifest/P3/P5 身份，所以该静态 set 与旧 P10.1 revision 2
都只保留历史复验价值，不能作为 r6 current authority。它们也不证明动作中的接缝、官方 Runtime、
连续 raster 安全或发布权；`dynamic_seam_safety_unproven`、`runtime_equivalence_unproven` 与
`visual_seam_quality_unproven` 仍使 release gate 保持 blocked。

## P10.1 current heads 与 P10.2 结构诊断

2026-08-31 的 current-head 双快照读取与零写入 P10.2 编译结果如下。P10.2 report 没有发布到
mutable alias；SHA 是相同 exact 输入与固定算法重新编译所得的 canonical 内容身份。

下表绑定的是本页前半部分已采用的历史 P9 链，不会自动迁移到 A revision 6 或 B revision 16
新草案。两个项目都只有完成各自新的 Depth policy、Depth candidates 与最终 P9 adoption 后，
才能为新链重新建立 P10 current head。

| 地址 / 结果 | `seethrough_output` | `seethrough_output_5` |
| --- | --- | --- |
| P10 review package | `183d5d2d970a1861360261f3607cf83910f25f6487dc4be3c5690d5d0099dec3` | `d2591818597c856a58e433a029fbf6c2d8a5efbb9bb4ea250970639abbb82212` |
| P10.0 candidate | `cd19684f792ca3e2c364c8abc6a5cde2c7a79e05e72b634a92e381d39b051cad` | `a46b9fcbdad898d8e6c45033210e3f09090b7b4bd3da3334532b8164dca72bb6` |
| P10.1 revision | `2` | `2` |
| P10.1 decision | `70d62da63a1ea392b79181d280984730b049bb018fcc443222f58e0f7878275e` | `206ec2d4b74ac0d94508d9aa7d95cee3f6a7b6339e4a5bd6ab8c5f9b08395a46` |
| P10.1 current state | `adjust / pending_probe` | `adjust / pending_probe` |
| P10.2 report | `4406289ece9ad0e707b2598eab0ba885bcb5f62d1e6be7d37bfa5c942a558e72` | `73fcea3c70aa03d4ffbda03d8971a1c33e29a363e3f09c7a0260a224d44bb7ad` |
| P10.2 status | `structural_rejected` | `structural_rejected` |

样本 A 旧链的 r2 参数为 cycles `2`、四骨幅度 `0.8/0.7/0.4/0.2°`、相位
`0/0.04/0.08/0.12`。不可变的 P10.2 v1 报告仍诚实记录：在固定 `1024×1024`
素材/setup 坐标下，334 个采样中有 218 个 containment 失败，`0/8` 仍有 217 个；这是一项
历史素材框诊断，不是 Rig 或 Runtime 相机的硬边界。P10.2 v3 的零权威动态视口候选已能
适配完整动作包络。唯一责任附件仍是 `layer-007-handwear-l`；动作证据候选推荐
`forearm.left → upper-arm.left`，setup 包络覆盖骨段由 1 增至 2，root-compensated motion
extent 改善约 `31.81%`。操作者已经完成这次确认并保存 revision 6；随后新
Manifest/P2–P5、P9、P10.1 与 P10.2 已按 current 身份重建。旧 P10 没有迁移到新链；当前
canvas-only P10.2 通过独立 CaptureFraming candidate/decision 和 P10.3 v2 合同承接，不能仅凭
dynamic fit 进入官方 Runtime。B 表中结果仍是 revision 16 之前的历史链证据。

本轮读取性能优化不改变上述证据边界：stored split revalidation 缓存绑定
source/preview/manifest 全字节、Resolved/decision 与 runtime，P9 exact replay 按 key
single-flight，list/detail 可按 `project_id` 限定范围；前后双快照仍保留，缓存不授予 authority。
实测全项目 warm 从约 `10.85 s` 降至约 `0.61 s`，A scope warm 约 `0.28 s`；冷启动仍需约
`18 s` 完整重放 A 的 P9 链。

## 权限与质量边界

这份 handoff 只允许声明：该组 recorded 输入已经闭合、P7 结构编译与 exact replay 通过、
显式相机的 P8 投影与 exact replay 通过、A/B 的历史 P5/P9 已从精确上游重放通过；A revision 6
和 B revision 16 已分别重建到 P5 并准备 pending P9 草案；样本 A 旧链的 P10.5b/P10.5c
静态接缝身份仍可精确复验。
它不授予或证明：

- 外部 checkpoint authenticity、模型或素材许可；
- 广泛动作集的质量验收，或目标角色上的视觉质量；
- P5 在目标角色上的 raster、接缝或作品质量；
- 样本 A 的动态 seam、样本 B 的完整静态 seam、官方 Spine Runtime、连续 raster 安全、
  publishable timeline 或 release authority。

intake report SHA、P7/P8 bundle 地址、P5 地址或草案晋级回执都不能替代最终 P9 双 SHA 填入
readiness 请求。任何输入、map、camera、compiler 或算法 profile 变化都必须生成新地址，不能
沿用本 handoff 的旧人工结论。

## 下一步

1. 在 [Motion Policy 自动工作流](http://127.0.0.1:8765/motion-policy-review.html) 选择 A revision 6 或 B revision 16 的 current 草案。页面自动读取来源和 SHA；操作者只确认 setup 前后关系，服务端生成正式 policy、Depth candidates 与新的 exact review package。
2. 不要把上一步回执当成 P9 完成。继续在同一页面复核晋级后的 Foot/Depth candidates，并执行一次独立的最终 P9 human adoption；B 的左腿 foot-lock 保持拒绝或不可观测。
3. 两个项目都按各自新 P9 地址重新建立 P10.0/P10.1、重跑 P10.2，并按新 Manifest/P3 重新生成静态 seam candidate。旧 P10 与 A 旧 P10.5c 只供历史复验。
4. 若新 P10.2 为 `manual_visual_required`，可按现有 v1 入口进入 P10.3。若唯一拒绝项仍是 `sampled_canvas_containment`，必须等待 CaptureFraming candidate/显式人工 decision 与 TemporaryPreview/RuntimeCapture v2：新合同须覆盖 setup、base、combined 完整包络，并保持原 v1 report/hash 不变；`DynamicViewportFit v1` 不能直接成为准入。
5. P10.3 sampled visual head、P10.4 区间证明和新链 P10.5c 闭合后，再组合为 P10.5d；草案晋级、取景决定和 sampled still approval 都不单独授予动态 seam 或 release authority。
6. 为 readiness 生成新的 strict canonical 请求，只写入实际最终采用并 exact verify 的 P9/P10 双 SHA；之后继续 P10.6–P10.7a、官方 Runtime capture、sampled raster 人审与独立 P10.7c setup golden 对照。
