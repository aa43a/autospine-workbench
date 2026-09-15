# 琪露诺新版：安全绑定与基础动作候选

2026-09-15 读到当前来源的 17/17 关节已复核，执行现有 prepare_apply_all 流程。新增十个候选选项，随后两轮自动采用八层：neck、face、nose、mouth、eyebrow、eyewhite、irides、eyelash。两批决定读回均可撤销；精确来源见 [决定记录](crino-current-auto-bindings-v1.json)。独立正确率未测量。

当前规划为 86de5e70b5954d25b4939d81e8e604169312609ebc43f73aaa5337c71d896420。其余十层仍待处理，旧版翼层的归属、清除和视觉确认未转写到新版。

实际工作台任务 job-988d7c39bcc04142b7c20aeb56e13b00 已完成来源解析、网格构建及动画编译，进入 animated_review_required。基础 limb-flex-15 候选报告有 20 根骨骼、6 个网格层、3 个分区源层、23 个可见层，无 rejected_mesh_layers。

此结果不等于官方 Runtime 多动作通过或整角色接受，不改变首批十角色完成数。下一步仍需普通肢体路线确认以及其余层的处理与视觉验收。
