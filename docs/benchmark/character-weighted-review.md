# 已有加权区域的准确范围复核

2026-09-12。新增 character-weighted-review/v1，解决“区域已进入整角色，但只能去改整层绑定”的操作缺口。

## 操作

在工作台整角色候选下，查看 Runtime 后使用“确认已有区域绑定”。只有整层输出均为加权区域、没有静态残余或缺失区域，且当前 Runtime 与几何检查通过时，才允许确认。每个图层独立确认，可撤销。原始 layer-binding draft 不改写，也不重新生成网格。

记录绑定 project、job、artifact、完整图层列表及 Runtime 指纹。记录追加保存并检查版本冲突；不同候选或区域内容不能沿用旧确认。输出仍是候选，不授权发布。确认仅解决绑定范围，setup、draw order、connections、motion 四项视觉验收仍须独立满足。

后端 GET/POST：/api/projects/{project}/automation/character/jobs/{job}/weighted-review。
持久化：当前 job 的 weighted-review 目录；每份记录由 canonical SHA 及 previous_sha256 串联。

## 真实范围

character-weighted-review-readiness-v1.json 通过准确来源读取、工件 inventory 和实际 Runtime 报告得到：

- 红美铃 layer-001 / layer-006：两侧手臂可进入区域确认。
- 小恶魔 layer-009：腿部有效区域可确认，此前已批准的残余排除保留。
- 辉夜：无符合条件图层，不能绕过残余复核。

本次未提交任何人工区域确认，未闭合项仍为 17。此前胸前服装片两项确认仍待用户答复。

## 验证

15 项 Python 测试通过，涵盖确认/撤销、准确身份、部分区域拒绝、Runtime/几何失败、Schema、统计与独立视觉门禁及文件长度。12 项 Web 测试通过，涵盖来源切换、未保存状态、迟到响应、区域排除和旧流程。

已加载到本地 8918 服务。真实 GET 返回红美铃两层；缺失 Origin 的 POST 被拒绝为 403，非法字段 POST 被拒绝为 400，无写入。历史工件保持不变。
