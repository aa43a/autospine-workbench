# 分析工件与只读 API 参考

本文定义 P1 pose/geometry/candidate 工件的发布关系和 HTTP 读取边界。生成步骤见 [生成并复核四肢候选](how-to-run-pose-alpha.md)，人工决定语义见 [候选关节决定参考](candidate-decisions-reference.md)。

## Provenance 链

`pose-geometry` 先验证全部文档和跨文档 fragment，再按以下顺序发布：

```text
pose-observations/<pose-sha>.json
        ↓
alpha-geometry-evidence/<geometry-sha>.json
        ↓
joint-candidates/<candidate-sha>.json
```

每个文件名都是其 strict canonical JSON 的 SHA-256。发布是逐件原子的 provenance-safe 顺序，不是跨三个目录的事务；失败时已完成的不可变上游可复用，下游不会出现。

候选中的 geometry 引用固定为：

```text
alpha-geometry-evidence:<geometry-sha>#layers/<layer-id>
alpha-geometry-evidence:<geometry-sha>#layers/<layer-id>/components/<component-id>
alpha-geometry-evidence:<geometry-sha>#paths/<path-id>
alpha-geometry-evidence:<geometry-sha>#contacts/<contact-id>
```

`layer_alpha` 可引用 layer/component 或 path，`kinematic_residual` 只能引用 path，`contact_geometry` 只能引用 contact。发布前 validator 会确认 SHA、section 和目标 ID 都存在。

结构合同见 [alpha geometry evidence v1](../schemas/alpha-geometry-evidence-v1.schema.json) 与 [joint candidates v1](../schemas/joint-candidates-v1.schema.json)；服务端还执行 schema 无法表达的内容地址和跨引用语义检查。

## HTTP 端点

所有端点只读，`{sha256}` 必须是 64 位小写十六进制完整内容地址；没有 `latest` 别名。

| 方法 | 路径 | 响应 |
| --- | --- | --- |
| `GET` | `/api/projects/{id}/candidate-artifacts` | 候选工件索引 |
| `GET` | `/api/projects/{id}/candidate-artifacts/{sha256}` | 完整 candidate v1 文档 |
| `GET` | `/api/projects/{id}/geometry-evidence` | geometry 工件索引 |
| `GET` | `/api/projects/{id}/geometry-evidence/{sha256}` | 完整 alpha geometry evidence v1 文档 |

候选索引项包含 artifact/provider/input/config/run SHA、QA、关节/候选数量和 method counts。geometry 索引项包含对应 identity、QA、layer/path/contact 数量、relation counts 和 observability counts。

读取边界会拒绝 symlink、重复 JSON key、NaN/Infinity、超过 4 MiB 的单件、内容与文件名 SHA 不一致、错误 project ID 或语义 validator 失败。索引最多读取 256 件、合计 64 MiB；任一损坏条目会使索引 fail closed。

## 错误语义

| HTTP | error | 含义 |
| ---: | --- | --- |
| `404` | `candidate_artifact_not_found` | 候选 SHA 非法或工件不存在 |
| `404` | `geometry_evidence_not_found` | geometry SHA 非法或工件不存在 |
| `500` | `analysis_repository_error` | 本地工件损坏、越界或未通过语义验证 |

响应使用 `Cache-Control: no-store`。服务只允许 loopback Host；这些端点不会触发姿态模型或在线分析。
