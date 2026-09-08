# 亚像素 alpha 等值轮廓诊断

新增 `autospine.seam-gap-isoline/v1`，保留旧栅格单元边界报告，逐像素比较亚像素位置与朝向。
这是 CPU 样本场的近似诊断，不修改原动画或采用决定。

```powershell
python -m autospine_workbench.benchmark.seam_gap_isoline_cli `
  --before ../tmp/r2b-continuous-anchor/alice-v1.json `
  --after ../tmp/r2b-seam-increment/alice-v1.json `
  --before-dir ../tmp/r2b-continuous-anchor/alice `
  --after-dir ../tmp/r2b-seam-increment/alice `
  --output-dir ../tmp/r2b-gap-isoline/alice
```

输出内容地址 JSON 与复核页。深蓝／深绿线表示对应附件的最近点连线与外向法向。
`read_isoline` 重算报告并比对地址；source_boundary_sha256 绑定旧栅格报告。

## 数值定义

在当前 CPU alpha 样本中心间构造双线性插值，每个跨阈值单元细分为 4×4 子单元，
线性求边上的 alpha=8 交点，以弦段近似子单元内曲线。
法向取弦段中点处插值场的负梯度，并转换到世界 Y 向上。
这不是直接在每个亚像素点重新执行 UV 纹理采样，也不是 GPU 等值轮廓；未给出全域误差保证。

四交点鞍点、恰好命中阈值的角点、近零梯度不任意连线；
样本 4px 范围内存在这类未解决单元时，标为 unresolved_isoline_neighborhood。
ROI 外不补零、不造外轮廓。仍保留所有并列最近弦段及原距离／朝向判据。
局部连通性继续引用原 alpha8 占用栅格，不能当作亚像素拓扑证明。

## 2026-09-08 结果

| 关系 | 相向边界 | 最近边界不相向 | 距离／边界证据不足 |
| --- | ---: | ---: | ---: |
| Alice 左 | 7 | 0 | 0 |
| Alice 右 | 0 | 0 | 0 |
| 琪露诺左 | 0 | 58 | 41 |
| 琪露诺右 | 0 | 152 | 60 |

全部 318 个跨帧像素样本保留。铃仙无接缝候选，不计为通过。
Alice 从栅格边界的相向 1／并列歧义 6，变为亚像素近似的相向 7。
对这 7 个样本另外运行 8×8 细分，分类全部一致，最大最近距离变化约 0.01662px。
该精度对照只覆盖 Alice 七点，不能外推为其他角色的全域精度认证。

当前证据更支持 Alice 存在局部夹缝，尤其第 36–38 帧的连续轨迹；仍未确认生产缺陷或采用候选。
下一步应把这些位置对应到直接 UV／alpha 采样或同帧官方 Runtime 局部截图，
校准空白宽度与可见性，再决定局部修正或门禁。不能把琪露诺的不相向／证据不足当作自动通过。
