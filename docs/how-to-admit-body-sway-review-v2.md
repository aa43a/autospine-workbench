# 自动准入 P10.3c v2 视觉复核结果

本文面向普通操作员，说明如何把一个 current、已批准的 P10.3c v2 sampled visual head 交给
P10.4a v2。页面只需要 completed Runtime job 的完整 `job_id`；不选择文件、不填写 SHA，也不要求
再次作出人工决定。

P10.4a 是只读、仅在本次编译时有效的准入检查。成功不等于连续时间安全、接缝安全、可发布
Spine timeline 或 release authority。

## 1. 从视觉复核成功回执进入

在 P10.3c 时间轴页面完成全部画面检查并明确提交。只有结果为
`sampled_visual_approved` 时，页面才显示“继续 P10.4a”按钮。按钮携带同一个完整 `job_id`：

```text
http://127.0.0.1:8765/body-sway-review-admission-v2.html?job_id=<完整 job ID>
```

若缺少 `job_id`，页面不会扫描 state、猜测 `latest` 或选择其他项目。请返回原 Runtime 采集任务，
从已完成 job 进入 P10.3c，再使用成功回执继续。

## 2. 等待自动校验

页面载入后会自动调用本地只读入口：

```text
GET /api/p10/runtime-capture/jobs/<job_id>/visual-review-v2/admission
```

服务端自动完成：

1. 确认 job 已完成并读取其不可变 execution 地址；
2. 重放 Preview v2、official Runtime execution、artifact set 与全部 authoritative captures；
3. 读取 P10.3c v2 history 快照 A；
4. 按精确 candidate、revision 与 decision SHA 重放 current decision；
5. 再读取 history 快照 B，并确认 A、B 完全一致；
6. 只在 current head 为 `sampled_visual_approved` 时输出 canonical admission。

普通页面只显示项目、动作、任务、current revision 和通俗结论。完整 admission SHA 与 canonical
JSON 收在“技术详情”中，仅供审计，不需要复制到下一页面。

## 3. 理解成功结果

“准入检查通过”表示：

- completed official Runtime sampled execution 已精确绑定；
- P10.3c sampled visual decision 已由人批准；
- 该 decision 在本次编译前后仍是 current head；
- 后续 P10.4b v2 可以把这份 admission 作为严格输入。

页面同时必须显示“这还不是可发布动画”。当前真实阻塞至少包括：

- 连续时间安全尚未证明；
- 当前仍是 preview-only timeline；
- current Manifest/P3 链缺少已复核接缝锚点；
- 可复用安全幅度范围尚未证明。

P10.4a 不写人工 revision、不发布 MotionInstance v3、不进入冻结 v1 幅度/连续证明，也不解除
release gate。

## 4. 失败时怎么办

页面 fail closed 时不会生成部分准入。常见情况是：

- job 不存在或尚未完成；
- current P10.3c head 是 rejected，或尚无人工 revision；
- Preview、P10.1、CaptureFraming、candidate 或 execution 来源已经变化；
- 读取期间出现新的 visual-review revision；
- exact decision、capture 或 canonical admission 校验失败。

可以点击“重新校验”处理短暂读取问题。若来源或 head 已变化，请返回原 P10.3c 页面核对；需要修复
绑定、动作、取景或素材时，应生成新的 Preview v2 和 execution，不覆盖旧 job 或旧 revision。

## 5. 下一门禁

当前下一工程项是独立的 P10.4b v2 幅度候选与连续证明。它不能复用冻结 v1 的
`BodySwayReviewAdmission v1`、`compile-body-sway-amplitude-envelope` 或
`compile-body-sway-continuous-proof` 语义。P10.4b v2 入口交付前，P10.4a 页面只报告已准入和明确
blocker，不自动跳转到旧链。

冻结 v1 的专业 CLI 仍可用于历史复验，见[冻结 v1 视觉复核准入](how-to-admit-body-sway-review.md)。
