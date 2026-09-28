# 角色动作编辑链交付核对

日期：2026-09-28。入口：http://127.0.0.1:8918/motion-editor.html 。
从动作中心也可进入。服务为本地工作台；无需额外创建项目或覆盖已接受候选。

动作编辑现支持同页图层排序、移动、旋转、缩放和保存导出，见 [图层校正操作与验证](motion-editor-layer-corrections.md)。

后续主线见 [M5：脸部、头发与服装联合动画](milestone-m5-joint-animation.md)。
下文质量边界由 [M4 质量后续工作](m4-motion-quality-followup.md) 按需承接，
不要求全部修复后才开始联合动画；本页已交付范围和既有验收保持原记录。

## 使用流程

1. 选择已绑定角色和源动作。也可展开“新增动作”，导入文件或填写Kimodo描述。
2. 来源任务完成后点击“载入编辑”。左右画布共用时间轴，可播放、暂停和反向拖动。
3. 修改水平角度；在不同时间点击“记录角度”形成轨道。0→360保留完整一圈。
   新编辑默认按投影方向补帧；旧草稿恢复原版本。可撤销/重做、保存或导入导出草稿。
4. 点击“构建当前动作候选”。页面显示处理阶段，任务可取消、刷新恢复。
5. 完成后查看检查结果，点击“在编辑区对照导出结果”并恢复其角度草稿。
   对照栏显示实际烘焙结果；下载按钮输出Spine4.3.26候选包。

## 按原目标核对

| 要求 | 当前实现及直接证据 | 结论 |
|---|---|---|
| 已绑定角色及确切版本选择 | motion-target读取、独立角色job绑定；实际Alice/辉夜/红美铃页面提交 | 已实现 |
| 已有、导入、Kimodo | 完整BVH页面导入、真实Kimodo任务c8f9555203bc4130abeaf37e523a16cb生成并载入；intake-race-v1验证重试及旧响应隔离 | 已实现 |
| 共用时间轴和360°实时贴图 | final-ui-v1验证整圈、半圈、回零、播放/暂停、草稿与390px布局；final-live-v1核对官方Runtime骨骼世界变换 | 已实现 |
| 共用求解及连续角度 | Python/JS姿态逐轨道对照；BVH最大差8.13e-12、Kimodo3.42e-13；v2按投影方向细分；测试明确拒绝不可观察方向 | 已实现，带下述限制 |
| 固定与关键帧烘焙 | 固定候选04c191a14c5e4c4d90ac166e1a169051及三角色新版完整旋转任务 | 已实现 |
| 几何/接触/遮挡/Runtime | 三角色新版各659帧Runtime几何通过，相机接触代理通过；遮挡异常明确保留 | 检查链已实现，非全部视觉通过 |
| 实际导出对照和Spine包 | 三角色五次时间定位（含倒退）逐像素对照；红美铃93文件、辉夜89文件ZIP完整，版本4.3.26 | 已实现 |
| 身份、人工记录及撤销 | 新任务独立；版本/源身份不符拒绝恢复；草稿变更显示旧结果；有界撤销/重做；不提交人工接受 | 已实现 |
| 模块长度和回归 | 编辑模块均不超过400行；本轮51项Python、27项前端测试通过 | 已核对 |

证据根为工作区tmp，不将历史固定M4候选替代本目标的动态验证：

- motion-editor-real-generation-v1、motion-editor-intake-race-v1。
- motion-editor-final-ui-v1、motion-editor-final-live-v1。
- motion-projected-bvh-v2、motion-projected-pose-v2。
- motion-editor-projected-comparison-v2c、motion-editor-projected-result-v2（红美铃）。
- motion-editor-alice-projected-comparison-v2（Alice）。
- motion-editor-huiye-projected-comparison-v2、motion-editor-huiye-projected-result-v2b。

新版任务：Alice motion-b559cb9ad0884b538c39a95eb40d37c7；辉夜
motion-b72f1979482e4b929653233b175de5d2；红美铃motion-fdbe41f6bbe843b9a5c403dd1f118c24。

## 保留的产品边界

完成的是可操作的动作编辑、映射、检查和导出链，不是所有动作的视觉质量认证。
正面素材不能生成可信侧背面；侧背面与遮挡异常仍显示为needs_changes。
投影不可观察、采样预算或时间精度不足时明确失败，不靠猜方向、截断旋转或隐藏半圈通过。
当前最多4096采样、256角度键、±3600度；源读取保留既有帧数限制。

实时草稿使用共享原始姿态规则；局部修形、接触与遮挡修正于后台构建执行。
实际导出栏用于逐帧查看这些修正结果，不能把原始草稿画面当成已通过QA的产物。
接触代理不等于真实地面与鞋底接触证明，Runtime几何通过不等于遮挡自然。
本轮没有记录新的人工视觉接受，也没有发布或替换用户历史候选。
