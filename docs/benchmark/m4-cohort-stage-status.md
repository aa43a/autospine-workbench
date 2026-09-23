# 固定动作集分阶段状态

固定集状态矩阵现直接显示投影、几何、接触、遮挡、Runtime 等当前报告返回的检查项。展开单项可查看检查范围及阻塞说明；“检查此项”继续使用原同页角色选择与播放入口。

阶段筛选仅排除该项明确为 `sampled_pass` 的候选。缺失阶段、旧格式证据、读取失败和未生成候选仍保留。所有计数在筛选前计算，阶段视觉接受与技术检查保持独立。刷新及验收更新会清除旧阶段详情；来源、候选和检查身份必须匹配才显示证据。

验证命令：

```
node tools/check-motion-cohort-status.mjs E:/proj/unusual/localset/tmp/spine43-verification
node tools/check-motion-cohort-status-live.mjs E:/proj/unusual/localset/tmp/spine43-verification tmp/cohort-stages-live-v1
```

浏览器回归覆盖阶段筛选、说明展开、统计分母不变、旧格式证据、身份失配、停止核对及同页选择。真实固定集核对只读取现有证据，不重新捕获 Runtime，不记录新视觉接受。

此交付改善异常定位，不表示 Reach/Squat 大动作质量已通过，也不将深度不确定自动解释为缺失素材。

实际 24 项只读核对通过：技术整体通过 0/24，有效阶段接受 3/24。按未通过或未验证筛选后，投影 18 项、几何 13 项、接触 15 项、遮挡 24 项、Runtime 0 项；各筛选均保持统计不变。无新增验收记录、无 Runtime 重捕获。截图和原始结果位于 `tmp/cohort-stages-live-v1/`。
