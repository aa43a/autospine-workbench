# ADR：Pipeline Profile v1

日期：2026-09-07。状态：合同已实现，已接入首个 region 预览编排器。

项目级 CLI 默认使用 `production_review`。旧 CLI、reader、算法 profile 与
内容地址继续原位保留；选择运行模式不重写旧工件，也不创建任何审核或发布凭据。

| Profile | 复核模式 | 导出约束 | 自动决定 |
| --- | --- | --- | --- |
| `draft_auto` | 候选预览 | 仅预览 | 无；候选不等于采用 |
| `production_review` | 异常队列 | 通过 QA 与独立发布门禁 | 必须使用另立版本的 policy_auto 合同 |
| `certification_exact` | 历史精确链 | 原有精确门禁 | 无 |

合同固定 `authority=none` 和 `artifact_identity=existing_content_addresses`。
`qa_gated` 是约束声明，不是 QA 通过结果。编排器不能仅因选择 production profile
就调用带发布权的入口。Certification 模式也不能跳过 Runtime 的显式授权。

JSON Schema 与无第三方依赖的语义 validator 均拒绝未知字段、跨模式拼接、
隐式类型转换与未知 profile。策略语义发生变化时必须另立版本。
输入质量示例中的 `manual_review` 属于建议复核行为，不是第四个运行 profile。

合同查看入口：在源码 checkout 中设置 `PYTHONPATH=src` 后执行：

```text
python -m autospine_workbench.automation.pipeline_profile
python -m autospine_workbench.automation.pipeline_profile draft_auto
python -m autospine_workbench.automation.pipeline_profile certification_exact
```

命令只输出合同 JSON，不访问项目、不写 state-root、不执行 Runtime。
未知模式返回退出码 2 与 `reason_code=unsupported_pipeline_profile`。

[PipelineRun v1](adr/pipeline-run-v1.md) 已引用本合同以及旧内容地址，状态持久化
与工件存储分离，支持幂等、取消、恢复和 current 漂移检测。setup-region Review Queue 已接入主工作台。
通用 pipeline 状态不复用 Runtime 的单次执行授权。
