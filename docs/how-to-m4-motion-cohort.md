# 固定外部动作验收

报告顶部现有紧凑的角色 × 动作矩阵，点击组合跳到同页证据与播放入口；下方按投影、几何、接触、遮挡、Runtime 统计采样通过、需处理和未知。缺失或未知状态不计通过，即使任务完成或 Runtime 帧数非零。JSON 同时输出 `stage_coverage`。该汇总不更改候选、自动采用或人工验收状态。

当前冻结基线使用 `m4-cohort-plan-v3.json` 和 `cohort-state-v3.json`；下方 v2 命令保留作历史重放。2026-09-21 读取 v3 已存证据得到 24 项、11,334 帧：投影 6/24、几何 11/24、接触 9/24、遮挡 0/24、Runtime 24/24 采样通过。全部组合仍有技术异常。本轮没有重新捕获 Runtime，没有读取新的人工视觉验收记录；这些数量不能证明任意动作范围受支持。

```powershell
python tools/m4_motion_cohort_report.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/m4-support-matrix.html
```

在动作中心已生成的角色任务卡片上点击“检查可用范围与待处理项”，可在原页面展开投影、几何、接触、遮挡、Runtime 的独立状态。异常附时间轴入口；没有证据显示尚未验证。只有已实施的采样检查均通过才显示可进行阶段视觉复核，仍不等于人工验收或发布。

此工具复用运行中的工作台 API，不直接改写角色或接受候选。计划固定三个角色工件、八类源动作的完整字节、正面视角；类别依据文件名或生成提示，仍需核对实际动画。

## 运行

先启动工作台及官方 Runtime 捕获环境。在仓库根目录执行：

```powershell
python tools/m4_motion_cohort.py docs/benchmark/m4-cohort-plan-v2.json ../tmp/m4-motion-center/cohort-state-v2.json --steps 200
python tools/m4_motion_cohort_report.py docs/benchmark/m4-cohort-plan-v2.json ../tmp/m4-motion-center/cohort-state-v2.json ../tmp/m4-motion-center/cohort.html
```

状态文件保存每个已提交任务的 ID。再次执行会查询相同任务，终态失败保留；不会为了通过而自动缩短动作、换视角或换角色。修改计划需要独立版本与新运行记录。默认每次只执行一步，`--steps` 可有界连续运行；仅在 API 确认任务正在排队/执行时等待。

同一状态文件使用独占锁。异常终止后，先核对 `.lock` 中的 PID 已退出再移除锁。若出现 `submitting`，说明 POST 结果尚未确认，应先检查服务端任务记录并补录确切 ID，不能直接重发或清除标记。

## 阅读结果

报告固定显示 24 个组合，并分别展示任务、几何、Runtime 帧数、接触、遮挡与人工视觉状态。几何失败可按附件跳到首个异常时刻；接触报告可定位滑移时间。未完成或无证据的项目不会计为通过。

报告是生成时的快照；播放和接触入口仍由服务器重新检查源身份。此批次不自动登记人工视觉验收，也不授权发布。FBX 缺少接触标签时显示“无源接触标签”，不能宣称足底锁定通过；动态遮挡仍显示“未检查”。

## 版本与初始证据

v1 发现已有 `walking.fbx` 与指定目录中的同名文件字节不同，身份检查拒绝复用。v2 仅去除该错误复用 ID，重新导入固定路径文件；保留 v1、拒绝记录及完全相同的三项呼吸结果。未更换固定动作文件或降低门槛。

首个完整动作 `breathing_idle.fbx` 在 Alice、辉夜、红美铃分别完成 554 帧官方 Runtime 捕获及几何检查。接触、动态遮挡和人工视觉验收尚无通过结论，不能据此宣称 M4 完成。

## 定位源投影异常

动作中心的目标候选中打开“查看遮挡时间点”，再点“检查首个冲突位置的权重归属”，可查看人体与服装混合区域的实际交集，并跳转到播放时间。检查为只读诊断；提示缺少布料深度时不要将辅助骨一律当作胸部，也不要把诊断完成当作遮挡通过。

```powershell
$env:PYTHONPATH='src'
python tools/diagnose_motion_projection.py motion-1f52729769af473084912644f9d16765 ../tmp/m4-motion-center/walking-projection
```

诊断读取经过内容验证的 MotionIR 来源包，支持 BVH/FBX 与 Kimodo SOMA77，生成逐骨段可见长度曲线、首次参考塌缩状态和完整异常源帧区间。保持既有 20% 可见长度与 0.5–1.5 倍相对长度门槛，不做权重修改或阈值放宽。

固定行走的正面投影在三条手臂骨段失败，左上臂最低可见长度约 5.6%。同字节侧面版本八骨段通过，Alice 独立侧面候选通过 377 帧几何与官方捕获；但手臂仍存在被躯干遮挡的视觉现象。改变源投影视角不会生成角色侧面贴图，接触与动态遮挡仍需后续处理。侧面试验不替换固定正面矩阵中的失败项。详细身份见 `benchmark/m4-projection-diagnostics-v1.json`。
