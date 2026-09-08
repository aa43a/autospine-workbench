# 连续 corrective Bake 与接缝诊断

`autospine.continuous-corrective-preview/v1` 在已有离散组合候选上建立独立 profile `bilinear-field-linear-bake-v1`。不改写原组合工件、权重、绑定或残余决定。

主关节范围 0–60°、远端范围 −30–30°。对已有网格角度表中的局部 deform offsets 做双线性插值，沿两秒周期生成 30 FPS 的 61 个线性关键帧：主关节为 `30*(1-cos(pi*t))`，远端为 `30*sin(pi*t)`。首尾显式归零。这是受限诊断动作，不是 walk 或 wave 的正式动作适配，也不是扩大原单关节安全范围。

## 生成

在仓库根目录设置 `PYTHONPATH=src`：

```powershell
python -m autospine_workbench.benchmark.continuous_corrective_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-combined/alice-v1.json `
  --directory ../tmp/r2b-continuous/alice `
  --output ../tmp/r2b-continuous/alice-v1.json `
  --zip ../tmp/r2b-continuous/alice-v1.zip
```

另两角色为 lingxian、crino。输入组合候选及其 atlas/width/mesh/skeleton 链必须精确重放。输出新 CAS 地址、ZIP、Runtime JSON、Atlas、PNG 和 Editor 图片；`read_continuous` 重建并比较内容地址。

官方 Runtime 使用[已有验证工具](how-to-ownership-spine43.md)，把输出根目录换成 `r2b-continuous`。JSON 目标保持 4.3.26，实际 npm Runtime 版本单独记录。

## QA 的范围

三个角色共 12 个区域在该受限动作下通过几何采样。Alice 两处腿鞋最大增距为 10.13/13.75 px，琪露诺为 8.54/7.84 px，均超过诊断阈值。铃仙没有可用的跨附件邻近点，琪露诺手臂也未覆盖。来源中更大角度的三处失败继续保留。

- 以 60 FPS 共 121 个时刻重建线性 bone/deform 插值，包括所有 bake key 与中点。
- 检查面积比 0.5–2、边长拉伸 ≤2、翻转、有限数和 loop 首尾误差 ≤1e-7 px。
- 记录最大相邻帧顶点位移；目前没有以该值代替速度、加速度或视觉平滑度验收。
- 在 setup 时寻找不同附件间 4 px 内的邻近顶点，固定对应关系，再记录动作中距离增长。增长超过 2 px 标为 blocked。

接缝对应关系仅为几何诊断候选：不保证顶点位于真实 alpha 接口，也不覆盖所有边界。没有对应点时记录 `unpaired_regions`；即使测得距离稳定，`seam_coverage` 仍为 `unproven`。正式接缝验收还需要 alpha/contact 证据、对应关系复核和动态栅格检查。

`results` 保留来源的离散宽角度 QA，当前受限动作的结果在 `bake_qa` 中，不能用窄范围通过覆盖原 blocked 状态。所有工件保持 `authority:none`、`production_authorized:false`；完整角色、残余和生产门禁继续保留。

下一步应根据测得的接缝增长建立 joint/contact seam 约束候选，验证腿与鞋的共同边界运动，再扩展连续动作覆盖。不能只继续调宽度系数或隐藏裂缝。
