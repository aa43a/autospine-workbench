# M4 当前策略固定回归

本轮使用 [计划 v3](benchmark/m4-cohort-plan-v3.json)，重新执行 Alice、辉夜、红美铃与八类动作的 24 个组合。角色工件、原始动作字节和正面完整动作范围与 [旧基线](m4-fixed-baseline-results.md) 一致，复用已经验证的源导入任务。侧面行走试验单独保留，不替换本轮的正面行走。

固定执行策略：

- 支撑：`external-phase-contact-auto-v1`，先尝试全段静止支撑，再尝试源证据合格的局部支撑区间。
- 遮挡：`external-arm-torso-depth-overlap-v2`，原生 alpha 重叠检查与受保护的绘制顺序候选。
- Runtime 参考：`spine43-linear-weighted-float32-storage-v1`。

每个成功任务必须与计划中的策略一致，否则编排停止并保留任务记录。报告绑定具体候选身份；不能将旧候选的综合检查作为新候选的证据。旧基线的失败不被本轮覆盖，也不自动重试失败项。

从仓库根目录运行：

```powershell
python -X utf8 -u tools/m4_motion_cohort.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json --steps 1000
python -X utf8 tools/m4_motion_cohort_report.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/cohort-current-policy.html
```

第二条命令生成当时的快照，不是自动更新的仪表盘。第一条命令可从精确任务 ID 恢复；遇到不确定的提交标记时，先核对服务端是否已经接收，不能盲目重复提交。锁文件用于避免多个编排器同时提交。

维护时可创建状态文件同名的 `.stop` 文件（本轮为 `cohort-state-v3.stop`）。编排器在下一步边界退出并释放锁，不取消服务端已经提交的任务。确认这些任务结束后再重启服务；删除 `.stop` 文件后用原命令续跑。不要将停止提交等同于停止捕获，也不要因为观察超时而重建正在运行的任务。

报告分别展示任务、候选、综合检查、几何、Runtime 帧数、接触、遮挡和人工视觉状态。部分支撑区间修正成功不代表整段接地通过；Runtime 捕获完成也不代表几何和遮挡通过。人工阶段验收仍需针对本轮精确候选进行，不能继承原角色基础动作的验收。

本轮 24 项均已结束并完成捕获，共 11,334 帧，11 项几何通过；24 项仍有技术异常，0 项满足全部既定技术门禁。2026-09-21 的只读阶段记录核对未发现本批候选的人工接受记录。这些数字说明固定流程已经执行完毕，不代表 24 类组合均受支持。M4 尚未完成。

最新核对快照为 `../tmp/m4-motion-center/cohort-m4-audit.html`，阶段记录时间为 `2026-09-21T02:56:55.883049+00:00`。本次重新读取了精确候选的阶段证据，没有重新捕获这 24 项动画。侧面 12 项和偏转 12 项仍是独立补充矩阵，不替换正面失败项。

动作中心的任务轮询现在保留未变化的任务卡、已展开检查和键盘焦点。候选身份或任务状态变化时才替换对应卡片，避免沿用旧候选检查；后台其他任务运行不会再清空正在阅读的报告。可用 `node tools/check-motion-polling.mjs http://127.0.0.1:8918` 执行只读浏览器回归；需要 Playwright（也可通过 `PLAYWRIGHT_MODULE` 指定模块）。测试采用浏览器内拦截的任务样本，不提交或修改真实任务。
