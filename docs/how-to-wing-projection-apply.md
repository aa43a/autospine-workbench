# 应用主翼清理草稿与彩色翼面缺失发现

本切片校验上传的分组草稿，并以修正过层序的翼片后置包为目标。候选源纹理与后置包当前上衣必须具有相同内容身份，且来源拆分报告一致；这样既保留此前11笔清理，也不会因草稿生成于旧层序时而把层序改回去。

本次四组仍为 `uncertain`，用户实际进行了3笔局部移除。按局部笔画优先的语义共移除70,245个可见像素。没有把不确定组自动改为移除。

移除内容保存在 `projection/removed-topwear.png`，本轮原图在 `projection/original-topwear.png`，草稿和二值遮罩一并保存。原上衣可以由剩余与移除图片精确重建。骨骼、动作、UV、其他附件和翼片后置次序不变。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_projection_apply_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-back-order/crino/preview-manifest.json --candidate-source-dir ../tmp/r2b-wing-split-applied/crino --draft C:/Users/Administrator/Downloads/wing-projection-draft-v1.json --output-dir ../tmp/r2b-wing-cleaned/crino
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-cleaned ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

## 重要纠正：不能采用直接清除版

官方 Runtime 数值121帧通过、Atlas与候选原图参考最大通道差0，只证明包按当前素材正确播放。

查看清理后的0.5秒截图和独立 `wing-c0.png`，当前独立主翼组件主要是轮廓，完整彩色翼面来自上衣源纹理。移除上衣里的彩色翼面后，只剩轮廓。因此之前把问题概括为“两份完整主翼”不准确；源层之间不仅重叠，还存在颜色内容分散。

这不是用户笔画没有生效，也不是骨骼、层序或运行时没加载图片。该结果应保留为视觉不通过的诊断候选，不能替换为生产素材。移除图保存了彩色像素，没有数据丢失。

新旧同帧比较在0.5秒有24,523像素变化，20,629个像素降到alpha8以下。它们与完整彩色翼面消失的截图相符，不能沿用“只是微小边缘采样差异”的解释。

后续已新增 [封闭轮廓内的颜色转移候选](how-to-wing-color-transfer.md)，从保存像素恢复彩色主翼并使用原翼骨播放。区域外的挂坠与边缘残余保留，不强制配准或吸附；不再要求用户擦除同一批颜色。
