# 真实角色原贴图回交回归

2026-09-25。父任务 `motion-744b6a402ba546c783b50cc871a653d5`，Alice，父 artifact `24a39f6e66829e2595bb90c1461d755f531be1c45df0cf1a1cb83b37ae007b23`。

使用父候选 `layer-004-depth-001` 的原始 RGBA 贴图与 0.1 秒原网格坐标，创建 `[0.05, 0.15)` 新附件切换候选。此测试用于验证真实多附件角色的图片、对应、构建和 Runtime 运输链路；没有绘制新侧面，也没有将原有失败姿态标为修复。

可重复工具：`tools/m4_view_handoff_regression.py`。仅接受没有活动干预草稿的父候选；中途恢复必须与保存的 draft 完整相符；已有 submitted.json 时拒绝再次提交。通过正式候选 ZIP 下载骨架，使用同源 API 保存有明确回归说明的草稿并提交。

本次草稿 revision 3，子任务 `motion-00696eeedad848029806096960447241`。输出位于 `localset/tmp/m4-motion-center/view-handoff-real-v1/{draft,handoff,submitted}.json`。截至本次记录，API 和子进程均确认任务仍运行，步骤 post_contact_repair；尚无 Runtime 结论。下次应继续观察该任务，不能因本轮结束创建替代任务或声称通过。

等待期间补充新视角 worker 的显式失败码白名单，保留对应折叠、姿态翻转、来源不匹配等原因；任意日志或未列入的 view 消息仍不外传。关键原因增加中文调整提示。2 项失败边界测试、23 项活动附件/几何/深度/存储与候选测试通过。

## 采样复制开销

后续检查确认 worker 仍有 CPU 活动，未因状态重复而中断或重建。活动附件采样原先每帧深复制完整动画后又丢弃整段 deform，改为只复制归一化后仍需要的字段；公开的 normalized document 仍独立于源数据，setup 采样只读共享静态数据。没有减少时刻、顶点或几何检查。

`tools/m4_active_sample_benchmark.py` 与提交 `2c2d1a5` 的旧采样器直接对照同一父 artifact。0.05、0.1、0.15 秒的完整返回数据严格相等；旧耗时分别 70.1、76.2、66.5 ms，新耗时 10.7、11.1、11.0 ms。原始结果在 `sampler-comparison.json`。这是三个 CPU 采样的性能证据，不是整段 Runtime 成功或整体提速比例。25 项相关测试通过，包含返回对象修改不会污染源候选的检查。当前已运行 worker 不重启，优化用于后续执行。

进一步观察同一任务已到 publish_candidate，尚未得到 Runtime 结论。补齐模板 HTTP 入口的明确错误传递：仅白名单内 ValueError 返回具体原因，其他异常仍返回通用错误，防止文件路径或任意异常文本泄漏。4 项路由与 worker 错误边界测试通过；服务须在活动任务结束后更新。

## 首次完整运行超时

首个任务最终以 motion_decode_timeout 失败，进程已退出。已保存 candidate 为 `240381c4c04ce43d8bb5cb13ddfd5bb756e8b934c48e2bf9ad3045383c187fba`；官方 Runtime 尚未执行完成。保留 900 秒原上限，不以超时为由降低检查或认定通过。

`tools/m4_verify_view_transport.py` 对已保存候选验证：原 PNG 字节、骨骼、槽位不变；2,106 个原检查时刻全部保留，新候选 2,234 时刻，其中 46 时刻按 float32 切换边界使用新附件。原时刻最大顶点差异 7.734013369741614e-7 px，小于 1e-6 px；几何仍失败，selected=false。报告 `transport-verification.json`。这不是官方 Runtime 证明，只是候选运输不变量检查。

下一次从同一材料通过正式 retry 创建独立子任务，使用 30c83fc 的采样复制优化，仍保留旧超时记录及原 900 秒任务上限。
