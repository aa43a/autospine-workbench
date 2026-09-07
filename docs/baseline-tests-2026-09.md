# 2026-09-07 checkpoint 测试报告

本次用户要求先提交项目，因此这是开发 checkpoint，不是稳定认证版本。
初始提交为 `4254151283d82b515934faf14d6d935e1e9a695a`；运行范围包含前序遗留
未提交 Runtime 执行链。测试日志保留在项目根目录，不纳入版本控制。

| 检查 | 结果 |
| --- | --- |
| 初始 Web 全量 | 390/390 通过 |
| Profile、质量、目录、Runtime 执行/恢复/manager/API 定向回归 | 76/76 通过，51.575 秒 |
| 更新目录后的 Web 全量 | 390/390 通过；同步修正旧“下一切片”断言 |
| Python 原始全量 `python -m unittest discover -s tests -v` | 3258 项，1915.676 秒；3230 通过、14 error、1 failure、13 skip |
| 原始失败用例在最终代码逐项重跑 | 15/15 通过，23.476 秒；未覆盖或重写原始全量日志 |
| 官方 Runtime 新采集 | 未运行，仍 opt-in；stub 不计作官方 Runtime 证据 |
| 稳定认证 tag | 未创建 |

初次质量门禁发现 reader/runner/test 三个遗留超长文件；提取纯校验与测试辅助
代码后定向质量门禁通过。未放宽任何行数阈值。

全量进程早于本轮改动启动，部分模块已预加载旧实现。因此即使最终通过，
仍需结合变更后的 76 项定向测试解释，不宣称它覆盖最终提交的所有字节。
未来冻结前应对最终静止 checkout 再跑一次完整基线。

只读 [golden 清单](certification-baseline-inventory-2026-09.json) 保存 23 个已跟踪
golden 文件和 pilot 身份记录的工作区/提交 SHA。它不等同于 A/B 当前完整工件链重放。
本次 24 个文件的 `matches_committed_bytes` 全部为 true，未重写 golden。

日志：`baseline-python-2026-09.log`、`baseline-focused-2026-09.log`、
`baseline-web-2026-09.log`。原始失败逐项最终重跑日志为
`baseline-failed-recheck-2026-09.log`。

## Checkpoint 后的补充验证

- 冻结哈希与 golden 检查：17 项，12 通过、5 个真实重放 opt-in 跳过。
- 随后显式开启真实 P3/P4/P5/P6/seam 和 A/B 边界重放：13/13 通过（143.985 秒），相关测试确认 state 树未改变。
- 新增默认 A/B 历史边界回归：2/2 通过，直接复用原有 golden。
- 已定位并修复 Windows owner.lock 被测试快照读取时的 PermissionError；只对精确锁路径读取身份/元数据，其余文件仍逐字节，生产排他锁不变。
- Reader 凭据显式拒绝 copy/deepcopy/pickle；constructor假token与未登记对象仍 fail closed。
- 最终 HTTP/reader/owner lease/snapshot 回归 52/52 通过；其他直接快照调用方 44/44 通过；核心/profile/边界/质量/目录 18/18 通过。
- [20 PNG / 12 PSD 素材盘点](benchmark/intake-2026-09.md) 已完成，32 个源文件字节 SHA 与大小再次复核一致。

## 原始失败与跳过分类

原始 14 error：12 个旧 HTTP 快照直接读取 Windows owner.lock，1 个测试同时启动
同 state-root 的两个服务，1 个 reader 防伪测试仍假定凭据可 pickle。另有 1 failure
来自已过期的工作流“下一切片”断言。对应测试辅助逻辑、服务测试生命周期及凭据
不可序列化合同均已修正；从原始日志自动提取的全部 15 个失败用例最终重跑通过。

13 个 skip 中，P3–P6/seam 的 5 个真实 golden 与 2 个 A/B dynamic-seam 边界
已在独立 opt-in 重放中执行通过。其余为 2 个真实 reviewed-seam-set gate、1 个
真实 readiness gate，以及 3 个 Chrome/官方 Runtime smoke；没有把 skip 记作通过。

原始全量在开发期间运行，并非最终静止 checkout 的一次全绿运行。最终修复由
定向回归与全部失败用例重跑覆盖；`certification-core-2026-09` 仍待最终完整基线
与 A/B current 链封存。本轮仅提交开发 checkpoint 与补充修复。
