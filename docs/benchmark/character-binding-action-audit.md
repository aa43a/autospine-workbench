# 绑定动作与编辑来源分离

2026-09-12。来源追踪记录 explicit_selection 表示记录曾被显式编辑，可能只是更新备注，不证明 action 已变为 bind。旧整角色统计仅按 decision_source 判断 pending，可能把已有加权候选且仍 pending 的带备注记录误算为完成。

本次以实际 action 与选项判断绑定完成；pending、requires_split、semantic_review、缺失动作或缺失选项都保留待办。有效的精确区域确认仍可解决加权区域的 pending，但不能覆盖拆分或静态残余。来源追踪文档及历史工件不变。

前端同时显示动作与编辑来源，避免把“显式编辑”读成“已选择绑定”。Python 与 Web 共用 14 个反例/正例数据，包括备注编辑、动作冲突、区域确认和撤销语义。

15 项 Python 和 13 项 Web 测试通过。重新从工作台读取三角色当前 job、实际 Runtime 报告及复核：17 项未闭合，0/3 完成，Runtime 三份均通过。人工耗时与错误自动采用率仍未测量。报告见 character-cohort-action-audit-v1.json。

本次没有新增人工确认、改变骨骼或重新生成素材。胸前服装片两项提案及三层加权区域仍待相应确认；裙摆、混装翼与静态残余仍需后续能力与复核。
