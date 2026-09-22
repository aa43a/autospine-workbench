# Kimodo 脚部适配：三结构工作流回归

2026-09-22。沿用同一真实 Kimodo 生成动作 `motion-dc7dc44a65c74445bd87e1baaf81c6cf`，完整 120 源帧、原视角、接触修正开启、显式 `source-pose-post-contact-margin-v1`。未重新生成源动作，也未减幅、裁剪或改变速度。

新增 Alice 和辉夜候选，通过工作台任务队列执行；红美铃使用已有精确候选及其 Runtime 证据，本次未重新捕获。三者源 MotionIR、NPZ 与映射身份完全一致。

| 角色 | 任务 | Runtime 时刻 | 脚部矩阵最大误差 | 脚部通道引入踝点位移 | 几何 |
| --- | --- | ---: | ---: | ---: | --- |
| 红美铃 | motion-83eb9fa230154c7eb878102be719f69f | 1702 | 7.77e-16 | 0 px | 左臂面积失败 |
| Alice | motion-a7a946be55ee44169e8ccb6e0fe4baa7 | 2106 | 7.36e-16 | 0 px | layer-004 面积失败 |
| 辉夜 | motion-fbda8f3581e842288bdf7b8c02280629 | 1858 | 7.29e-16 | 0 px | layer-003-component-0000 面积失败 |

三者保留源接触标签，CPU 踝部代理均为 ankle_proxy_passed；Runtime contact_status 均为 not_evaluated。脚部矩阵及通道检查 3/3，整体几何 0/3，不能将局部来源适配通过表述为完整动作通过。

Alice 新候选 `501ed517731d534f2a956bb9037fd686e08460e23110575d717f756e9c66a81d`：几何失败 1810 个时刻，最小面积比 0.297189，翻转 0。辉夜新候选 `b83c308040344fbea59f260a0e715d0c5c4758d56b260edee952d802f8bba74b`：几何失败 1527 个时刻，最小面积比 0.316608，翻转 0。

## 实际工作台交付

两个新候选均通过任务卡的同页播放器、源骨架共用时间轴起点／中点／终点检查，没有脚本错误；浏览器实际下载 ZIP，并与不可变产物逐文件、逐字节核对。Alice 为 114 个文件，辉夜为 102 个文件。结果仍是诊断候选，无新增人工接受，历史决定和默认策略不变。

可操作入口：

- Alice：http://127.0.0.1:8918/motions.html#motion-a7a946be55ee44169e8ccb6e0fe4baa7
- 辉夜：http://127.0.0.1:8918/motions.html#motion-fbda8f3581e842288bdf7b8c02280629

证据根目录：`localset/tmp/m4-motion-center/kimodo-foot-target-v1`。各角色目录包含 submitted、cohort-check、browser-delivery、delivery-check 和实际下载包；根目录 cohort-summary 使用同源身份检查，分别统计脚部与整体几何。`tools/m4_foot_cohort_check.py` 可复核，已有回执仅允许相同内容恢复，禁止静默覆盖不同结果。四项测试覆盖身份混用、任务重复、非有限误差、接触标签变化和恢复时的回执保护。

本次补齐的是新 NPZ 脚部适配的三结构回归，不是三角色八类动作全部完成。目标 Spine 版本为 4.3.26，实际官方 Runtime 包为 4.3.13；数值核对通过不代替视觉与鞋底接触验收。后续回到动作表示和未通过的几何、遮挡处理，不扩大袖装专项。
