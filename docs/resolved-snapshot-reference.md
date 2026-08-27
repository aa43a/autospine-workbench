# Resolved Project v1 参考

本文是面向 API、编译器和合同维护者的 Reference。它说明
`autospine.resolved-project/v1` 的结构、语义 validator、内容地址和版本边界。工作台的日常
保存步骤仍以[操作手册](operator-quick-guide.zh-CN.md)为准。

## 入口

| 用途 | 入口 |
| --- | --- |
| JSON Schema | `schemas/resolved-project-v1.schema.json` |
| 严格语义 validator | `autospine_workbench.resolved_snapshot_validation.require_resolved_snapshot` |
| 验证并返回 snapshot SHA | `autospine_workbench.resolved_snapshot_validation.resolved_snapshot_sha256` |
| Snapshot builder | `autospine_workbench.resolved_project.ResolvedProjectBuilder` |
| 语义测试 | `tests.test_resolved_snapshot_validation` |
| 可选 Schema 实例测试 | `tests.test_resolved_snapshot_schema` |

该能力没有独立 CLI 或操作页面。统一功能入口中心只展示可执行页面、CLI 和尚未实现的规划
能力；已完成的合同能力以本参考和[功能与入口参考](capability-reference.md)为准。

## 顶层合同

v1 顶层字段固定为：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 固定为 `autospine.resolved-project/v1` |
| `project_id` | 安全、稳定的项目标识 |
| `revision` | 产生该 snapshot 的 override revision，允许初始值 `0` |
| `inputs` | base project、override、可选 analysis 与候选分析身份 |
| `canvas` | 正尺寸、左上原点、Y 向下的统一画布 |
| `layers` | 应用图层 authoring 和 split 决定后的有效图层 |
| `skeleton` | 应用绝对坐标或候选决定后的 joints/bones |
| `qa` | 从 resolved 实体状态派生的复核清单与总状态 |
| `sha256` | 删除本字段后，对 canonical JSON 计算的 SHA-256 |

Schema 对顶层和 authority-bearing 子对象使用 `additionalProperties: false`。结构通过只说明字段
形状符合 v1；它不能替代跨引用、派生状态和内容地址检查。

## 语义 validator

最小调用：

```python
from autospine_workbench.resolved_snapshot_validation import (
    require_resolved_snapshot,
    resolved_snapshot_sha256,
)

require_resolved_snapshot(snapshot)
digest = resolved_snapshot_sha256(snapshot)
```

在 API 或 compiler 已经拥有可信上下文时，可额外固定身份：

```python
require_resolved_snapshot(
    snapshot,
    expected_project_id=project_id,
    expected_revision=revision,
    expected_base_project_sha256=base_project_sha256,
    expected_override_sha256=override_sha256,
)
```

validator 不读取外部目录，主要执行以下检查：

- 重新计算删除 `sha256` 字段后的 canonical 内容地址；
- 检查画布尺寸、有限坐标、bbox、唯一实体 ID 与 bone/joint 交叉引用；
- 检查 joint decision 的 action、最终坐标、review state 和 decision kind 是否一致；
- 要求被 joint decision 使用的 candidate artifact 出现在 `inputs.candidate_analyses`，并闭合
  provider、provider version、input/config/run identity；
- 检查 split decision 声明字段、algorithm、当前 split spec 与 current/stale 内部 binding；
- 从 layers/joints/split decisions 重新派生全部 QA ID 列表与 `ready`/`needs_review` 状态；
- 拒绝未知 authority 字段、非有限数、错误 SHA 和与可选可信上下文不一致的身份。

候选或 split artifact 原始字节，以及 split decision 声明的 `resolved_snapshot_sha256` 是否
指向真实外部工件，仍由各自 binder 负责。standalone validator 只验证这些 SHA 的形状、
snapshot 内部闭合及调用方显式提供的可信身份，不会按相邻目录、文件名或 `latest` 猜测外部
证据。`require_resolved_snapshot_for_project(...)` 属于严格 trusted-context 边界，因此必须同时
提供确切 override mapping；缺少 override 时 fail closed。

v1 的 canonical JSON 明确定义为 Python `json.dumps` 的 `sort_keys=True`、紧凑分隔符、
`ensure_ascii=False`、`allow_nan=False` 后的 UTF-8 字节。它不是 RFC 8785/JCS，也不会把
`100` 与 `100.0` 规范化为同一种表示；两者在 v1 中会产生不同 SHA。这个限制属于冻结的
v1 hash domain，不能原地修正。需要跨语言数值规范化时必须发布 v2。

## Provenance 与决定边界

`inputs.base_project_sha256` 和 `inputs.override_sha256` 固定基础输入与人工 revision。
`candidate_analyses` 是当前 joint decisions 实际引用的去重候选 provenance inventory；接受候选
不会反过来改变候选的 stage-scoped input identity。

Split decision 继续区分 `current` 与 `stale`。只有仍绑定当前 authoring、split spec、算法版本和
review target 的 accept 才能进入 `accepted_split_layer_ids`；stale 或 reject 必须保留在相应 QA
清单中，不能通过重新封装 snapshot 冒充 ready。

## 历史兼容与版本升级

P0 在正式冻结 v1 前修正了“撤销 split authoring 后 stale decision 从 QA 消失”的派生缺陷；
因此这类 pre-P0 临时状态重新生成时会得到修正后的 QA 与新 SHA。修正不会把旧决定静默标成
current。正式冻结点同时用历史回归确认下列已知真实 revision 的既有字节没有变化；本地存在
对应 See-through audit 与 override history 时固定：

- `seethrough_output` 的 `r000005.json` snapshot；
- `seethrough_output_5` 的 `r000007.json` snapshot。

测试会比较批准的完整 SHA；缺少真实 fixture 时会明确跳过，因此跳过不能写成当前环境已经
完成历史回归。

`autospine.resolved-project/v1` 的字段、哈希规则和语义已经冻结。未来只要 builder、QA 派生或
provenance 解释发生语义变化，就必须：

1. 新增 `autospine.resolved-project/v2` token；
2. 新增独立 v2 Schema 与 validator；
3. 保留 v1 的只读验证和既有 SHA；
4. 让下游通过显式版本能力选择 v1 或 v2，未知版本 fail closed；
5. 重新生成受影响的候选或决定，不能静默复用旧 binding。

## 测试

在仓库根目录运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest `
  tests.test_resolved_snapshot_validation `
  tests.test_resolved_snapshot_schema -v
```

Python 语义 validator 测试不依赖第三方包。Schema 文件的解析与固定身份检查也会运行；完整
Draft 2020-12 实例校验需要可选 `jsonschema`：

```powershell
python -m pip install -e ".[test]"
```

未安装该依赖时，实例测试会显示 `skipped`。只有测试输出确认实例用例实际执行并通过时，才可
声明完成 JSON Schema 实例验证。
