# 姿态附件接入正式采样几何检查

2026-09-24。`deformation_qa.inspect` 在存在 attachment timeline 时分派到
活动附件检查，固定网格原分支保持原行为。

每帧必须携带与骨架时间线一致的附件名；可见 slot 清单、顶点数量、有限值
都需匹配。几何门槛保持面积比 0.5–2、边长≤2、零翻转，使用该附件自己的
setup 顶点与三角形；记录按 animation/slot/attachment 分开聚合。
隐藏附件单独记录；全隐藏结果不能通过。接触及切换连续性明确未检查。

这使同 slot 的新姿态网格不能借用旧网格的绿色结果。初版将旧纹理异常定位器
显式置为 unavailable，后续已完成下述活动附件定位。
后续仍需连接候选构建、表面接触及切换检查；
本改动没有将实验候选提升为默认，也不代表实际新膝形已完成。

真实已有实验 `pose-attachment-variant-v1/candidate.json` 的 163 个采样进入
正式入口，得到 28 条附件检查记录，4 条失败，整体 passed=false。
输出为 `localset/tmp/m4-motion-center/pose-attachment-variant-v1/formal-active-geometry.json`。
本轮复用既有姿态参考，没有新 Runtime 或 GPU 捕获，没有修改已有身份或验收。

回归覆盖固定角色 QA、motion clip、活动网格、不同拓扑、错配附件身份、
新附件翻转与旧定位器拒绝。正式范围仍是采样几何，不保证帧间连续性。

## 活动附件异常定位

`active_geometry_details.py` 先重新校验活动附件采样，然后按确切附件分组，
复用固定网格的 UV/原姿态面积/移除 deform 对照。分组内部只固定网格身份，
骨骼时间线保持原样。纹理路径、三角形索引、世界位置和采样时刻来自该附件；
返回报告保留原候选与原 skeleton 身份，不将临时分析文档当成新候选。

工作台异常卡片显示附件名称，可以跳到动作时刻。活动附件条目暂不提供
旧固定网格修正或高亮入口，避免把新索引写入原 attachment；只读定位不清除失败。

真实冻结 Runtime 捕获包 `818e98fa29dd431d41cdf38e67bc6f1f8c7526e73257dfce360a3966d1ac96eb`
产生四条失败区域记录：原 layer-003 99 个采样、姿态 layer-003 64 个采样，
另两附件各 163 个。三个面积失败记录各展示 12 个极值事件；layer-008 为边长
问题，没有伪造面积事件。输出 `pose-attachment-variant-v1/active-source-locations.json`。
本轮未启动新的 Runtime/GPU 捕获，未做浏览器交互实测。

接触代码核对：`final_motion_contact.recheck` 调用 `motion_contacts.analyze`，
采样 foot 骨骼位置。其报告已声明 ankle proxy，不能作为新姿态附件的鞋底
表面接触证据。后续应在确切活动附件上定义与验证鞋底材料锚点，不能仅因
骨骼不变就自动通过网格表面接触。
