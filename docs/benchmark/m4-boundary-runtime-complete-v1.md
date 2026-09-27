# M4 边界候选完整 Runtime 与播放器

2026-09-27。16 批、16,319 独立时刻的官方 Runtime 数值验证完成并通过，
精确时间覆盖审计通过。每批重复 setup 起点不重复计入独立时刻。
实际官方 Runtime 包版本 4.3.13，输出目标 Spine 4.3.26；不混称版本。

## 结果与限制

- 输入规范化骨架：`3ba444a00438086b475e7165bf80bda84ca04a7aa668c36e67ad1b4abbe4f087`。
- 原双精度局部 15,940 时刻通过、一致时间参照 16,557 时刻通过。
- Float32 局部面积检查仍有已记录数值缺口，见 boundary-storage-audit。
- 整角色 setup 几何未通过，异常在 layer-001-l 与 layer-001-r；两侧均无翻转。
  左侧最小面积比 0.225251、最大边长比 1.920628；右侧 0.199700 / 1.902180。
  右侧与父包一致，左侧仍保留父包深压缩；没有通过局部修正宣称解决投影问题。
- 接触、深度、视觉尚未验收，未正式采用。

完整报告 `tmp/m4-joint-boundary-runtime-v1/report.json` SHA256：
`ba702bbec5ceb2f0435b88f64904b142b752aeb9ff9a147ffb39e2900855a078`。

## 可播放交付

新增 m4_transverse_batch_player.py，导出前重新审计全部批次和来源身份，再复用
现有实时播放器；视野取全部捕获范围并集，避免只显示第一批位置。播放窗口
支持既有播放、暂停、时间轴操作，未在本轮浏览器中实测交互。

- 完整对照入口：`tmp/m4-joint-boundary-runtime-v1/index.html`
- 播放器：`tmp/m4-joint-boundary-runtime-v1/batch-000/runtime/player.html`
- 播放场景 SHA256：`cef9e92e8cbc576cc1c7247bea645c850eb28ea8ea53a36c8f4fd670aedec9a4`
- 视野：left=207、bottom=-1044、width=597、height=1144。

14 项相关测试通过，包括不允许未验证 Runtime 导出、全批次视野并集、显式
包身份不能绕过捕获校验，以及保留几何失败与未采用状态。

下一步让该完整候选进入实际效果、接触与前后关系检查，存储精度诊断继续
保留。当前微小数值缺口与源投影压缩是不同问题，不能用其一掩盖另一项。
