# 复核 P10.3c 官方 Runtime 采样帧

本文面向普通操作员，说明如何复核一份已完成的 P10.3 official Runtime execution。工作台会从完成的 job 自动带入精确证据地址；不需要选择文件或填写 SHA-256。

本流程只判断已经采样的 cases。即使全部通过，结果也只是采样画面获得人工认可；发布门禁仍保持 `blocked`。

## 开始前

必须先在 P10.3 采集页完成一次真实官方 Runtime job，并得到不可变 execution bundle。测试 stub、未完成 job 或零散截图都不能进入正式复核。

当前系统的 v2 review candidate、append-only history、decision 和 store 已实现，但样本尚未完成真实 Runtime 执行和人工视觉批准。系统不会自动生成任何人工决定。

## 1. 从完成的 job 进入

在 P10.3 采集页找到状态为“已完成”的 job，点击“进入视觉复核”。页面 URL 只携带完整 `job_id`；服务端从这个不可变 completed job 自动解析并重放：

- project；
- Preview v2；
- execution bundle；
- artifact set。

直达格式为：

```text
http://127.0.0.1:8765/body-sway-review-v2.html?job_id=<完整 job ID>
```

内部四段地址共同定位一份不可变 execution。工作台还会重新核对当前 Preview v2、CaptureFraming 和 P10.1 身份，避免旧证据静默套用到新决定。

若通过书签进入，页面必须包含完整 `job_id`。job 不存在、未完成、current P10.1/CaptureFraming 已变化或 exact replay 失败时，应返回采集历史重新打开；不要手工拼四段地址、从目录扫描或选择 `latest`。

## 2. 逐 case 检查画面

按页面顺序检查每个 case 的官方 Runtime 图像、采样时刻和证据摘要。重点查看：

- 角色是否完整可见；
- 身体摆动方向和幅度是否合理；
- 骨骼、附件和 draw order 是否异常；
- 肩、腰、髋及其他连接处是否出现裂缝或错误重叠；
- 该帧是否足以作出判断。

每个 case 必须由人选择：

- `approve`：该采样帧可接受；
- `reject`：观察到明确问题；
- `unobservable`：当前证据无法可靠判断。

`reject` 和 `unobservable` 必须填写原因。系统不会因为大多数 case 通过而替你批准剩余 case，也不会把 `unobservable` 当作通过。

## 3. 提交一个 revision

1. 确认所有 case 都已选择动作。
2. 填写复核人标识和必要备注。
3. 核对页面显示的当前 history head。
4. 点击提交，并在最终确认中确认本 revision。

decision history 是 append-only：

- revision 从 1 开始并严格连续；
- 同一候选最多保存 64 个 revision；
- 同一基线、相同字节的安全重试会复用原决定；
- 其他人先提交或页面基线过期时会产生冲突，必须刷新 history、重新核对 head 后再提交；
- 系统不会覆盖、改写或自动迁移旧决定。

候选算法、Preview、execution、framing 或 P10.1 任一身份变化，都会形成不同候选；旧人工决定不会静默复用。

## 4. 理解结果

- 所有 case 都是 `approve`：该候选得到 `sampled_visual_approved`。
- 任一 case 是 `reject` 或 `unobservable`：结果为 `sampled_visual_rejected`。
- 未完成或未提交：仍是待人工复核。

无论哪种结果，`release_gate.status` 都继续是 `blocked`。P10.3c 不证明连续时间安全、所有接缝安全、可复用安全范围或最终发布质量。

## 专家参考：精确地址与冻结 v1

v2 使用独立 namespace，并以四段地址读取 authoritative execution：

| 地址项 | 含义 |
| --- | --- |
| `project_id` | 项目标识 |
| `temporary_preview_v2_sha256` | package-centric Preview v2 身份 |
| `bundle_sha256` | official Runtime execution bundle 身份 |
| `artifact_set_sha256` | 本次 execution 的固定捕获集合 |

普通操作员不需要手填这些值。API/自动化客户端必须使用完整身份并接受 exact replay；不得扫描目录或回退到最新项。

旧 P10.3 v1 capture/review 合同已经冻结，只用于历史证据和回归。不要把 v1 capture bundle、v1 candidate 或 v1 decision 混入 v2 地址和历史。

## 本流程不包含

- 自动批准视觉质量；
- 用测试 stub 代替官方 Spine Runtime；
- 检查所有连续时间点；
- 自动证明 seam、遮挡或 draw order 在未采样姿势中安全；
- 解除发布门禁；
- 自动生成 MotionInstance v3 或最终 Spine 动画。

若采样通过，后续必须先实现独立的 P10.4a v2 admission/consumer 适配，才能进入 v2 幅度与连续安全工作。现有 `BodySwayReviewAdmission v1` 只消费冻结 v1 visual review，不能读取或替代 v2 head。若采样失败，回到绑定、动作参数、framing 或资产修正相应来源后，创建新的 Preview v2 和 execution，不要覆盖旧证据。

开发者修改 v2 复核合同时，应运行对应的 v2 candidate/history/decision/store 与 HTTP/UI 定向测试，并保留冻结 v1 回归。真实 Runtime 测试仍必须由有授权的操作者显式启动；测试通过本身不代表样本已被人工批准。
