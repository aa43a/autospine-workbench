# 翼片低透明度边缘候选与上衣拆分清单

本切片消费已校验的 `selected-wing-hinges-v1` 包。原骨骼、根部选择、动画、Atlas 布局和上衣纹理逐字节保持不变；只改变原有翼片像素在预览附件之间的归属。它不是新的人工采用决定。

## 规则与回退

`wing-faint-edge-unique-owner-2px-v1` 只处理 alpha 1–7 的残余像素。在欧氏距离 2px 内必须只有一个原始 alpha>=8 组件，且该组件已有根部选择。所有距离均依据原始组件计算，不使用刚刚转移的像素继续扩张。

无邻近组件、多组件歧义、未选择组件及 alpha>=8 的残余均保留。转移时复制原 RGBA，不补色、不扩 alpha、不删上衣。重建逐像素校验全部 alpha 和非透明 RGB；回退直接使用原预览包。

逐像素明细单独保存为 `edge-ownership.json`，摘要通过 SHA-256 引用它，避免超过既有报告大小门禁。JSON Schema 位于 `schemas/wing-edge-preview-v1.schema.json`；语义 reader `wing_edge_preview.verify` 会重新分析并校验整个报告。

## 运行

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_edge_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --base ../tmp/r2b-wing-spine-v2/crino/preview-manifest.json --output-dir ../tmp/r2b-wing-edges/crino
$env:KEEP_PREVIEW='1'
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-edges ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

命令重放原包的完整来源后，发布独立内容寻址候选及可导入 Spine 的 ZIP。相同输入可重复运行，已有不同内容拒绝覆盖。官方验证器仍使用外置 spine-webgl 4.3.13，输出目标是 4.3.26。

保持新旧预览服务运行后，可将实际本机 URL 传给同帧比较器：

```powershell
node tools/compare-wing-edge-runtime.mjs 'http://127.0.0.1:7226/?character=crino' 'http://127.0.0.1:1444/?character=crino' ../tmp/r2b-wing-edges/comparison ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe'
```

比较器校验新旧 Runtime 和骨架身份一致，捕获 0/0.5/1/1.5/2 秒的同尺寸 framebuffer 并输出图片对照。这里的像素变化不是裂缝判决。

## 琪露诺结果与剩余问题

2,036 个低透明度像素转入翼片；1,883 个无邻近组件的低透明度像素及 45 个高透明度残余像素保留。没有多组件歧义项。

11 项针对性测试通过；官方 Runtime 121 帧的 Atlas 与独立原图参考最大像素差为 0。新旧方案对照中，setup 最大通道差为 1，摆动帧最大为 7。这说明源像素精确重建不等于经过过滤、分附件混合后的 framebuffer 完全一致。0.5 秒有 17 个像素下降到 alpha8 以下，1.5 秒有 14 个；这些是采样变化，未判定为裂缝或通过视觉生产验收。

上衣与四翼片共 17,354 个 alpha>=8 重叠像素，RGBA 完全一致数为 0。报告为每翼片保留重叠 bbox、数量和色差，并以 `source_layer_requires_semantic_split` 进入复核清单。这个清单只说明需要语义拆分，不是删除区域的遮罩；扩大 bbox 删除上衣会损害真实服装。

后续已新增 [上衣／翼片拆分遮罩编辑页](how-to-wing-split-review.md)，用于明确源层移除与保留区。边缘候选仍为 `needs_review`，没有生产授权。
