# 普通路线三角色推进

2026-09-14：用户确认集中页 17 层方案。已保存 14 个刚性绑定（爱丽丝 5、铃仙 4、露米娅 5），其余记录逐项保持；三个 bottomwear 使用同一固定裙腰与独立三链策略生成加权候选。新候选各通过 1,028 帧官方验证、几何失败 0。确切来源与检查见 [裙装推进记录](ordinary-skirt-progress-v1.json)。

实际挥手捕获帧发现爱丽丝肩端与上衣分离，仍需修正；三者均未保存整角色视觉接受。普通路线完成数不能由数值通过直接增加。以下为早期阶段记录，预览入口已更新至本次候选。

2026-09-13 用户确认爱丽丝、铃仙、露米娅先走普通肢体绑定，异常服装单独处理。已将路线分别绑定到当前 resolved 来源；不把普通路线解释为无袖，也不替代原固定三角色名单。

三名角色均已从工作台生成统一候选，保留原人工记录和未确认层。三份官方 @esotericsoftware/spine-webgl 4.3.13 报告各验证 1,028 帧：idle 129、wave-left 257、walk 513、limb-flex-15 129。Spine 输出默认仍为 4.3.26。首次记录见 [历史数值记录](ordinary-cohort-progress-v1.json)；铃仙、露米娅已按新头颈确认和自动细节绑定重建，[最新来源与报告](head-prerequisite-progress-v1.json)独立保存。

行走沿用同一 MotionIR 和投影策略，未按角色调参。检查涵盖顶点一致性及非空、未裁切 framebuffer；踝部代理修正不等于鞋底 foot-lock，toe anchor 缺失和遮挡仍须复核。

爱丽丝可读回两批、共 11 层可撤销的安全自动决定。铃仙和露米娅先补齐候选选项，随后用户明确确认四个头颈层，既有策略再各自动采用十个细节层。新增候选选项不计作确认层；自动采用准确率仍未测量。三角色的未绑定源层、静态残余和整角色视觉未闭合，因此不计作新增完成角色。

## 预览入口

- [爱丽丝](http://127.0.0.1:8918/api/projects/alice/automation/character/jobs/job-44f590f6f9be4bc38a77760484fbe195/view/skirt/index.html)
- [铃仙](http://127.0.0.1:8918/api/projects/lingxian/automation/character/jobs/job-a13aeff0cd534e41a92973f002dca8e8/view/skirt/index.html)
- [露米娅](http://127.0.0.1:8918/api/projects/lumia/automation/character/jobs/job-e7a10fcc7d964b51a72bd27c3dd1072a/view/skirt/index.html)

## 请求中断

爱丽丝自动处理已提交，但客户端在响应前等待超时。通过只读当前决定恢复，而没有重发采用。修复成功响应遇到断线后再次发送 400 的误报；九项自动采用、断线处理及质量回归测试通过。此修复不取消后台工作，不改变绑定权威，也不缩短计算时间。
