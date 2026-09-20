# 三里程碑闭环核对（2026-09-20）

后续修复：本文发现的异常跨重建缺口已补上决定级连续性读取与显式解除回执；见 [异常保留规则](automatic-binding-audit.md)。新增测试覆盖连续重建、原决定改变、服务对象重启、解除后再次重建、再次报告错误及仅保存计时。下文保留发现问题时的核验记录，不再代表该缺口的最新实现状态。真实 Alice API 回读仍保留原 12 项正确判断及原回执地址，没有修改真实角色判断。

检查代码基线 `aef29d4`。本轮没有重新运行真实角色构建或 Runtime 捕获，没有增加人工判断。87 项针对性测试通过（155.249 秒）。以下将存储、算法、现有角色证据与待补工作分别记录。

| 要求 | 核验来源 | 结论与范围 |
| --- | --- | --- |
| 全源层覆盖、静态残余与缺失不冒充绑定完成 | `test_character_coverage`、`test_character_coverage_reader` | 通过；覆盖缺失分区、重复输出、显式排除及来源重放 |
| 袖装进入整角色并保留原始像素和骨架 | `test_character_sleeve_composition` | 通过；拒绝重复消费、非源像素、骨架和动作不兼容 |
| 自动策略不覆盖人工决定 | 头颈、头部、眼部、静态部件策略测试 | 通过策略支持范围内的人工保留及几何门槛；不是总体准确率证明 |
| 自动采用可撤销、来源冲突拒绝 | `test_simple_binding_policy`、`test_binding_auto_run`、`test_binding_auto_workflow` | 通过；真实注册存储中的撤销保留人工待办，较新的人工编辑不能被旧撤销覆盖；编排测试使用模拟提案 |
| 重建保留未变化的原区域确认及残余排除 | `test_final_binding_edit_replay`、`test_character_binding_replay` | 通过；纹理、几何、动作或来源变化拒绝沿用 |
| 默认归属与当前异常 | `test_character_auto_audit`；上一轮前端测试 | 未抽查不阻塞；当前任务的错误进入待办，不伪造正确标签 |
| 未修复异常跨重建保留 | `character_auto_audit.py` 与 `CharacterJobs.submit`；下述隔离复现 | **未完成**：任务身份变化会使原异常不再进入新任务的当前清单 |
| 固定三角色、多动作验收 | `fixed-three-workflow-2026-09-20.json` | 已保存快照 3/3、9/9，当前候选 Runtime 失败率 0%；非全部历史尝试 |
| 首批十角色、多动作验收 | `first-ten-audit-update-2026-09-20.json` | 已保存快照 10/10、30/30；仅 Alice 抽查于同日增量更新，其他证据未在本轮重扫 |
| 真实指标 | 同上；`test_project_work_sessions`、角色集评估测试 | 12/119 项已判断、0 项错误；抽查 84.909 秒。总体错误自动采用率及完整人工耗时仍未知，不能补造历史时间 |

## 已复现的异常连续性缺口

隔离临时存储中创建旧任务，保存一项 `incorrect`；新任务使用相同 artifact、相同图层和相同 `decision_sha256`，只改变 `job_id`。读取新任务返回 0 项错误、1 项未抽查，旧任务回执保持不变。复现脚本位于工作区 `../tmp/check-audit-rebuild-gap.py`；这是审计存储复现，不是官方 Runtime 端到端重建测试。

原因：异常历史保存在各任务的 `auto-binding-audit` 目录；当前读取只访问本任务目录，且 `verified_reviews` 要求任务身份一致。构建任务使用新 UUID。当前没有单独的未修复异常连续性记录。

下一项应建立可验证的异常沿用机制：引用原始回执，仅对仍有效且未改变的自动决定保留待办；真实绑定修正、显式撤销或纠正误报后才能解除。不同项目、来源失效和不同决定不能盲目继承。沿用异常不创建新人工正确标签、不重复累计抽查耗时，也不改写旧回执。需增加重建、无关层修改、真正修正、撤销及来源变化测试，并在工作台显示原异常来源。

## 本轮验证命令

`PYTHONPATH=src;tests` 下运行 `python -m unittest`，模块为：

```text
test_character_coverage test_character_coverage_reader test_character_sleeve_composition
test_simple_binding_policy test_head_anchor_policy test_head_binding_policy
test_head_parts_policy test_eye_neighborhood_policy test_pixel_head_anchor_policy
test_static_part_policy test_binding_auto_run test_binding_auto_workflow
test_final_binding_edit_replay test_character_binding_replay test_character_auto_audit
test_character_cohort test_cohort_workflow test_cohort_workflow_report
test_project_work_sessions test_quality
```

在补齐异常连续性之前，不宣称“仅异常复核”完全闭环。可选精度抽查仍不作为用户继续使用自动归属的前置条件。
