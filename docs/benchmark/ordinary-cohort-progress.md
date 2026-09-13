# 普通路线三角色推进

2026-09-13 用户确认爱丽丝、铃仙、露米娅先走普通肢体绑定，异常服装单独处理。已将路线分别绑定到当前 resolved 来源；不把普通路线解释为无袖，也不替代原固定三角色名单。

三名角色均已从工作台生成统一候选，保留原人工记录和未确认层。三份官方 @esotericsoftware/spine-webgl 4.3.13 报告各验证 1,028 帧：idle 129、wave-left 257、walk 513、limb-flex-15 129。Spine 输出默认仍为 4.3.26。确切工件和报告摘要见 [数值记录](ordinary-cohort-progress-v1.json)。

行走沿用同一 MotionIR 和投影策略，未按角色调参。检查涵盖顶点一致性及非空、未裁切 framebuffer；踝部代理修正不等于鞋底 foot-lock，toe anchor 缺失和遮挡仍须复核。

爱丽丝可读回两批、共 11 层可撤销的安全自动决定。铃仙和露米娅本轮只补齐候选选项，没有新增自动采用；新增候选选项不计作确认层。三角色的未绑定源层、静态残余和整角色视觉未闭合，因此不计作新增完成角色。

## 预览入口

- [爱丽丝](http://127.0.0.1:8918/api/projects/alice/automation/character/jobs/job-92490c3934a840e09096a46a8a5217be/view/index.html)
- [铃仙](http://127.0.0.1:8918/api/projects/lingxian/automation/character/jobs/job-4659db4b2117457b9130db4cd8219211/view/index.html)
- [露米娅](http://127.0.0.1:8918/api/projects/lumia/automation/character/jobs/job-37ebfa7993854b829ab43e6ba2b2e47f/view/index.html)

## 请求中断

爱丽丝自动处理已提交，但客户端在响应前等待超时。通过只读当前决定恢复，而没有重发采用。修复成功响应遇到断线后再次发送 400 的误报；九项自动采用、断线处理及质量回归测试通过。此修复不取消后台工作，不改变绑定权威，也不缩短计算时间。
