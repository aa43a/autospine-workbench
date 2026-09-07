# 独立 checkout 基线：2026-09-07

本报告针对固定提交的完整跟踪源码测试，不代表 A/B current 链封存、官方 Runtime
执行、素材验收或发布认证。本次没有创建稳定标签。

被测提交是预览/编辑器导出切片，早于后续 Benchmark 提交 `3117379`。后者由独立的
40 项定向测试补充验证；本次完整 suite 不覆盖它及此后改动，不能概括为当前 HEAD 全量通过。

## 固定输入

- 提交：`2cb411f2b76fee0cac592f60dd41d16af6728e8e`。
- Git tree：`70f8c7e64641fba65980e701c7a31d2a9e98ca13`。
- 独立 detached worktree：`../tmp/certification-core-2cb411f`。
- 建立方式：`git worktree add --detach ../tmp/certification-core-2cb411f 2cb411f2b76fee0cac592f60dd41d16af6728e8e`。
- 2090 个跟踪文件均存在；按 Git 属性规范化后逐文件 blob 身份与 HEAD 一致。
- 测试前 `git diff --exit-code HEAD` 返回 0；未将活跃工作树改动混入快照。
- 测试结束后再次确认同一 HEAD/tree；跟踪文件 diff 和状态均为空。

测试日志放在 checkout 外的 `../tmp/`，不改动被测跟踪源码。没有复制、链接或
重定向真实生产 `workspace`、PSD/PNG 素材或历史 audit。需要这些未跟踪输入的
测试自行 skip，具体结果以完整日志为准。没有设置 Runtime opt-in 开关。

## 测试结果

时间均为 Asia/Shanghai（UTC+08:00）。

| 范围 | 命令 | 环境 | 结果 |
| --- | --- | --- | --- |
| Python | `python -m unittest discover -s tests -v` | Python 3.14.3 | 3377 项：3358 通过、19 skip、0 失败/错误；退出码 0 |
| Web | `npm test --prefix web` | Node 20.20.0 / npm 10.8.2 | 405 通过，0 失败，0 skip；退出码 0 |

Python 于 `2026-09-07T20:11:40+08:00` 启动，`20:42:54+08:00` 完成，unittest
报告耗时 1870.388 秒（约 31 分 10 秒）；日志为
`../tmp/baseline-frozen-2cb411f-python.log`。Web 于 `20:11:54+08:00` 启动，
`20:11:55+08:00` 完成，测试 runner 报告耗时 502.6177 ms；日志为
`../tmp/baseline-frozen-2cb411f-web.log`。

## 19 项 skip 的边界

| 原因 | 数量 | 涉及范围 |
| --- | ---: | --- |
| 隔离 checkout 没有真实 audit/素材 | 6 | actual audits 2、actual geometry/limb/pose 各 1、历史 resolved snapshots 1 |
| 未开启真实历史 golden opt-in | 5 | P3 Mesh、P4 IK、P5 Motion、P6 Spine、静态 seam 各 1 |
| 未开启真实样本 gate opt-in | 5 | dynamic seam A/B 2、reviewed seam set A/B 2、双样本 readiness 1 |
| 未提供真实浏览器/官方 Runtime opt-in | 3 | licensed Runtime smoke 2、real Chrome smoke 1 |

这些 skip 不等于通过。固定 checkout 的绿色结果证明上述提交在已执行测试范围内
通过，不能据此宣称 A/B current 已冻结，或官方 Runtime、视觉与发布认证通过。

## 后续提交的独立补充验证

以下结果由主任务在后续提交上单独运行，未混入本次固定 checkout 全量统计。

| 范围 | 提交 | 结果 |
| --- | --- | --- |
| Benchmark 新功能定向测试 | `3117379` | 40 项通过，11.908 秒 |
| 真实 P3/P4/P5/P6/SEAM opt-in 六模块 | `9de8a55d1e156b141567323a420841bcf3da351a` | 13 项通过，0 skip/失败，125.846 秒；退出码 0 |

真实历史重放日志为 `../tmp/benchmark-core-real-replay-2026-09.log`，明确记录被测
提交与启用的 P3/P4/P5/P6/SEAM 标志，没有启用 Runtime。B 四条不可观测负向边界
保持阻塞。上述定向结果不是后续 HEAD 的另一次完整 suite，也不代表 current
成功链已封存。认证标签仍须等 A 成功链清单与 B 负向工件按各自精确身份确认后再决定。
