# 官方 Runtime 同帧局部合成

本切片针对 Alice 已定位的七点，使用外部官方 `@esotericsoftware/spine-webgl 4.3.13`，
读取目标为 Spine 4.3.26 的两版候选。未重新实现 Runtime parser、FK 或 renderer。

```powershell
node tools/verify-seam-local-runtime.mjs `
  ../tmp/r2b-continuous-anchor ../tmp/r2b-seam-increment `
  ../tmp/r2b-direct-alpha/alice/b6b05d23c9e08ac64505e73173ef89c737f81a28b8c073e3e05d325ae9a0af95.json `
  ../tmp/r2b-local-runtime ../tmp/spine43-verification `
  'C:/Program Files/Google/Chrome/Application/chrome.exe'
```

输出 report.json、224 张局部 PNG、原／增量并排页面。脚本校验所加载 bundle 文件的 SHA，
记录 Runtime、变换后的 harness、可选 framebuffer hook、输入报告和 manifest 的字节身份。
源报告与 bundle 必须由调用者选用同一已核验链；此工具不替代 Python 完整 reader。

每点比较 before／after、1／4 倍 framebuffer 像素密度、共享 Atlas／独立图参考，
以及 driver、follower、pair、all 四种渲染。all 仅指 bundle 中现有候选区域，并非完整角色。
ROI 为以原像素单元对齐的 32×32 世界像素区域；4 倍密度记录原像素单元内的 16 个 framebuffer 像素。
相机及附件显示状态在每次捕获后恢复。原 harness 未加载 hook 时行为保持不变。

本次 Chrome/SwiftShader 开启抗锯齿，透明 framebuffer，premultipliedAlpha=true；
实际 RGB/alpha blend factors 为 ONE、ONE_MINUS_SRC_ALPHA。
报告保存原始 readPixels RGBA，PNG 仅为查看而将预乘 RGB 解预乘。测量不使用截图背景。
未进行硬件、过滤模式、PMA 设置全矩阵扫描。

## 2026-09-08 实测

原生密度下双附件合成 alpha（0–255）：

| 帧 | 原动画 | 增量候选 |
| --- | ---: | ---: |
| 34 | 30 | 9 |
| 36 | 30 | 6 |
| 37 | 40 | 10 |
| 38 | 27 | 3 |
| 52，第一个点 | 24 | 1 |
| 52，第二个点 | 64 | 11 |
| 58 | 13 | 7 |

七点 alpha 全部下降，四点低于 alpha8；CPU 直接合成预测与 Runtime 相差不超过 1 个 alpha 单位。
1／4 倍密度、四种模式的目标单元 RGBA，在共享 Atlas 与独立纹理参考间完全一致。
pair 与现有候选区域 all 在这些目标像素一致，没有其他已导出附件遮住这处空白。
这确认了当前渲染条件下的透明度退化，不能据此推断所有缩放条件下均可见，
也不能将其升级为完整角色视觉失败或全局排除 Atlas 问题。

原动画与增量各 121 帧既有 Runtime 编码／运动对照通过，合计 242 帧。
224 张局部图已校验 SHA；这次是实际官方 Runtime 证据，不是 stub。

## 下一步

保留增量候选未采用。当前证据不支持先改 Atlas padding 或全局权重。
下一步以原连续锚点动画为回退基线，对 Alice 左侧增量做稳定的整段／逐关系准入：
同时检查边界增距、网格、合成透明度损失及重叠颜色，避免逐帧开关造成跳变。
其他角色仍需单独验证，不能由 Alice 七点外推全角色采用权。
