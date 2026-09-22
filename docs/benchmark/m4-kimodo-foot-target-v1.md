# Kimodo 脚部姿态整角色验证

2026-09-22。通过工作台 API 创建独立任务 `motion-83eb9fa230154c7eb878102be719f69f`，源为真实生成的 `motion-dc7dc44a65c74445bd87e1baaf81c6cf`，角色为红美铃已存在的 `job-7d8ce666ea13487a953bdfa5258ea79a`。完整动作、原视角、接触修正开启，显式选择 `source-pose-post-contact-margin-v1`，无裁剪、减幅或变速。

首次 HTTP 请求缺少 Origin，被 403 拒绝且未排队；补齐同源请求头后收到完整 202 回执。attempt、rejected、submitted 记录均保留。候选为 `cc7829f8aaf9ba906e8896583d651fcdc78067647d3c723d90fd348edddee12a`，未覆盖或采用历史结果。

## 已验证

- 120 个源关键帧的脚部世界矩阵最大误差约 7.77e-16。
- 在候选 1,702 个检查时刻，脚部 rotate/scale/shear 通道引入的脚踝位移为 0 px。这只比较通道影响，不是三维脚底约束的证明。
- 原 MotionIR 接触标签保留；最终 CPU 脚踝代理检查为 ankle_proxy_passed。
- 官方 Runtime 捕获 1,702 帧、27 个槽位；播放、源同步时间轴起点／中点／终点验证通过，无脚本错误。
- 浏览器实际下载 ZIP 的 105 个文件与不可变产物逐字节一致。

## 未通过

整体几何检查失败，仅 layer-006（handwear-l）超限：1,439 个失败时刻，首个为 0.6933919853515625 秒；最小面积比 0.284965884，翻转采样 0，最大边长比 1.292333。接触后约束失败与整体变形失败均继续保留，不用脚部通过抹除左臂问题。

Runtime 摘要 contact_status 为 not_evaluated；CPU 脚踝代理通过不等同于 GPU 脚底或视觉接受。查看了中点整角色截图，没有将本次观察写作人工验收。

证据：`localset/tmp/m4-motion-center/kimodo-foot-target-v1/hongmeiling/check-v2.json`、`browser-delivery.json`、`candidate.zip` 和三时刻截图。可通过 `tools/m4_foot_target_check.py` 重新核对精确任务。

下一项保留该角色／动作／失败时刻，检查左臂面积压缩的表示限制；脚部适配需要另外两种结构角色的回归。M4 三角色八动作的完整质量验收仍未完成。

## 同帧移除 deform 的诊断对照

工作台任务卡 → 检查可用范围与待处理项 → 查看变形区域与处理方案，现展示保留相同骨骼、权重和时间、仅移除动画 deform 后的面积比，以及实际结果与其差值。这是 CPU 反事实采样，不是新增官方 Runtime 捕获，不修改候选、原门禁或人工决定。

本候选三角形 203 在 3.966667 秒，原权重采样面积比为 0.349390052，实际修正后为 0.284965884，差值 -0.064424167。邻域也有修正后改善的三角形，不能据此把所有异常归因于 deform 或直接删除修正。下一修正策略需要同时评估原权重压缩、投影参考及修正造成的退化。

七项单元测试通过，包括真实骨骼缩放和 deform 组合、输入不变性、身份拒绝、压缩/扩张各自时刻。真实浏览器完成入口点击、指标显示与区域切换，无脚本错误。证据位于 `localset/tmp/m4-motion-center/kimodo-foot-target-v1/deform-comparison`；复现工具为 `tools/check-motion-deform-comparison.mjs`。首次浏览器脚本遗漏前置检查按钮，已修正后重跑；未创建新候选。
