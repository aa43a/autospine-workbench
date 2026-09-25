# 真实 Kimodo 移动脚端候选

2026-09-26。在读取投影验证之外，实际调用通用角色构建函数，使用已验证 SOMA77 NPZ 来源 571428c04e573db828d89f0b5f646b4e36fcaebb947cb141629b38a0f7dbd2ff 和 Alice 整角色包。原视角、完整 120 帧片段，采用 absolute-projection-hip-center-temporal-v1 与 moving-source-ankle-timeline-v1，明确关闭静止接触校正，保留源接触标签用于测量。与旧 post-contact-timeline-v2 候选为不同策略，不声称精度优于旧策略。

独立候选 d7a597af7c864b82706ed54b42edaabbe5c3cd738f41603e39ae8cfa6824badb，脚端策略 applied=true，最终 749 个时刻峰值误差 0.000427566 px，门槛 3.531407336 px。官方 Runtime 749 帧检查通过，实际 4.3.13，目标 4.3.26。仍有一个几何失败附件及遮挡问题，状态 needs_changes，没有视觉接受。

这补齐本例 NPZ 从源观测到真实角色求解、最终测量及 Runtime 捕获的证据，不代表所有 Kimodo 动作或三结构泛化通过，也不是鞋底接地检查。输出在 tmp/m4-kimodo-moving-target/alice-v1，含独立 request、build、capture-result、verification 与 runtime 报告。没有修改原任务或用户决定，没有重新生成 NPZ；在线操作尚待服务更新。
