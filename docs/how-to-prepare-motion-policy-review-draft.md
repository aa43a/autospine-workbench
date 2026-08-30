# 准备新的 Motion Policy 复核草案

当 P3/P4/P5 因绑定或语义修正而变化时，不应把旧 P9 决定或旧候选复制到新链。
`prepare-motion-policy-review-draft` 会从显式 exact 地址一次性完成以下零批准工作：

- 重放并交叉核对 P3、P4、P5、P7、P8；
- 生成 Kimodo policy evidence；
- 生成 path-free standalone Foot-lock report；
- 根据当前 P3 slot 绑定、P5 canonical bone role 和 setup draw order 生成 pending Depth proposal；
- 原子写入一个此前不存在的 `workspace/reviews/<NEW_NAMESPACE>/`。

它不会生成 `depth-pair-policy.json`、Depth candidates、人工 decision、reviewed policy 或
P9 bundle。输出 namespace 因此不会被默认 P9 package 发现器误认为可采用 package。

发布后的固定 inventory 是：

```text
workspace/reviews/<NEW_NAMESPACE>/
├── shared/kimodo-policy-evidence.json
└── <PROJECT>/
    ├── foot-lock-candidates.json
    ├── depth-pair-policy.proposal.json
    └── draft-manifest.json
```

CLI 回执只返回 namespace、project、是否幂等复用、manifest SHA、Foot SHA
与 proposal SHA；不返回 state root 下的本机目录。

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -B -m autospine_workbench prepare-motion-policy-review-draft `
  seethrough_output_5 wave-left-v1-r16-draft `
  --p3-rig-sha256 <NEW_P3_RIG_SHA> `
  --p3-bundle-sha256 <NEW_P3_BUNDLE_SHA> `
  --p4-profile-sha256 <NEW_P4_PROFILE_SHA> `
  --p4-bundle-sha256 <NEW_P4_BUNDLE_SHA> `
  --motion-instance-sha256 <NEW_P5_INSTANCE_SHA> `
  --motion-retarget-bundle-sha256 <NEW_P5_BUNDLE_SHA> `
  --p7-motion-sha256 <EXACT_P7_MOTION_SHA> `
  --p7-bundle-sha256 <EXACT_P7_BUNDLE_SHA> `
  --p8-motion-sha256 <EXACT_P8_MOTION_SHA> `
  --p8-bundle-sha256 <EXACT_P8_BUNDLE_SHA> `
  --first-slot-id layer-008-hand-r `
  --second-slot-id layer-013-face `
  --pair-id hand-left-vs-face `
  --state-root .\workspace
```

对当前样本 B，`layer-008-hand-r` 的 `depth_role` 必须由新链自动得到
`humanoid.arm.upper.left`；不要把旧 proposal 中的 `humanoid.arm.lower.left` 复制过来。
命令会对既有 namespace 执行 exact inventory/byte 对比：完全相同可幂等复用，存在额外文件
或字节差异则失败。若要重新生成，使用新的 namespace，不要覆盖历史目录。

当前 revision 16 已生成的草案身份如下，供只读核对；这些 SHA 不是批准凭据：

| 工件 | SHA-256 |
| --- | --- |
| P3 rig / bundle | `c254a13adcf6b255fd0d51f8ad8aaa44e9d7097eadf57feb8836e61e0ad1a7ad` / `4c5d0044b64b43a995a6467dcbead52fd7d0f98d3396e3337c81070901410e63` |
| P4 profile / bundle | `39ee630756608ff819e509bbdbb928e8fdb97ea27adadf65d7b3cb4249802f4e` / `81595efe8d7f2f6ffa67ce481ff053a30adef761e32876ebf8ef9ebc038f2e6b` |
| P5 instance / bundle | `61cf4b8b907269dbf40156c771b406ff80c41ac13248ec91077bde50adebf772` / `f679df13d861e53fbb9aa9e318ced08e4e7678c006679ec3a84cfe2a3ef45b51` |
| Foot candidates | `4a53f4e67d225ad969d42954d2822fffdf1a5d1452f1578e2beabd3aca4faf9c` |
| pending Depth proposal | `432308add08014d4749cf0904ff2c1c4f409c1e9433398ffb0b4df206803b8a1` |
| draft manifest | `f9280c2034141a2135a5183df82710c1394e8e738c0cb889d03402c7ecec1ac7` |

样本 B 的 `ankle.left` 已人工标记为 `unobservable`，但 P4/Foot v1 会继续使用现有启发式
骨端坐标；已审 `shoe-opening.left` 只是分层代理点，两者相距约 `147.758 px`。所以候选数值
有限、P4 探针通过或 Foot state 为 `candidate` 都不能证明左脚真实接触。正式复核时不得自动批准
任何依赖 `leg.left` 的 root correction/foot-lock；在显式 proxy-effector/observability 合同交付前，
应将其保持为拒绝或不可观测。

下一步仍是操作者查看 `depth-pair-policy.proposal.json` 并明确批准。只有得到独立的正式
policy 后，才能用 `probe-depth-order` 生成 Depth candidates，再进入 Motion Policy 页面做
一次最终 P9 adoption。批准 Depth proposal 不会同时批准 Foot candidates，更不会解除上述左脚
observability blocker。
