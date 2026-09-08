# 逐关系候选准入报告

将几何、原 alpha 边界增距、官方 Runtime 原生像素密度的目标合成变化整理为解释性报告。
所有结论仍为 authority:none / needs_review；这是审查工具，不是自动采用或发布策略。

```powershell
python -m autospine_workbench.benchmark.seam_admission_cli `
  --direct ../tmp/r2b-direct-alpha/crino/2641a6c5131ca76207f1169d8c7459202e3795c4e2146193f12a28073898c7c1.json `
  --runtime ../tmp/r2b-crino-runtime/report.json `
  --candidate ../tmp/r2b-seam-increment/crino-v1.json `
  --manifest ../tmp/r2b-seam-increment/crino/preview-manifest.json `
  --output-dir ../tmp/r2b-admission/crino-increment
```

报告和 Runtime 输入通过字节 SHA 绑定，candidate 与实际加载 manifest／文件清单相匹配。
验证全部 PNG 身份、点坐标／时间／关系、捕获矩阵完整性与重复项，并要求原／候选各121帧原有回归通过。
`read_admission` 重算本审查并比对内容地址；不替代上游全部算法编译 reader。

状态按以下顺序生成：几何失败→blocked_geometry，边界增距>2px→blocked_boundary_distance，
无目标样本→not_evaluated；候选区域 all 合成 alpha 下降超过1→review_runtime_alpha_loss，
仅 pair 下降→review_pair_alpha_loss，否则 sampled_no_new_regression。
1 个 alpha 单位容差只处理量化差异，不是经过校准的感知阈值。
通过这些已记录点不能证明未采样时刻／区域、重叠颜色、缩放或完整角色通过。

## 琪露诺 Runtime 验证

`tools/verify-seam-local-runtime.mjs` 增加可选 character 和 profile 参数。
`crino native-pair` 对全部311个已记录位置捕获 before／after、共享Atlas、1倍密度、pair／all，
共1244张局部图；另有242帧原有对照。没有抽取少量点代替全部311点。
新结果使用 seam-local-runtime/v2，明确 capture_matrix；旧Alice v1证据继续可读。
full profile保留两种密度、两种纹理和四种合成模式，但琪露诺本次没有执行该完整矩阵。

## 2026-09-08 结果

| 候选／关系 | 样本 | all alpha下降>1 | 新增all alpha<8 | 结论 |
| --- | ---: | ---: | ---: | --- |
| Alice原增量左 | 7 | 7 | 4 | 复核透明度退化 |
| Alice整段回退左 | 7 | 0 | 0 | 当前采样未发现新增退化 |
| Alice右 | 0 | 0 | 0 | 未评估，不能记为通过 |
| 琪露诺增量左 | 99 | 99 | 93 | 复核透明度退化 |
| 琪露诺增量右 | 212 | 212 | 191 | 复核透明度退化 |

琪露诺左右最大原生合成alpha损失分别为135／157；虽几何与边界增距通过，不能据此采用。
不将该结论外推成所有视图下肉眼可见的裂缝，亦不推断琪露诺 Atlas 问题已排除。
下一步验证琪露诺双侧整段回退是否恢复局部合成，并保住边界门槛；随后再建立组合候选与完整区域回归。
