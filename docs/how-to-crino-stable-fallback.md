# 琪露诺双侧回退验证与候选组合收敛

复用现有整段回退、Runtime捕获和逐关系审查工具，不新增求解器、合同或自动采用策略。
选择 `layer-006-l`、`layer-006-r`，恢复整条附件动画轨道，避免逐帧开关。

```powershell
python -m autospine_workbench.benchmark.seam_stable_fallback_cli `
  --before ../tmp/r2b-continuous-anchor/crino-v1.json `
  --after ../tmp/r2b-seam-increment/crino-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/crino `
  --after-dir ../tmp/r2b-seam-increment/crino `
  --follower layer-006-l --follower layer-006-r `
  --output-dir ../tmp/r2b-stable-fallback/crino
```

## 2026-09-08 验证结果

- 六个候选区域几何通过，原边界样本及对应保留。
- 左／右边界增距为1.952775／1.698898px，均低于2px。
- 相对reference，两侧均无新增空白帧；共同走廊峰值3→3、2→2，原有空白仍在。
- 官方4.3.13 Runtime原／回退各121帧回归通过，共242帧。
- 对全部311个已记录点，在原生密度、共享Atlas、pair/all模式下捕获1244张图。
- 622组原／回退配对的目标RGBA完全一致；完整32×32世界像素ROI的PNG也全部一致。
- 回退报告、逐关系报告的Schema和精确reader通过，所有文件SHA及ZIP字节重放通过。
- 本切片没有修改算法代码，未重复运行已通过的50项单元测试，也未运行全量测试。

输出候选地址：`ea482f812a1c6650170baadb4260b4165357e2890a4b9c6ef81dd1855c97939b`。
Spine预览包位于工作目录外层 `tmp/r2b-stable-fallback/crino/preview.zip`。
报告仍为 needs_review / authority:none；局部一致不能证明完整角色视觉验收。

## 当前保守候选组合

| 关系 | 轨道来源 | 边界增距 |
| --- | --- | ---: |
| Alice左 | reference整段回退 | 1.968960px |
| Alice右 | 保留increment | 1.727884px |
| 琪露诺左 | reference整段回退 | 1.952775px |
| 琪露诺右 | reference整段回退 | 1.698898px |

该组合消除已验证的增量透明度退化，同时保留Alice右侧几何改善。
Alice右侧仍缺少对应的局部Runtime目标采样，报告必须保留未评估；铃仙没有接缝候选，不作为接缝通过样本。

下一步围绕这组固定组合统一预览入口与回归清单，补足Alice右侧和原有空白的视觉覆盖，
不继续全局调权重或增加纵向诊断阶段。采用决定、完整区域颜色／重叠、未覆盖区域和生产门禁仍独立保留。
