# 从已保存像素恢复运动主翼颜色

上一版清理暴露出颜色归属问题：独立翼片主要是轮廓，彩色翼面实际位于上衣层。本切片直接消费保存的 `projection/removed-topwear.png`，不要求用户重画或重复擦除。

## 规则

`unique-closed-alpha-color-transfer-v1` 对每片原翼纹理使用 alpha>=8 的轮廓作为边界，在一像素外部 padding 上做四邻接背景泛洪。无法连到外部的像素构成封闭区域；至少16个封闭内部像素才允许生成颜色转移候选。开放轮廓不自动闭合，不使用凸包、膨胀或最近邻补齐。

将保存图像素按原画布偏移映射到各翼片。只在唯一合格封闭区域内转移；多个区域匹配或不匹配的像素均保留在 `color/unassigned.png`。不变形配准、不生成颜色、不向外扩展纹理覆盖。

转入图按 `donor over original outline` 与原轮廓合成。原轮廓和转入图分别保存。反向放回画布后，所有转入图加未归属图必须逐像素重建原 donor 的 alpha 与全部非透明 RGBA。

仅替换四翼片的编辑器 PNG 和对应 Atlas 页面内容。清理后的上衣、残余翼层、UV、Atlas 布局、根部、骨骼、动画和后置层序均保持不变。候选绑定源清理报告和 donor SHA，reader 可重放完整输出报告。

## 运行

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_color_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-cleaned/crino/preview-manifest.json --output-dir ../tmp/r2b-wing-color/crino
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-color ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

输出为 Spine 4.3.26 局部候选，验证使用外置官方 spine-webgl 4.3.13。ZIP 中 `editor/skeleton.json` 可与 images 目录一同导入。

## 2026-09-09 结果

| 翼片 | 封闭内部像素 | 转入保存像素 |
|---|---:|---:|
| C0 | 16,160 | 21,758 |
| C1 | 16,939 | 21,735 |
| C2 | 1,922 | 5,956 |
| C3 | 3,155 | 6,138 |

转移包含轮廓自身的覆盖区，所以转入数可大于封闭内部数。共55,587像素转入，无归属歧义；14,658像素仍在封闭区域外。查看未归属图，其中包含四个挂坠及背景边缘，不把这些像素强行贴到主翼。

7项针对性测试通过，包括封闭／开放轮廓、坐标偏移、歧义保留、逐像素重建、幂等、来源变更拒绝、其他资产不变和 Schema。官方 Runtime 121帧通过，Atlas与候选原图参考最大通道差0。

与仅剩轮廓的上一版相比，0/0.5/1/1.5/2秒分别增加12,984/12,951/12,984/12,969/12,984个 alpha>=8 framebuffer 像素，没有 alpha8 可见像素损失。查看两个摆动方向截图，彩色主翼恢复并随原翼骨运动，未出现此前那份明显的静态主翼。

这是局部颜色归属方向成立的证据，不是完整角色生产验收。剩余挂坠、边缘残余、颜色与轮廓接合处仍需复核。下一步应对挂坠建立独立归属及挂接候选，再合回完整角色；无需继续擦除已恢复的主翼颜色。
