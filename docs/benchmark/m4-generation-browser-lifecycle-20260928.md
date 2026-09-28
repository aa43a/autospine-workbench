# Kimodo 网页生成、取消、重试及重新打开实测

2026-09-28 在运行中的 8918 工作台通过真实 Chrome 按钮操作，
没有模拟 API 或模型。开始前确认没有 pending/running 动作任务，
只操作本次新建的两个任务，没有重启服务或修改角色候选。

参数：`A person stands still and breathes gently`，1 秒，10 步，
seed 20260928，正面。完整实测工具为
`tools/check-m4-generation-lifecycle.mjs`。

1. “生成动作”创建 `motion-6ece79a30df04d939613fc616781d282`。
   API 确认进入真实 `generate_motion` 并有日志；页面显示当前阶段、
   持续时间、日志更新情况和取消按钮，没有虚构完成百分比。
2. 点击该卡片“取消任务”，最终状态为 `canceled`。
3. 重新加载页面后，点击“重新生成动作（保留旧记录）”，得到新身份
   `motion-6fabae462531459ab74cdce05334d604`，页面自动定位新任务。
4. 新任务经过模型校验、生成、输出复查及 MotionIR 编译，最终 `succeeded`。
   旧任务完整 API 记录与取消后保存值一致，重试来源绑定原请求摘要。
5. 再次加载页面，点击新任务“查看源动作”，实际时间轴定位到
   `0.47 秒 · 帧 15`。页面脚本错误为空。

随后使用生产 `VerifiedMotionBundleReader` 重新读取 MotionIR 包，
核对原始 NPZ 与新任务源摘要、在线预览、生成环境、生成请求及重试关系。
各项通过，NPZ SHA256：
`f3d0dca13855260d99541f9ccadd118cccac47358d1fa832acb54f1ed50bfc1e`。
两个请求的生成参数相同，原任务请求摘要与 retry_of 一致。

证据目录：工作区 `tmp/m4-generation-browser-20260928/`，包含
`report.json`、`running.png`、`reopened.png`、`source-check.json`。
任务及原始生成文件保留在正常工作台记录中，便于继续查看。

边界：本轮重开指浏览器页面重载，不宣称新做了服务崩溃恢复。
服务关闭/中断恢复另见真实 Windows 生命周期测试和独立模型恢复记录。
取消在模型运行阶段发生，不以“取消已完成任务”替代测试。
没有将这条新源动作适配角色，不增加三角色八动作的视觉通过数；
之前已验证的生成 → Alice → Runtime → 下载链保持独立证据。
