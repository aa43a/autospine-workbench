# 局部低alpha边缘归属候选

消费已定位的双线性采样邻域，尝试将残余的alpha 1–7像素转移给同一源层中的唯一邻近分区。该能力不会修改主权重或扩大网格，也不会自动采用结果。

## 转移条件

- 只检查定位报告中的texel并集，先重放捕获与定位报告，验证原候选内容地址。
- 原像素非零且alpha<8；所有目标分区在该位置均透明。
- 半径2源像素内只有一个分区拥有alpha>=8的原始支撑像素。新增边缘不参与下一次邻近搜索。
- 目标像素中心必须在该分区既有UV三角形内。

满足条件时原RGBA逐值搬移，原残余位置清零，其余像素保持原位。歧义、无邻近分区、网格未覆盖以及主体像素全部保留。更新派生Atlas tile、编辑器PNG和残余参照，骨架JSON、权重、UV、层序及动画字节不变。源像素搬移精确不等于Runtime合成逐字节不变，因为附件的变形、采样与混合位置不同。

## 复现

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.limb_edge_cli --source ../tmp/r2b-wing-limbs/crino/preview-manifest.json --locations ../tmp/r2b-residual-locations/review-v2/locations.json --capture ../tmp/r2b-residual-locations/capture.json --manifest docs/benchmark/manifest-frozen-v1.json --output-dir ../tmp/r2b-limb-edge/crino
python -m unittest tests.test_limb_edge_transfer tests.test_residual_locations tests.test_quality -q
node tools/verify-ownership-runtime.mjs ../tmp/r2b-limb-edge ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

原包与新包分别启动官方预览服务后，将实际地址传入：

```powershell
node tools/compare-wing-edge-runtime.mjs 'http://127.0.0.1:14058/?character=crino' 'http://127.0.0.1:9345/?character=crino' ../tmp/r2b-limb-edge/comparison ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' --all-frames
```

`--all-frames` 要求两侧骨架JSON完全相同，逐帧比较0–2秒的121个时刻；只在代表帧保存截图。原来的五帧模式与仅层序变化模式继续可用。

## 2026-09-09：候选未采用

| 源层 | 候选texel | 转移 | 透明跳过 | 无可靠邻近区域 |
|---|---:|---:|---:|---:|
| handwear | 304 | 5 | 22 | 277 |
| legwear | 96 | 0 | 14 | 82 |
| footwear | 202 | 5 | 32 | 165 |

共10个低alpha像素被转移，原始候选不变。12项针对性测试及Schema检查通过；新包官方spine-webgl 4.3.13的121帧结构／数值／原图参考检查通过，导出目标仍为Spine 4.3.26。

但是原／新包同帧比较出现退化信号：第30帧及第116帧各有1个原本alpha>=8的像素降到阈值以下，没有alpha8增益。全段最大RGBA通道差5；setup仅4个显示像素出现最大1的量化差异，没有alpha8跨越。

这不直接证明产生了可见裂缝，但也不足以批准改变最终资产。**保留 `363accf4f4c4d7b93e00066b9a187611aa9aed8d7c48411bf76376d9f915778d` 为未采用候选，继续使用原合并包。** 不删除异常采样、不放宽阈值、不宣称残余已解决。

这个实验说明：唯一空间邻近与网格覆盖不足以证明运动归属。后续若继续自动转移，应补充动态相对运动一致性或更明确的接触证据；不能为了消除微小统计差异反复调整四肢主权重。
