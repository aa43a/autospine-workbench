# 真实角色原贴图回交回归

2026-09-25。父任务 `motion-744b6a402ba546c783b50cc871a653d5`，Alice，父 artifact `24a39f6e66829e2595bb90c1461d755f531be1c45df0cf1a1cb83b37ae007b23`。

使用父候选 `layer-004-depth-001` 的原始 RGBA 贴图与 0.1 秒原网格坐标，创建 `[0.05, 0.15)` 新附件切换候选。此测试用于验证真实多附件角色的图片、对应、构建和 Runtime 运输链路；没有绘制新侧面，也没有将原有失败姿态标为修复。

可重复工具：`tools/m4_view_handoff_regression.py`。仅接受没有活动干预草稿的父候选；中途恢复必须与保存的 draft 完整相符；已有 submitted.json 时拒绝再次提交。通过正式候选 ZIP 下载骨架，使用同源 API 保存有明确回归说明的草稿并提交。

本次草稿 revision 3，子任务 `motion-00696eeedad848029806096960447241`。输出位于 `localset/tmp/m4-motion-center/view-handoff-real-v1/{draft,handoff,submitted}.json`。截至本次记录，API 和子进程均确认任务仍运行，步骤 post_contact_repair；尚无 Runtime 结论。下次应继续观察该任务，不能因本轮结束创建替代任务或声称通过。

等待期间补充新视角 worker 的显式失败码白名单，保留对应折叠、姿态翻转、来源不匹配等原因；任意日志或未列入的 view 消息仍不外传。关键原因增加中文调整提示。2 项失败边界测试、23 项活动附件/几何/深度/存储与候选测试通过。
