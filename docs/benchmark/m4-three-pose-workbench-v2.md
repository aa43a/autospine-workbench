# 三结构源姿态 v2 工作台回归

2026-09-24。沿用完整 M4 范围，此记录不是里程碑完成声明。

来源固定为 `motion-2671c6fdbc10444592420e6f8f4ad838`（真实 FBX 呼吸动作），
使用 `source-pose-post-contact-timeline-v2`、完整片段、来源视角、接触处理开启。
所有任务通过工作台提交，旧候选及人工接受记录保留。

| 角色 | 任务 | 本次核查状态 |
| --- | --- | --- |
| 红美铃 | motion-2006938df1554092aa3fe10e7eaea819 | 构建完成；播放、同步、下载及报告入口通过 |
| Alice | motion-a78eb317d46b447cade3f83371e54ff1 | 构建完成；播放、同步、下载及报告入口通过 |
| 辉夜 | motion-b5c0568c213d4c9ab341547eb1348ebb | 构建完成；播放、同步、下载及报告入口通过 |

Alice 与辉夜的独占提交回执分别位于 `tmp/foot-v2-alice-workbench-v1/submitted.json`
及 `tmp/foot-v2-huiye-workbench-v1/submitted.json`。后续先查这两个任务，不重复提交。
角色选择/提交耗时分别约为 Alice 15.72/15.90 秒、辉夜 13.64/13.64 秒。
这仍是可见延迟，不因工具等待成功而宣称性能达标。

## 自动化检查改进及已验证证据

`check-motion-live-delivery.mjs` 现在将浏览器下载与当前候选验证接口逐字节比较，
再次读取任务核对候选身份，并把 ZIP 长度、SHA256 和比对结果写入机器报告。
红美铃实测包 128,748,691 字节，SHA256：
`30d4904466b55ffa646b2407c5d2c4b67473abb31fc49122f180bae8a1967872`。
证据：`tmp/foot-v2-workbench-v3/delivery-verified/browser-delivery.json`。

姿态工作台检查脚本先定位实际任务卡并滚动到该卡，再检查摘要及报告，
避免在长列表中等待尚未进入可视区的摘要。首轮可见摘要等待超时未计通过；
修订后的真实浏览器检查通过。核对最终接触报告与 Runtime 的 2,213 个采样一致，
姿态策略身份正确，播放器指定时间和候选身份正确，无页面脚本错误。
证据：`tmp/foot-v2-workbench-v3/readiness-visible/report.json`。

重启本地服务前确认没有活动任务，启用上一提交的诊断透传后，159 个历史任务
状态保持一致。随后才提交 Alice 与辉夜。两者终止前不再重启服务。

红美铃深度仍待复核，代理接触不证明鞋底接地；本轮没有新增人工视觉接受。
三结构本次操作回归已完成，技术质量和视觉接受仍单独保留，不能据此宣布 M4 完成。

## Alice 后续结果

候选 `c9bff7444d62d778e8a81762a2032ecb0b6bf9dd0b2f64e9c175abac03f7ef8a`，
2,213 个 Runtime 采样的几何检查通过。接触 `inferred_proxy_passed`，深度仍为
`depth_candidates_need_review`。同页播放器及 0、4.967、9.933 秒源时间轴同步通过。
浏览器 ZIP 与验证接口一致，135,181,656 字节，SHA256：
`bba3bc836e540584852880deab4c1438204a0d769229b6d4618a988d549e5e2e`。
证据在 `tmp/foot-v2-alice-workbench-v1/delivery/browser-delivery.json`。
已查看中间帧，不生成整段视觉接受记录。
姿态依据、最终接触时间轴和播放器身份检查也通过，证据在同目录
`readiness/report.json`，未写入任何阶段接受决定。

## 辉夜与集中入口

辉夜候选 `b6941a46bdd2f2bf0cb65a6229342517d79e1b92e71525e22d0806e5aaa59dd5`，
2,213 个 Runtime 采样几何通过；接触 `inferred_proxy_passed`，深度仍需处理。
同页播放、三个时间点同步及报告入口检查通过，无脚本错误。
ZIP 143,021,237 字节，SHA256：
`37cde1c38f414ac8ae1feb263f5ef465ba2e8d8e89f4ada0a19b5f4fe164166a`。
证据在 `tmp/foot-v2-huiye-workbench-v1/delivery` 和 `readiness`。

三者合计 6,639 个 Runtime 采样，均为本轮新捕获。浏览器验证与集中页核查本身
不重新捕获 Runtime。集中入口 `tmp/foot-v2-three-review-v2/index.html` 使用既有
工作台的角色选择、同步时间轴及异常筛选，不新增独立播放器。

实际集中页核查结果：3/3 候选可读取，技术全通过 0/3、新有效阶段接受 0/3。
投影、几何、代理接触、Runtime 四项均为限定采样通过，三项遮挡均需处理。
未齐备 v1 快照也已验证：可读取 2/2，分母仍为 3，运行中的辉夜不计通过。
检查脚本默认仍要求原 24 项固定集；本轮显式传入 3，并将 expected/available/
missing 写入结果，不把缩小分母当作原固定集完成。原三角色八动作清单未修改。

另外将 Alice、辉夜、红美铃的浏览器 ZIP 与不可变存储逐文件核对，分别为
115、105、109 个文件，全部字节一致；各自 delivery（红美铃为 delivery-verified）
目录的 `exact-store.json` 保留对应身份与证据。
后续优先定位这三项遮挡异常的类型和时段，并收口工作台慢校验；Reach/Squat
大动作表示失败及三角色八类动作质量目标保持未完成。
