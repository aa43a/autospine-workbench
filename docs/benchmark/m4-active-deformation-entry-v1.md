# 姿态附件接入正式采样几何检查

2026-09-24。`deformation_qa.inspect` 在存在 attachment timeline 时分派到
活动附件检查，固定网格原分支保持原行为。

每帧必须携带与骨架时间线一致的附件名；可见 slot 清单、顶点数量、有限值
都需匹配。几何门槛保持面积比 0.5–2、边长≤2、零翻转，使用该附件自己的
setup 顶点与三角形；记录按 animation/slot/attachment 分开聚合。
隐藏附件单独记录；全隐藏结果不能通过。接触及切换连续性明确未检查。

这使同 slot 的新姿态网格不能借用旧网格的绿色结果。旧纹理异常定位器
暂不支持活动附件，现显式返回 unavailable，避免将新三角形索引画到旧纹理。
后续仍需将活动附件定位接入该页面，再连接候选构建、接触及切换检查；
本改动没有将实验候选提升为默认，也不代表实际新膝形已完成。

真实已有实验 `pose-attachment-variant-v1/candidate.json` 的 163 个采样进入
正式入口，得到 28 条附件检查记录，4 条失败，整体 passed=false。
输出为 `localset/tmp/m4-motion-center/pose-attachment-variant-v1/formal-active-geometry.json`。
本轮复用既有姿态参考，没有新 Runtime 或 GPU 捕获，没有修改已有身份或验收。

回归覆盖固定角色 QA、motion clip、活动网格、不同拓扑、错配附件身份、
新附件翻转与旧定位器拒绝。正式范围仍是采样几何，不保证帧间连续性。
