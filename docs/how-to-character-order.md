# 比较整角色的遮挡顺序

当源层顺序让裙装后面的腿部切边露出时，可以生成独立顺序候选。先检查 setup 和动作帧：原先就存在的切边不能直接归因于新动作或网格权重。

`build-character-order.py` 从内容寻址角色包读取现有 slot，只改变指定的前后关系。`--behind BACK:FRONT` 表示 BACK 先绘制、FRONT 覆盖它，可重复指定。工具采用稳定拓扑排序；不使用角色名称、固定图层编号或衣服特判。未选候选不会修改工作台当前结果。

```powershell
python tools/build-character-order.py --state-root workspace --source <角色内容地址> --behind <腿区域slot>:<裙装slot> --output <对照目录>
```

输出 `generation.json` 引用新的内容寻址包。Schema 是 `schemas/character-order-candidate-v1.schema.json`；语义检查拒绝重复 slot、未知 slot、循环约束、非 4.3.26 来源、过期数值参考、动态 drawOrder 和 clipping 依赖。CLI 输出候选，不提交任何人工决定。

骨骼、附件/权重/UV、动画、纹理、已确认绑定及逐帧顶点不变。数值参考的 skeleton 身份随新顺序更新，旧包保持原地址。Runtime 和绘制顺序视觉状态重新置为待验证，不沿用旧结果。对新包执行官方捕获后，比较 setup 与动作帧；顺序变化可能遮住本来应在前方的饰物，因此通过数值检查不能自动采用。

工作台整角色候选区提供“部件前后遮挡”：选择前方与后方部件，添加关系后确认保存。已保存关系会在动作、裙装、分区和残余处理完成后、Runtime 捕获之前应用。保存不会自动通过视觉验收；点击“构建整角色候选”后检查新的完整动作。入口同时支持撤销，保留旧记录与旧候选。

`/automation/character/order-review` 提供 GET 和 POST。写入要求同源意图、当前项目、确切角色包和历史头地址。来源变化返回 `character_order_source_changed`，不会把旧遮挡决定迁移到另一个动作或分区结果。保存时记录构建选项，工作台恢复这些选项；撤销后再重建回到原顺序。没有顺序决定的项目保持旧请求和工件身份。
