# 生成任务活动刷新焦点回归

2026-09-26。此前 generation activity 每秒变化进入整卡签名，轮询会反复替换卡片。现使用独立活动更新回调，只有生命周期、阶段或上下文变化才重建卡片。

内置浏览器实际操作 `http://127.0.0.1:8918/tests/motion-activity-focus.html`：启动检查后执行 10 次定时活动更新，结果 stable=true、focused=true、builds=1，活动按钮为“取消模拟任务”。随后实际点击该按钮，显示“已取消”，构建次数为 2。页面使用真实 reconcileMotionJobs 与 generationActivity 模块，所有任务数据仅在内存中，没有模型进程或服务写入。

这验证 DOM 保留、焦点和取消控件事件，不证明真实子进程停止、后端新活动字段上线或完整 Kimodo 恢复完成。对应无浏览器回归工具为 tools/check-motion-job-reconcile.mjs；状态文案回归为 tools/check-motion-job-status.mjs。
