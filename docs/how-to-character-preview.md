# 已确认图层的角色组合预览

组合已明确选择的刚性 region 与通过 Bake QA 的手臂 Mesh；不重新采用默认建议或补全未选项。
当前 Alice、铃仙各包含 5 个刚性图层和 2 张手臂 Mesh，另有 16／14 层未进入组合。
脸部细节、下半身等缺失是待处理绑定，不是已经完成的完整角色动画。

```powershell
python -m autospine_workbench.benchmark compose-character-preview `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --bake ../tmp/r2b-mesh/alice-bake-v1.json `
  --html ../tmp/r2b-mesh/alice-character-v2.html `
  --zip ../tmp/r2b-mesh/alice-character-v1.zip `
  --output ../tmp/r2b-mesh/alice-character-v1.json
```

`lingxian` 同理。HTML 可播放与拖帧，可选择显示半透明原图参考；参考图不参与动画、绑定或 QA。
WebGL 使用预乘 Alpha framebuffer，避免图层叠加时重复乘透明度导致暗边。
当前 HTML 刚性显示仅支持此循环中静止的 head/neck/chest 图层；其它刚性驱动会明确拒绝。
ZIP 包含同一组合的 Spine 4.3.26 JSON、Atlas 和 PNG，解压后导入 `skeleton.json`。

## 接触候选的含义

在肩部附近、已选 chest 刚性图层与手臂的 alpha≥8 重叠像素中，按离肩距离选最多 16 个锚点。
将像素中心映射到原 Mesh 三角形的重心坐标，再跟踪 61 个烘焙关键帧。
本循环胸部静止，因此其锚点以 setup 坐标为参考。没有像素重叠或无法映射时返回 `unobservable`。

Alice 两侧找到 5／26 个重叠像素，铃仙为 1584／1182 个；候选采样分离量接近零。
这不是完整接触区、连续时间、衣袖轮廓或遮挡 QA，也不是人工认可的 seam anchors。
报告始终为 `candidate_requires_review` 或 `unobservable`，`seam_certified=false`。
当前还没有主工作台中的接缝候选采用入口，不能以 gap 小自动批准。

## 身份和验证

组合必须引用同一 candidate、skeleton、binding draft、Mesh 和 Bake 地址，修改选择后不能复用旧 Mesh。
新 `character-target-preview/v1` 回执列出刚性层、所有导出/排除层、接触候选及 ZIP 文件摘要。
`read_character_preview` 完整重放来源、重算接触并重建 ZIP；旧手臂诊断包不改写。
源图层顺序仅作为预览顺序，`draw_order_status=source_order_unreviewed`；完整角色状态继续阻塞。

[真实验证记录](benchmark/character-preview-2026-09-08.json)：37 项相关测试通过，
真实 CLI、Schema/CAS、ZIP 摘要、刚性层独立 FK 和 Chrome 组合显示检查通过。
未运行全量 Python/Web 或官方 Spine Runtime/Editor，未宣布接缝认证通过。

下一步整理剩余图层的语义/绑定复核入口，处理脸部附件、裙子和下肢，再把接触候选接入复核与动态 seam 测试。
