# 真实 Kimodo 取消、独立重试与记录恢复

2026-09-26。通过生产 MotionIntakeJobs、generation submit/worker 和 Windows 工作进程隔离，在独立 state 目录执行真实模型任务，无模拟模型或网络服务。8918 服务未操作。

参数：1 秒轻呼吸、seed 20260926、10 diffusion steps、正面。原任务 motion-1183cdb7e7814df2bbe1fa582b9d537b 到 generate_motion 且已有真实日志后请求取消，最终 canceled，工作进程 poll 确认退出。随后 retry 创建 motion-11ed20dae8854cc2af15f9b52b475727，同参数、独立目录，retry_of 绑定原请求摘要；最终 succeeded。

旧 request/result 字节保持一致。新任务生成 NPZ 并编译 MotionIR，VerifiedMotionBundleReader 重新核对全部来源身份，NPZ SHA 为 4cfccbfc86abac41f52db7f760fd198255db7d78bc31c7c30cee8f65fde54645。新任务记录模型环境和生成参数摘要，预览重新打开后内容一致。新管理器从磁盘恢复两任务状态为 canceled/succeeded。

这是真实模型和进程管理链验证；重试从头生成，非模型断点续算。未测试服务崩溃瞬间、不宣称所有孙进程逐 PID 独立观察，也未覆盖在线按钮至 HTTP 全链。进程树隔离由生产 Windows Job Object 机制执行。输出未适配角色，不增加三角色八动作的通过数。

结果：m4-real-kimodo-lifecycle-v1.json。隔离目录：tmp/m4-kimodo-lifecycle-v1。复现工具：设置 PYTHONPATH=src，运行 `python tools/m4_kimodo_lifecycle_probe.py <全新输出目录> --workspace <localset目录>`；会真实运行本地模型并保留全部记录，已有目录拒绝覆盖。
