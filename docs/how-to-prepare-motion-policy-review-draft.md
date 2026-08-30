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
  seethrough_output_5 wave-left-v1-r15-draft `
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

下一步仍是操作者查看 `depth-pair-policy.proposal.json` 并明确批准。只有得到独立的正式
policy 后，才能用 `probe-depth-order` 生成 Depth candidates，再进入 Motion Policy 页面做
一次最终 P9 adoption。
