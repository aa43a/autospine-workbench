# 当前导入、生成来源与下载核对

2026-09-28 恢复工作台后，对历史真实任务做只读核对，未重新导入、
运行生成模型或捕获动画，未新增人工验收。

| 项目 | 本轮直接证据 | 结果与边界 |
| --- | --- | --- |
| FBX | 299 帧、53 关节；源字节、桥接报告、预览及 MotionIR 包重现 | 与原记录一致；只覆盖已声明 Mixamo 映射 |
| BVH | 299 帧、53 关节；源字节、预览及 MotionIR 包重现 | 与原记录一致 |
| SOMA77 NPZ | 120 帧、77 关节；源字节、预览及 MotionIR 包重现 | 与原记录一致；不推断未知骨架约定 |
| 两次真实 Kimodo 生成 | 原始 NPZ、逐数组摘要、请求与环境记录、当前预览 | 参数相同、输出相同；两次环境并不完全相同，runner 与 layout_builder 摘要不同，分别保留 |
| 生成结果 → Alice 下载 | 当前接口、精确候选身份、完整 ZIP 与保存包逐字节比较 | 97 文件一致；ZIP 摘要仍为 `e43dfc10fcc2b7b763dca180f02a650dd9211cb3b3223d2b3c2384d4edd1a139` |

生成候选 `motion-27303356132f4a4bace5ed864ccdb2f6` 的已有 375 帧
Runtime 证据仍匹配当前包。实际捕获 Runtime 版本为 4.3.13，导出目标为
Spine 4.3.26，不将两者写成同一版本。已有投影、几何、接触采样通过，
遮挡仍有 120 条失败记录（第一条为 0 秒 layer-003 / layer-006 的
visible_depth_straddle）。没有当前人工阶段接受，整体仍是 needs_changes。

原始核对文件位于 `tmp/m4-current-delivery-audit-20260928/`：

- `three-format-intake.json`：三格式当前 API、原始源文件与不可变编译包。
- `generation-provenance.json`：两次生成的真实来源记录与输出比较。
- `generated-alice.json`：当前下载、请求、角色、动作及 Runtime 证据身份。

复查入口为 `tools/m4_intake_identity_audit.py`，引用既有
`docs/benchmark/m4-process-owner-deployment-v1.json`，只读取旧任务。
生成来源与下载分别复用 `m4_generation_replay_check.py` 和
`m4_verify_online_cohort.py`。输出使用独立新路径，旧证据不覆盖。

三角色八类动作的全量支持范围核对另在执行；本记录不代表全部动作支持，
也不替代当前取消/恢复操作的独立证据及视觉阶段结论。

## 当前服务与生命周期复核

随后读取当前 `/api/motions`：FBX/BVH/NPZ 三格式入口可用，Blender
来自服务端 state_config 且 configured，Kimodo 环境为 configured。
该检查时未列出 pending/running 生成或适配任务；外部只读范围核对进程
仍在执行，两类任务不能混为一谈。保存于同目录 `service-capabilities.json`。
配置可用不代表新模型推理已执行，本轮没有据此新增生成质量结论。

在当前代码上运行 `test_motion_generation_lifecycle`、
`test_motion_generation_activity`、`test_motion_generation`，共 13 项通过。
其中 Windows 集成测试以实际进程句柄确认测试子进程先存活、后终止：
显式取消、正常关闭、只强制结束管理器后的后代终止与中断恢复，
以及进程归属建立失败时工作负载不执行。重试保持旧请求和结果，新建身份。
模型工作负载被测试进程替代，不宣称这些测试执行了 Kimodo 推理。
测试全部使用独立临时目录，没有中断工作台或范围核对进程。
