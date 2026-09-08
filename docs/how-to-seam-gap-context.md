# 新增空白的局部支撑证据

本分析读取连续锚点和固定 deform 增量两个已有 bundle，不改变动画、权重或采用状态。
入口为 `python -m autospine_workbench.benchmark.seam_gap_context_cli`，参数：

```powershell
python -m autospine_workbench.benchmark.seam_gap_context_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --output-dir ../tmp/r2b-gap-context/alice
```

输出规范化内容地址命名的 JSON 和 `index.html`。重跑 `analyze` 并比较内容地址即可复核。
源报告通过 source_anchor_sha256 关联；实际使用的骨架和纹理逐文件核验 SHA。
四处关系各 61 帧重新计算原 common-frame 指标并逐项比对，分类计数必须完整覆盖新增空白。
这不替代上游编译链的完整精确 reader。

固定 profile `alpha8-opposite-rays4-v1` 在同一 ROI、alpha8、原共同走廊上，
对每个新增空白沿水平、垂直和两个对角方向搜索最多 4 个栅格步的首个占用点：

- `opposed_attachment_support`：至少一对相反方向分别命中两张不同的独占附件。
- `single_attachment_support`：所有命中仅来自同一附件，且射线未被 ROI 截断。
- `uncertain`：混合、重叠、无支撑或 ROI 截断等证据不足。

对角的 4 步距离是 4√2 px，并非各向同性半径。标签描述局部支撑，不证明真实裂缝或外轮廓变化。
与外部连通的敞开裂缝仍可有相对支撑；单附件支撑也可能遗漏较远的另一侧，不自动豁免。
仅分析新增空白，既有裂缝、重叠、alpha 连续性仍需原 QA；CPU 结果不宣称官方 Runtime 栅格验证。

2026-09-08 实测（跨帧像素样本总数，非独立裂缝数）：

| 关系 | 新增 | 相对支撑 | 单附件支撑 | 不确定 |
| --- | ---: | ---: | ---: | ---: |
| Alice 左 | 7 | 7 | 0 | 0 |
| Alice 右 | 0 | 0 | 0 | 0 |
| 琪露诺左 | 99 | 38 | 52 | 9 |
| 琪露诺右 | 212 | 21 | 191 | 0 |

铃仙没有接缝候选，不计为通过。三角色逐帧重放通过，候选全部保留 needs_review。
下一步优先定位 Alice 左侧 7 个样本的实际接缝位置，并补充跨帧轮廓运动证据；
在分类校准前，不据此自动选择增量或授予生产权。
