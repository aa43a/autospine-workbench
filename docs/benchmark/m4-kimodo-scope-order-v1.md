# Kimodo 实际候选的覆盖区与顺序链验证

2026-09-26。读取已验证 Kimodo SOMA77 NPZ 候选 31db6e1a03724175493680a8b93f80ecd29c48184d3071632fdf8d1fe16b707d，在独立目录 tmp/m4-kimodo-scope-order/alice-v1 执行覆盖区分区，再执行 0.5–1.5 秒的局部顺序调整。选取 layer-004 三角形 0 只是执行链诊断，不代表用户归属或推荐动作处理，不写入在线草稿。

新包 64540c406332c352c9614107c20ddb42f72d4b939dc6ea73335f90a4370c83cb 完成 2,106 帧官方 Runtime 检查，实际 Runtime 4.3.13、目标 Spine 4.3.26。两次构建的几何均未通过，最终一个附件记录仍失败，四项继承问题保留，状态 needs_changes。旧来源没有移动脚端独立报告，继续缺失，不将该项计为验证通过。

已查看实际捕获 external-motion-1024.png：抬臂动作可见，肩侧白粉色边缘散点与不自然袖部形状仍存在。该验证说明后处理可以消费本例真实 NPZ 候选，不证明视觉质量改善，不替代三结构八动作覆盖，也未验证 Kimodo 移动脚端新策略。

目录包含 plans.json、build.json、verification.json、runtime/report.json 及截图。没有重新生成 Kimodo 动作或继承原视觉接受。机器结果见同名 JSON；生产服务仍未重启，在线提交和下载另行验收。
