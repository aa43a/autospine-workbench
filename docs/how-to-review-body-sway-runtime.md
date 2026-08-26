# 复核 body-sway 官方 runtime 采样帧

本文面向负责 P10.3 视觉验收的操作员，也提供 CLI 与 HTTP 客户端开发者所需的精确合同。目标是从一份不可变 runtime capture 生成候选、逐帧作出人工判断，并把判断追加为可回看的 revision。

本流程只批准或拒绝**已采样的静态帧**。即使所有 case 都是 `approve`，结果也只是 `sampled_visual_approved`；`release_gate.status` 仍为 `blocked`，不能据此发布 Spine 动画。

## 前置条件

开始前必须具备：

- 已通过 P10.2 结构探针的 exact candidate、decision 与 probe report；
- 同一来源链的 7 个完整 SHA；
- 操作者自行在仓库外安装且有权使用的官方 `@esotericsoftware/spine-player@4.2.119`；
- Windows 本机 Chrome/Chromium，以及捕获命令要求的显式许可确认；
- 捕获命令生成的 `captured_unreviewed` bundle。

真实证据必须由已授权的官方 Spine runtime 产生。`tests.test_body_sway_real_chrome_smoke` 使用 test-only `SpinePlayer` stub，只验证浏览器驱动和 PNG 通路，不能作为视觉复核输入或官方 runtime 兼容性证明。安装包内存在 `LICENSE` 文件也不等于已取得使用授权。

先按[捕获并封存 body-sway 官方 runtime 证据](how-to-capture-body-sway-runtime.md)运行真实捕获。视觉复核工具不会下载 runtime、运行捕获或从目录中猜测可用 bundle。

## 1. 记录精确四段地址

从捕获命令的调用参数与 canonical stdout 保存以下四项：

| 地址项 | 来源 |
| --- | --- |
| `project_id` | 捕获命令的 `<project-id>` 位置参数 |
| `temporary_preview_sha256` | stdout 的同名字段 |
| `runtime_capture_bundle_sha256` | stdout 的 `bundle_sha256` 字段 |
| `capture_artifact_set_sha256` | stdout 的 `artifact_set_sha256` 字段 |

四项共同定位一份不可变 capture。所有 SHA 必须是 64 位小写十六进制。CLI、API 和 UI 都不会扫描目录、选择首项、解析缩写 SHA，或自动回退到 `latest`。`candidate_sha256` 是从该 capture 确定性编译出的后续身份，不属于上述四段源地址。

## 2. 用 CLI 预检候选和历史

在仓库根目录执行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -B -m autospine_workbench prepare-body-sway-visual-review <project-id> `
  --temporary-preview-sha256 <temporary-preview-sha256> `
  --runtime-capture-bundle-sha256 <runtime-capture-bundle-sha256> `
  --capture-artifact-set-sha256 <capture-artifact-set-sha256> `
  --state-root .\workspace `
  --document-only
```

`prepare` 会重新验证 authoritative capture、确定性编译 candidate，并读取与该 candidate 绑定的完整线性历史。它不发布 candidate、不创建空历史目录，也不修改 state tree。省略 `--document-only` 时 stdout 只包含候选摘要和 bounded history；保留该参数时会输出完整的 path-free candidate 和历史快照。

记录输出中的：

- `candidate_sha256`；
- candidate 的全部 `cases[]`，尤其是 `case_id` 与 `evidence_sha256`；
- `history.current_revision` 与 `history.head_decision_sha256`。

若 exact capture 不存在、字节或哈希不一致、来源交叉接线，命令会 fail closed，而不是寻找替代 bundle。

## 3. 在可视化工作台逐 case 复核

启动本地服务：

```powershell
.\run.ps1
```

打开 [http://127.0.0.1:8765/body-sway-review.html](http://127.0.0.1:8765/body-sway-review.html)，然后：

1. 手工填写项目 ID 和三个完整 SHA，选择“加载精确候选”。页面初始不会自动选择任何 capture。
2. 检查候选摘要、固定顺序的 case、对应 PNG，以及持续显示的 release blocker。
3. 为每个 case 选择 `approve`、`reject` 或 `unobservable`。`reject` 与 `unobservable` 必须填写非空备注；这两种动作都会使总体状态成为 `sampled_visual_rejected`。
4. 在历史区重新读取当前历史，然后显式选择“以当前 head 为基线”。空历史也需要这个动作，它会选择 revision `0` / `null` 基线。历史列表本身不会自动选中 revision；点击某行才会按 revision 与 decision SHA 读取精确文档。
5. 填写安全格式的 Reviewer ID 和可选总备注，确认所有 case 已完成后提交。

非输入控件聚焦时，可用方向键移动 case，按 `1`、`2`、`3` 分别选择 approve、reject、unobservable；`Ctrl+Enter` 提交。窄屏布局、键盘焦点与 reduced-motion 已纳入前端回归，但实际图像判断仍由操作者负责。

提交成功后，页面会清除旧历史详情和提交基线，重新读取历史。若继续提交下一 revision，必须再次显式选择新的 head。

## 4. 用 CLI 提交（可选）

自动化客户端可以构造一个只含人工字段与 CAS 基线的 JSON：

```json
{
  "base_revision": 0,
  "candidate_sha256": "<candidate-sha256>",
  "previous_decision_sha256": null,
  "review": {
    "reviewer_id": "reviewer-01",
    "notes": "逐帧检查轮廓、遮挡和接缝。"
  },
  "decisions": [
    {
      "case_id": "<case-id>",
      "evidence_sha256": "<case-evidence-sha256>",
      "action": "approve",
      "notes": ""
    }
  ]
}
```

`decisions` 必须按 candidate 覆盖全部 case；不要自行省略、增加、重排或改写 `case_id` / `evidence_sha256`。上例只演示行结构，不能直接提交，因为实际 candidate 至少包含 3 个 case。对于 revision 1，基线固定为 `0` / `null`；后续 revision 必须使用最新的 `current_revision` 和 `head_decision_sha256`。

保存为 `review\body-sway-visual-review-submission.json` 后执行：

```powershell
python -B -m autospine_workbench submit-body-sway-visual-review <project-id> `
  --temporary-preview-sha256 <temporary-preview-sha256> `
  --runtime-capture-bundle-sha256 <runtime-capture-bundle-sha256> `
  --capture-artifact-set-sha256 <capture-artifact-set-sha256> `
  --state-root .\workspace `
  --submission .\review\body-sway-visual-review-submission.json
```

新 revision 成功时返回退出码 0 和 canonical JSON。相同基线、相同内容的安全重试会返回同一 decision，并以 `reused: true` 表示复用。旧基线或并发抢占返回退出码 3、`status: "conflict"` 和当前 head；重新运行 `prepare`、保留仍适用的草稿、显式换用新 head 后再提交。其他输入或重放失败返回退出码 2，stdout 不泄露本地路径或内部异常。

## 5. HTTP API 参考

以下 `{project}/{preview}/{bundle}/{artifact}` 就是同一个精确四段地址。`{candidate}`、`{decision}` 和 `{png}` 也只接受完整 SHA。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/projects/{project}/body-sway-runtime-captures/{preview}/{bundle}/{artifact}/visual-review/candidate` | 只读编译 candidate |
| `GET` | `.../visual-review/candidates/{candidate}/cases/{case}/image/{png}` | 读取 candidate 绑定的权威 PNG 字节 |
| `GET` | `.../visual-review/candidates/{candidate}/history` | 读取连续 revision 与当前 head；不自动选择 |
| `GET` | `.../visual-review/candidates/{candidate}/history/{revision}/{decision}` | 读取一个精确历史 decision |
| `PUT` | `.../visual-review/candidates/{candidate}/decisions` | 以 CAS 追加一个完整 decision |

所有响应都是 path-free；PNG 响应带由其 SHA 构成的 `ETag`。mutation 必须来自完全相同 authority 的 loopback 页面，并发送 `Content-Type: application/json` 与 `X-Autospine-Intent: body-sway-visual-review`。服务不会为跨端口 origin 放宽 CORS。

每个新 revision 返回 HTTP 201；字节相同的幂等重试返回 200；过期或跳号基线返回 409，并给出 requested/current revision 与 head SHA。客户端收到 409 后必须废弃旧历史与基线、重新读取 exact history，再让用户显式确认新 head；不得静默重放旧决定。

## 历史与 CAS 语义

- candidate 与 decision 分开保存；算法、capture 或浏览器 profile 变化会生成新 candidate SHA，旧决定不会静默复用。
- revision 从 1 开始、严格连续，最多 64 个。每个 slot 和内容寻址 decision 都是 write-once；读取会重放完整前驱链。
- `prepare`、candidate GET、history GET 和历史详情 GET 都是零写入。
- 只有提交会在通过 authoritative capture/candidate replay 与 CAS 后发布 candidate，并追加 decision revision。
- `sampled_visual_approved` 要求全部 case 都是 `approve`；任何 `reject` 或 `unobservable` 都会得到 `sampled_visual_rejected`。

## 已知限制与后续门禁

P10.3 视觉复核不能证明：

- 离散采样之间的连续时间安全；
- 未标注 attachment 接缝在所有姿势都安全；
- 人工幅度已形成可复用的安全范围；
- preview-only timeline 已成为 MotionInstance v3 或可发布 runtime timeline；
- 未采样姿势、其他角色或其他 Spine runtime 版本具有同等效果。

因此 sampled approval 后仍保留 `continuous_time_safety_unproven`、`preview_only_timeline`、`reviewed_seam_anchors_missing` 和 `safe_range_unproven`。出现 reject/unobservable 时还会加入 `sampled_visual_review_rejected`。眨眼、口型和头发弹簧仍不在这条 body-sway 视觉复核链内。

开发者在修改前端或 HTTP 适配器后，至少运行：

```powershell
npm test --prefix web

$env:PYTHONPATH = 'src'
python -B -m unittest `
  tests.test_body_sway_visual_review_http `
  tests.test_body_sway_visual_review_http_security `
  tests.test_p10_visual_review_cli `
  tests.test_quality
```

完整回归仍使用 `python -B -m unittest discover -s tests`。真实官方 runtime smoke 需要额外的已授权 runtime 环境，缺少它时相关测试会跳过，而不是由 stub 结果替代。
