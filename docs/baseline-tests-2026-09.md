# 2026-09-07 checkpoint 测试报告

本次用户要求先提交项目，因此这是开发 checkpoint，不是稳定认证版本。
初始提交为 `4254151283d82b515934faf14d6d935e1e9a695a`；运行范围包含前序遗留
未提交 Runtime 执行链。测试日志保留在项目根目录，不纳入版本控制。

| 检查 | 结果 |
| --- | --- |
| 初始 Web 全量 | 390/390 通过 |
| Profile、质量、目录、Runtime 执行/恢复/manager/API 定向回归 | 76/76 通过，51.575 秒 |
| 更新目录后的 Web 全量 | 390/390 通过；同步修正旧“下一切片”断言 |
| Python 全量 `python -m unittest discover -s tests -v` | checkpoint 时仍在运行，尚无最终通过结论 |
| 官方 Runtime 新采集 | 未运行，仍 opt-in；stub 不计作官方 Runtime 证据 |
| 稳定认证 tag | 未创建 |

初次质量门禁发现 reader/runner/test 三个遗留超长文件；提取纯校验与测试辅助
代码后定向质量门禁通过。未放宽任何行数阈值。

全量进程早于本轮改动启动，部分模块已预加载旧实现。因此即使最终通过，
仍需结合变更后的 76 项定向测试解释，不宣称它覆盖最终提交的所有字节。
未来冻结前应对最终静止 checkout 再跑一次完整基线。

只读 [golden 清单](certification-baseline-inventory-2026-09.json) 保存 23 个已跟踪
golden 文件和 pilot 身份记录的工作区/提交 SHA。它不等同于 A/B 当前完整工件链重放。
`matches_committed_bytes=false` 需要区分 checkout 换行与语义漂移，不据此重写 golden。

日志：`baseline-python-2026-09.log`、`baseline-focused-2026-09.log`、
`baseline-web-2026-09.log`。后续将补录全量汇总与 skip/failure 分类。
