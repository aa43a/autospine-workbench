# 复核 P10.5b 静态接缝锚点

P10.5b 把一份精确 `SeamAnchorCandidates v1` 交给人工逐关系复核，并将
`accept`、`adjust`、`reject` 或 `unobservable` 保存为不可变线性 revision。
本阶段只记录静态 locator 选择，不生成 `ReviewedSeamAnchorSet`，也不证明动作中的
动态接缝、视觉质量、runtime 等价或发布安全。

## 前置条件

准备同一项目的四段精确地址：

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

打开 [http://127.0.0.1:8765/seam-anchor-review.html](http://127.0.0.1:8765/seam-anchor-review.html)，
填写四段地址并加载候选。页面不会发现 `latest`，也不会自动选择历史 revision 或提交
基线。

页面固定显示六条关系：左右 `torso_arm`、左右 `pelvis_leg`、左右 `leg_foot`。每个
option 都显示 contact evidence、父子 attachment、locator 与 anchor pairs；父子原始
PNG 由 candidate SHA、option ID、attachment ID 和图片 SHA 的完整地址读取，响应不
暴露本地路径。

对每条 `review_required` 关系：

1. 先显式选择一个 candidate option；
2. 选择 `accept`、`adjust`、`reject` 或 `unobservable`；
3. `adjust` 时编辑完整 anchors JSON，保留原 option evidence 身份；
4. `adjust`、`reject` 与 `unobservable` 必须填写关系备注。

对 candidate 已标为 `unobservable` 的关系，只允许提交 `unobservable`，且不能伪造
option。全部六条关系完成后，重新读取历史并显式选择当前 head 作为基线，再提交完整
revision。若另一窗口先提交，服务返回 `409`；页面保留草稿，但清除旧基线，必须重新
读取历史后再决定是否提交。

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

写请求必须来自与本地 `Host` 完全相同的 `Origin`，并携带
`X-Autospine-Intent: seam-anchor-review`。服务拒绝重复 JSON key、NaN/Infinity、错误
content type、分块请求和超过 2 MiB 的 body。图片响应带内容 SHA `ETag`，且不会接受
不属于该 option 的 attachment 或图片摘要。

本地服务器会在进程内缓存已经完整校验的 exact candidate/P3 图片快照，candidate 最多
4 项/16 MiB，图片 source 最多 2 项/128 MiB；超出字节预算的值仍可服务当前请求，但
不会常驻。revision 历史和 current decision 从不进入缓存，所以另一客户端提交后重新
读取会看到新 head。内容地址目录若被越过正常工作流直接改写，应重启本地服务器后再
继续复核。

## 如何解释结果

只有六条关系全部为 `accept` 或 `adjust` 时，decision 状态才是
`reviewed_anchor_set_ready_for_compile`。任何 `reject` 或 `unobservable` 都得到
`reviewed_anchor_set_blocked`。两种状态的 release gate 都保持 `blocked`：

- ready 只表示可以进入 P10.5c 编译；
- blocked 不会产生部分 reviewed set，也不会自动补 fallback；
- 历史 revision 永不被覆盖，但旧 head 不再具有 current-head authority。

decision 的机器合同位于
`schemas/seam-anchor-review-decision-v1.schema.json`。Python validator 还会在 schema
之外重放 candidate/P3，验证 option membership、locator bounds/mesh topology、双侧
主轴顺序与 connector 非相交。

## 运行阶段测试

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_seam_anchor_review*.py"

cd .\web
npm test
```

测试覆盖 prepare 零写入、相同/竞争并发提交、历史与 content-address 篡改、严格 HTTP
边界、图片 option 绑定、键盘操作、窄屏结构和 reduced-motion。

## 下一阶段边界

P10.5c 必须显式读取 `history A → exact decision → history B`，且两次快照一致、指定
revision 仍是当前 ready head，才允许编译不可变 `ReviewedSeamAnchorSet`。P10.5d 再把
该 set 与精确 P10.4b2 动作域组合；P10.5b 本身不拥有这两项权力。
