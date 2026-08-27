# Candidate-backed joint and split decisions reference

本文是 `autospine-workbench.override/v3` 中 `joint_decisions` 与 `split_decisions` 的机器语义参考。它面向 API、UI 和离线编译器开发者；人工操作步骤仍以工作台界面说明为准。v3 继承 v2 的 candidate-backed joint decision，并增加 bilateral split artifact 的人工决定。

## 数据流

```text
stage-scoped inputs → immutable candidate artifact → revisioned decision → resolved snapshot
```

候选工件位于 `<state-root>/analysis/<project-id>/joint-candidates/<sha256>.json`。决定只引用完整工件 SHA，不能只引用 provider run 或候选 ID。resolved snapshot 同时哈希 override 和去重后的候选 analysis provenance，因此能够重建某一 revision 使用的确切算法输出。

工作台通过只读 candidate index/detail API 枚举并校验工件；geometry-bound 候选再按引用的 SHA/fragment 读取固定 path、contact 或 layer/component 证据。端点与错误语义见 [分析工件与只读 API 参考](analysis-artifacts-reference.md)。

候选的阶段输入不包含最终 joint decision 或 resolved revision。否则接受候选会反过来改变生成该候选的输入身份，形成哈希环。有效图层语义、PNG、pose、provider 版本和配置仍必须进入候选的 stage-scoped input identity。

## 客户端动作

| action | candidate artifact | candidate ID | final_xy | reason | resolved 行为 |
| --- | --- | --- | --- | --- | --- |
| `accept` | 必需 | 必需 | 客户端禁止 | 可选 | 坐标只能从候选工件派生 |
| `adjust` | 必需 | 必需 | 必需 | 必需 | 使用人工坐标并保留来源候选 |
| `reject` | 必需 | 必需 | 禁止 | 必需 | 保留 setup fallback，关节仍 unresolved |
| `unobservable` | 必需 | 禁止 | 禁止 | 必需 | 显式记录不可观测，保留 setup fallback |

四类动作都绑定 `candidate_artifact_sha256`，表示决定针对哪次完整分析。`joint_overrides` 继续表示与候选算法无关的绝对人工坐标。一个 joint 不能同时出现在 `joint_overrides` 和 `joint_decisions`。

客户端接受候选示例：

```json
{
  "schema_version": "autospine-workbench.override/v3",
  "base_revision": 7,
  "joint_overrides": {},
  "joint_decisions": {
    "elbow.left": {
      "action": "accept",
      "candidate_artifact_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "candidate_id": "elbow.left.fusion.4aa35df3ca21"
    }
  },
  "split_decisions": {},
  "layer_overrides": {},
  "notes": "accepted after overlay review"
}
```

## 服务端派生字段

客户端不能提交 `analysis`，也不能为 `accept` 提交 `final_xy`。保存时 binder 安全读取内容寻址工件，验证 project、joint/layer 交叉引用、画布、run identity、candidate ownership 和内容 SHA，然后写入：

```json
{
  "analysis": {
    "provider": "pose-alpha-limb-fusion",
    "provider_version": "2",
    "input_sha256": "…",
    "config_sha256": "…",
    "run_sha256": "…"
  },
  "final_xy": [320.5, 410.25]
}
```

读取历史 revision 时会重新验证这些派生字段。工件缺失、内容被改写、候选属于另一关节、analysis 不一致或 accept 坐标不匹配都会 fail closed；不会退化成普通坐标 override。

## Bilateral split 决定

`split_decisions` 以原始 bilateral 图层 ID 为 key。客户端只能提交 `action`、完整 `split_artifact_sha256`，以及拒绝时的非空 `reason`：

```json
{
  "split_decisions": {
    "layer-012-sleeves": {
      "action": "accept",
      "split_artifact_sha256": "89abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234567"
    }
  }
}
```

| action | artifact SHA | reason | resolved 行为 |
| --- | --- | --- | --- |
| `accept` | 必需 | 可选 | 只有当前绑定仍有效时，左右 part 才能进入 resolved split layer |
| `reject` | 必需 | 必需 | 保留拒绝证据，不把该预览用于下游 |

保存时 binder 重新读取 split artifact，并验证 project、源图层、operation config、review target、Layer Manifest、resolved snapshot、split spec、算法 ID/版本和内容 SHA。服务端随后补充 `operation_config_sha256`、`review_target_sha256`、`analysis` 与 `binding_status`；这些字段不能由客户端伪造。

`binding_status=current` 只表示决定仍绑定当前 authoring 输入和算法。图层 split spec、resolved snapshot、manifest、operation config 或算法身份变化时，已保存决定会变为 `stale`，必须针对新 artifact 重新复核。普通图层/关节编辑保存时，前端必须原样保留未编辑的 split decisions；显式移除决定则从下一 revision 中删除它。

## QA 语义

- `requires_review=true` 的启发式骨架中，未作决定的关节始终进入 `unresolved_joint_ids`，高 heuristic score 不能替代复核。
- `reject` 进入 `rejected_joint_ids` 和 `unresolved_joint_ids`。
- `unobservable` 进入 `unobservable_joint_ids`，不伪造可见候选。
- `accept` 的 review state 为 `candidate_accepted`；`adjust` 与绝对人工坐标保留人工调整语义，但 `decision_kind` 区分其来源。
- 前端保存普通图层或关节修改时必须原样保留未编辑的 `joint_decisions`；手工拖动某关节会显式移除该关节的 candidate decision，转为绝对人工 override。
- `split_decisions` 中 stale 或 reject 项不会进入可编译的 resolved split；QA 必须保留相应待处理状态。

## 兼容策略

override v1/v2 历史可只读加载，并规范化为 v3：v1 得到空 `joint_decisions`，v1/v2 都得到空 `split_decisions`。旧 `joint_overrides` 被解释为算法无关的 `manual_absolute`，不会冒充对候选的 accept；旧版本也不能携带 split decision 或 split spec。下一次成功保存会向 append-only history 写入 v3 snapshot，不会原地修改旧文件。
