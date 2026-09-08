# 新增空白连通区域与跨帧轨迹

本切片把同一时刻两版动画比较得到的新增空白组织为区域和关联候选，不改变 Mesh、权重、动画或采用状态。
继续使用原共同走廊、alpha8、30 FPS 的 61 个时刻，并逐帧重放已有指标。

```powershell
python -m autospine_workbench.benchmark.seam_gap_tracks_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --output-dir ../tmp/r2b-gap-tracks/alice
```

输出内容地址命名的 `autospine.seam-gap-tracks/v1` JSON 和自包含 `index.html`。
页面支持关系、轨迹、帧选择，以及当前帧放大／固定世界视野；坐标证据可展开。
蓝绿为两张附件、紫色为重叠、红色为当前新增空白、橙色为轨迹。
这些是 CPU alpha 占用图，不是新的官方 Runtime 截图。

`read_tracks` 根据源 bundle 重新运行本诊断并比对规范化内容地址，拒绝被修改的报告。
所用骨架和纹理逐文件核验，源 before 地址必须匹配 after 的 source_anchor_sha256。
这不替代上游完整编译链 reader。页面单独记录 SHA，修改页面不改变数据报告身份。

## 固定规则与限制

- 单帧使用八连通；保存全部像素中心世界坐标（Y 向上）、面积、质心、包围盒、三类支撑计数。
- 仅检查相邻帧，区域间最小像素中心距离不超过 3px 才建立候选边。
- 仅双方都唯一匹配时延续轨迹；多目标为 split_candidate，多来源为 merge_candidate，歧义处新开轨迹。
- 空帧、超距和首尾循环不强行续接；本版本没有运动补偿或缺失帧桥接。
- observed_frames 是观测帧数，不是已证实的物理缺陷寿命。边界宽度、法向、内外拓扑尚未求解。
- 所有轨迹为 unclassified / needs_review。没有门禁通过或自动采用动作。

## 2026-09-08 样本结果

| 关系 | 像素样本 | 候选轨迹 |
| --- | ---: | ---: |
| Alice 左 | 7 | 6 |
| Alice 右 | 0 | 0 |
| 琪露诺左 | 99 | 70 |
| 琪露诺右 | 212 | 107 |

铃仙无接缝候选，不计为通过。实际样本未触发分裂／合并候选；合成测试覆盖这两种情况。

Alice 左侧的观测：

| 帧 | 面积 | 世界质心 (x, y) |
| --- | ---: | --- |
| 34 | 1 | (440.5, -847.5) |
| 36 | 1 | (448.5, -853.5) |
| 37 | 1 | (452.5, -857.5) |
| 38 | 1 | (458.5, -861.5) |
| 52 | 2 | (580.5, -905.0) |
| 58 | 1 | (613.5, -904.5) |

36→37 的中心位移约 5.66px，37→38 约 7.21px，超过固定关联范围。
因此六条单帧轨迹不能证明六次短暂噪声，也不能排除同一移动缺陷。
下一步优先增加按附件运动补偿的关联证据，并保留当前基线对照；不靠扩大阈值消除断轨。
拓扑分类和采用门禁需在关联校准后继续完成。
