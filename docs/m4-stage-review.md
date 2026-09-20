# 外部动作阶段验收

动作中心中，完成的角色动作候选提供“记录 / 查看阶段验收”。先打开角色时间轴检查动作，再保存结论：

- 阶段可接受：仅在当前已实施的检查均允许阶段复核时可选。
- 阶段可接受，保留异常：需要说明可接受范围与保留问题；不会消除技术检查异常。
- 需要调整：记录异常位置和动作时间。
- 撤销此前阶段结论：追加撤销记录，旧记录保留。

接受类结论要求已有通过的 Runtime 证据。每次保存均核对候选工件、当前检查证据及记录版本。另一个页面已经保存，或检查证据变化时，旧表单会被拒绝；重新读取后再复核。重新生成的候选不会继承旧任务的验收。

记录存放于对应动作任务的 `stage-reviews/review-NNNN.json`，使用不可覆盖文件与前序摘要连接。接口为 `GET/POST /api/motions/{job_id}/stage-review`，复用工作台的同源写入保护。记录是视觉阶段决定，不是发布许可，也不修改原始素材、动作或技术检查结果。

服务通过 `stage_review_available` 声明入口可用。旧服务运行期间新版页面不会显示无效入口。正在进行固定回归捕获时，应等待安全维护间隙再重启加载新后端，不能中断活跃捕获来部署界面。

2026-09-20 已在本地工作台 8918 安全部署并只读验证真实候选表单。候选证据读取不再占用全局任务锁；历史追加仍在锁内核对版本。矩阵“记录阶段验收”链接可直接定位任务卡，不需要在历史列表中寻找。

验证：`python -m unittest test_motion_stage_review` 检查追加、撤销、恢复、并发版本、过期证据和历史完整性；`node tools/check-motion-stage-review.mjs http://127.0.0.1:8918` 使用浏览器内模拟任务验证操作，不向真实候选提交人工结论。后者需要 Playwright，支持 `PLAYWRIGHT_MODULE` 指定模块路径。

固定矩阵可只读收集阶段记录，再生成带人工结论的快照：

```powershell
python tools/m4_motion_cohort_reviews.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/cohort-reviews-v3.json
python tools/m4_motion_cohort_report.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/cohort-current-policy.html ../tmp/m4-motion-center/cohort-reviews-v3.json
```

收集器只读取已完成任务，单独写快照，不更新仍在运行的矩阵状态。候选、计划或证据不一致时不会沿用验收；撤销不计为接受。“保留异常接受”单列统计，几何通过数与技术异常数保持原口径。页面显示快照时间；要反映新保存的人工结论，需重新收集。
