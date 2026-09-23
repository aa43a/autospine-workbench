# 右臂近参考平面的实际画面对照

2026-09-23。使用工作台现有官方 Runtime 播放器，读取精确候选
9c627a5e3278e841ca69ce59ad8ca6bf44506b24c43e93b7d7b88e42edd40a5f，
任务 motion-ce0cadffdec24393861024af7206f8b2。
在 1、1.5、2 秒分别截图完整角色、layer-003 与 layer-006、仅 layer-003。
共 9 张画面，时间与 artifact 核对通过。脚本无写入业务接口、改顺序或验收操作。

证据：`tmp/repair-depth-visual-v1/report.json` 及同目录 frame-*.png。
可复现工具：`tools/check-motion-depth-visual.mjs BASE JOB OUTPUT`，
PLAYWRIGHT_MODULE 指向可用 playwright-core。

观察：这三个时刻右臂袖根在上衣后方，未看到明显穿插。
这是有限帧的助手观察，不是用户验收或真实深度证明。
完整角色抬起的另一侧手臂仍有形状问题，原几何失败和整体 needs_changes 保留。
因此本轮没有改变绘制顺序，也没有将近参考平面样本转成自动通过。

## 工作台定位

局部深度异常的定位链接现在包含当前两个 region 和 isolate 模式。
播放器在相同时间直接选中、显示对应部件，展开部件对照，允许恢复完整角色。
未知 region 保留完整角色并显示提示；查询参数只影响查看，不修改资产或验收。

check-motion-player-focus.mjs 使用真实任务验证定点、选中、恢复及非法部件降级；
check-motion-depth-ambiguity.mjs 验证生成链接。未执行新的整段几何或视觉验收。
