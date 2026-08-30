# 复核 P10.5b 静态接缝锚点

P10.5b 把一份精确 `SeamAnchorCandidates v1` 交给人工逐关系复核，并将
`accept`、`adjust`、`reject` 或 `unobservable` 保存为不可变线性 revision。
P10.5b 本身只记录静态 locator 选择；从 P9 package 进入且结果 ready 时，页面会在同一次
最终确认后继续 P10.5c，发布并精确读回 `ReviewedSeamAnchorSet`。两阶段都不证明动作中的
动态接缝、视觉质量、runtime 等价或发布安全。

样本 A 已完成这套流程：P10.5b revision 1 由操作者确认，P10.5c 静态 set 已发布并通过 exact
replay。除非候选或上游发生版本化变化，不要再次提交同一组六项决定；当前应转到
[身体摆动设置](http://127.0.0.1:8765/idle-behavior-review.html)，先关闭 P10.0/P10.1 与后续动作域。

## 前置条件

普通流程从 P9 成功或幂等复用回执点击“进入接缝复核”。链接只携带 exact
`package_id`；服务端重新读取该 package，闭合 Foot/Depth 共享的 P3 来源，精确复验 P3
bundle，并自动填入下列四段地址、加载候选和绑定 candidate namespace 的 current head。
浏览器不会拼接 SHA，也不会扫描 `latest`。

只有专业审计、历史排障或未登记 package 才需要手工准备同一项目的四段精确地址：

- `project_id`；
- `layer_manifest_sha256`；
- P3 `rig_sha256`；
- P3 `bundle_sha256`。

P10.5b 会从这四段地址重新编译 P10.5a candidate。candidate SHA、relationship
evidence SHA 与 option evidence SHA 都是决定的组成部分；任一算法或上游内容变化都会
产生新地址，旧决定不会被静默复用。

## 在独立页面复核

启动工作台：

```powershell
cd E:\proj\unusual\localset\autospine-workbench
.\run.ps1
```

正常情况下先在 P9 页面完成发布，再点击回执中的“进入接缝复核”。页面会自动加载当前
package 对应的四段地址、candidate、可观测性摘要和 current head；若存在 blocker，会在
顶部逐条显示，且不会生成 locator/image fallback。直接打开
[http://127.0.0.1:8765/seam-anchor-review.html](http://127.0.0.1:8765/seam-anchor-review.html)
时，可展开“专业模式”手工填写四段地址。两种模式都不会发现 `latest`；package 模式自动
把读取到的 current head 绑定为提交基线，手工地址模式仍要求操作者显式选择基线。

页面固定显示六条关系：左右 `torso_arm`、左右 `pelvis_leg`、左右 `leg_foot`。每个
candidate 响应包含一个 `setup_canvas`，以及每个父子 attachment 的 `canvas_offset_xy`、
`anchor_points` 和精确图片 URL。页面据此在统一 SVG 画布中合成 alpha 图：

- 青色表示 parent，紫色表示 child；
- 虚线框表示 contact bbox；
- 同编号圆点和连线表示一对 parent/child anchor；
- 原始 SHA、contact 数字、locator 表与父子单层图默认放在关闭的“技术详情”中。

图片仍由 candidate SHA、option ID、attachment ID 和图片 SHA 的完整地址读取，响应不暴露
本地路径。视觉合成只是帮助操作者理解同一份精确证据，不会改变 locator 或 evidence SHA。

页面加载后会应用版本化、确定性的 advisory assist：

| 证据情况 | 页面形成的草稿 | 人工边界 |
| --- | --- | --- |
| 只有一个完整 overlap option | 自动选择该 option，并形成 `accept` 草稿 | 可撤销；最终确认前零写入 |
| candidate 已证明不可观测 | 自动形成带原因的 `unobservable` 草稿 | 不生成锚点或 fallback，完整 P10.5c 将被阻塞 |
| 有多个可用 option | 只标出“建议重点查看”项 | 建议重点查看不等于批准；点击某个 option 才形成该项的 `accept` 草稿 |
| 证据不足以给建议 | 保持待处理 | 必须人工选择 action |

assist profile、候选顺序和量化指标都来自服务端响应；浏览器不根据图片亮度临时猜测。自动
填入、建议高亮、current-head 绑定和页面显示 `6 / 6` 都不是人工批准，也不会在后台提交。

对每条 `review_required` 关系：

1. 先检查合成 alpha、contact 框和编号锚点；
2. 唯一候选已由系统填入；多候选时点击认可的 option，该点击会同时形成 `accept` 草稿；
3. 需要覆盖时选择 `adjust`、`reject` 或 `unobservable`；
4. `adjust` 时编辑完整 anchors JSON，保留原 option evidence 身份；
5. `adjust`、`reject` 与 `unobservable` 必须填写关系备注。

对 candidate 已标为 `unobservable` 的关系，只允许提交 `unobservable`，且不能伪造
option。package 模式全部六条关系完成后，点击一次“确认复核并生成静态接缝集”：

1. 页面先以自动绑定的 base revision/head SHA 提交完整 P10.5b revision；
2. 若结果包含 `reject/unobservable`，只保存阻塞结论，不发布部分 P10.5c；
3. 若六条关系全部 `accept/adjust`，页面以同一个 `package_id`、candidate、revision 和
   decision SHA 调用独立 P10.5c publication；
4. 服务端重新读取 package/current decision，执行双历史快照，发布三文件 bundle，再从
   精确上游读回复验；页面只接受与本次 decision 完全一致的 path-free receipt。

若另一窗口先提交，P10.5b 返回 `409`；页面保留草稿，但清除旧基线，必须重新读取历史。
若 P10.5b 已保存而 P10.5c 失败，页面会明确显示“P10.5b 已保存；P10.5c 未完成”，此时只用
“仅重试生成静态接缝集”，不得再次提交六项人工决定。手工地址模式没有 P9 package，只会
保存 P10.5b revision；需要通过下方 CLI 或其他专业入口发布 P10.5c。

## 使用 CLI 准备候选

在仓库根目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path

python -m autospine_workbench prepare-seam-anchor-review <project-id> `
  --layer-manifest-sha256 <layer-manifest-sha256> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --state-root .\workspace `
  --document-only
```

`prepare` 会返回完整 canonical candidate 与有界历史快照，并保证 state tree 零写入。
历史为空时基线固定为：

```json
{
  "base_revision": 0,
  "previous_decision_sha256": null
}
```

## 提交一个 revision

准备 UTF-8 JSON。顶层只能包含：

```json
{
  "base_revision": 0,
  "candidate_sha256": "<candidate-sha256>",
  "previous_decision_sha256": null,
  "review": {
    "reviewer_id": "artist-01",
    "notes": "完整检查六条关系"
  },
  "decisions": [
    {
      "relationship_id": "seam.torso_arm.left",
      "relationship_evidence_sha256": "<relationship-evidence-sha256>",
      "action": "accept",
      "option_id": "seam.torso_arm.left.option.000",
      "option_evidence_sha256": "<option-evidence-sha256>",
      "notes": ""
    }
  ]
}
```

示例中的 `decisions` 必须扩展为固定顺序的六行；`final_anchors` 在 `accept`、
`reject` 和 `unobservable` 行中必须完全省略。提交：

```powershell
python -m autospine_workbench submit-seam-anchor-review <project-id> `
  --layer-manifest-sha256 <layer-manifest-sha256> `
  --p3-rig-sha256 <p3-rig-sha256> `
  --p3-bundle-sha256 <p3-bundle-sha256> `
  --submission .\seam-review.json `
  --state-root .\workspace
```

新 revision 返回退出码 `0` 与 `reused=false`；逐字节等价的重试返回同一 decision SHA
与 `reused=true`。旧基线返回退出码 `3`、当前 revision/head SHA 和稳定的
`seam_anchor_review_revision_conflict`，不会覆盖已存在的 slot。

## HTTP 精确资源

基础地址为：

```text
/api/projects/{project}/seam-anchor-reviews/{manifest_sha}/{p3_rig_sha}/{p3_bundle_sha}
```

| 方法 | 后缀 | 用途 |
| --- | --- | --- |
| `GET` | `/candidate` | 零写入编译 candidate 与图片证据引用 |
| `GET` | `/candidates/{candidate_sha}/history` | 读取有界线性历史 |
| `GET` | `/candidates/{candidate_sha}/history/{revision}/{decision_sha}` | 读取精确历史 decision |
| `GET` | `/candidates/{candidate_sha}/options/{option_id}/attachments/{attachment_id}/images/{image_sha}` | 读取 option-bound P3 原始 PNG |
| `POST` | `/candidates/{candidate_sha}/decisions` | CAS 提交一个完整 revision |

package 模式在 ready decision 后使用另一个写边界：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/motion-policy/review-packages/{package_id}/seam-publications` | 重放 package 与 current ready decision，发布 P10.5c，并返回 exact-readback receipt |

写请求必须来自与本地 `Host` 完全相同的 `Origin`，并携带
`X-Autospine-Intent: seam-anchor-review`。服务拒绝重复 JSON key、NaN/Infinity、错误
content type、分块请求和超过 2 MiB 的 body。图片响应带内容 SHA `ETag`，且不会接受
不属于该 option 的 attachment 或图片摘要。

P10.5c publication 使用独立 `X-Autospine-Intent: reviewed-seam-anchor-set-publication-v1`
和更小的严格请求，只接受 package/candidate/revision/decision 身份，不接受客户端路径或
Manifest/P3 地址。失败响应不会回滚已经提交的 P10.5b revision，也不会授权客户端重复提交。

本地服务器会在进程内缓存已经完整校验的 exact candidate/P3 图片快照，candidate 最多
4 项/16 MiB，图片 source 最多 2 项/128 MiB；超出字节预算的值仍可服务当前请求，但
不会常驻。revision 历史和 current decision 从不进入缓存，所以另一客户端提交后重新
读取会看到新 head。内容地址目录若被越过正常工作流直接改写，应重启本地服务器后再
继续复核。

## 如何解释结果

只有六条关系全部为 `accept` 或 `adjust` 时，decision 状态才是
`reviewed_anchor_set_ready_for_compile`。任何 `reject` 或 `unobservable` 都得到
`reviewed_anchor_set_blocked`。两种状态的 release gate 都保持 `blocked`：

- ready 只表示可以进入 P10.5c；package 模式会在同一次最终确认后继续编译、发布和精确读回；
- blocked 不会产生部分 reviewed set，也不会自动补 fallback；
- 历史 revision 永不被覆盖，但旧 head 不再具有 current-head authority。

成功的 P10.5c receipt 会返回 `reviewed_set_sha256`、`bundle_sha256`、精确上游重放状态和
`compile_time` 双快照 head observation。它仍把动态接缝、runtime 等价和视觉接缝质量列为
blocked；receipt 不是发布许可。

decision 的机器合同位于
`schemas/seam-anchor-review-decision-v1.schema.json`。Python validator 还会在 schema
之外重放 candidate/P3，验证 option membership、locator bounds/mesh topology、双侧
主轴顺序与 connector 非相交。

## 当前 A/B 状态

- 样本 A（`seethrough_output`）已由操作者确认 P10.5b revision `1`。精确身份为 package
  `a933df26a457be609c6c30f08ad8ad0284ad2f2a02bd655163ebb6e7775764c0`、candidate
  `8b84858b1a723e20374892c0fc570385c8a23ff91b7398839af3218b67f21ff6`、decision
  `111d7da8589204e300b9aa8067b1f69baf938ca6f2cd715961b0b506fb55f680`。P10.5c reviewed set
  `47656c2510e98b7598937a2c3315cd8f6e05274162160cf11a07cc167ed0e4d9` 与 bundle
  `fb8886cf1dcbff5d0ccb1fc36c6a087d93ad4e87678169dbad435e9e30e1adbe` 已通过 exact replay。
  这些身份只证明静态 locator 链闭合。
- 样本 B（`seethrough_output_5`）的左右 `pelvis_leg` 与 `leg_foot` 四条关系由源证据判为
  不可观测。自动流程会保留这些 `unobservable` 草稿并在确认后保存阻塞结论，不会把它们改成
  `accept`，也不会发布完整六关系 P10.5c。

## 运行阶段测试

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_seam_anchor_review*.py"

cd .\web
npm test
```

测试覆盖 prepare 零写入、相同/竞争并发提交、历史与 content-address 篡改、严格 HTTP
边界、setup-canvas 图片/锚点投影、确定性 assist、一次确认后的 package publication、仅重试
P10.5c、图片 option 绑定、键盘操作、窄屏结构和 reduced-motion。

## 下一阶段边界

P10.5c 无论由 package 页面还是 CLI 触发，都必须读取
`history A → exact decision → history B`，且两次快照一致、指定 revision 仍是 current ready
head，才允许编译不可变 `ReviewedSeamAnchorSet`。样本 A 已取得该 exact receipt，但当前还没有
可供组合的 P10.4b2 动作域。真实顺序是 P10.0/P10.1 身体摆动候选与人工确认 → P10.2 →
P10.3a–P10.3c → P10.4a → P10.4b1 → P10.4b2 → P10.5d；P10.5b 自动草稿或既有静态 set 都不能跳过这些门禁。
