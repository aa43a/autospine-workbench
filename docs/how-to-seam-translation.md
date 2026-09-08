# Alpha 支持的接缝平移约束实验

本切片尝试用共同运动减少腿／鞋分离，并把失败保留为可重放结果。新 profile 为 `alpha-supported-rigid-translation-v1`，不改写原连续动画或决定。

## 候选条件与算法

只在单骨附件与包含该骨骼的多骨附件之间找对应关系。setup 顶点相距不超过 4 px，两个顶点的源图片 UV 附近 5×5 像素窗口都必须含 alpha ≥8 的像素，且至少有三个对应点。多个可能驱动附件时不自动选择。记录实际顶点索引、骨骼索引和 pending 复核状态。

在 30 FPS 的每个 key，将 setup 点对偏移随末端骨骼旋转，计算各点需要的世界位移，取等权最小二乘平移量。整只鞋平移，不缩放、不修改绑定或权重；位移上限 16 px，超过时裁限并记录。将世界位移反变换到单骨局部 deform，首尾归零。

重新以 60 FPS 采样实际 bone/deform 插值，检查网格、loop 和固定点对增距。来源的所有邻近点与本次 alpha 支持的子集分别比较，避免仅筛掉失败点后宣称通过。alpha 窗口只证明附近存在纹理，不证明已找到真实接触边界，`alpha_contact_coverage` 保持 `unproven`。

## 真实结果

|关系|alpha 点对数|原全部点对增距 → 约束后|alpha 子集增距 → 约束后|
|---|---:|---:|---:|
|Alice 左腿／鞋|9|10.13 → 11.01 px|6.36 → 5.90 px|
|Alice 右腿／鞋|7|13.75 → 11.53 px|8.13 → 5.66 px|
|琪露诺左腿／鞋|7|8.54 → 7.78 px|7.30 → 6.00 px|
|琪露诺右腿／鞋|7|7.84 → 4.38 px|6.02 → 4.38 px|

12 个区域的受限动作网格检查仍通过；鞋保持刚性，没有新增面积拉伸。但四处均超过 2 px 接缝增距阈值，Alice／琪露诺输出 `blocked`。铃仙无符合条件的跨附件对应，输出 `candidate_noop`，不代表人工复核或接缝通过。全部候选未采用。

结果说明单一平移不能消除该组点对的非一致位移。下一项应先建立真实 alpha 接触轮廓与共同边界对应，再尝试局部过渡约束；继续使用原来源做对照，不能只提高平移上限或放宽接缝阈值。

## 生成与播放

在仓库根目录设置 `PYTHONPATH=src`：

```powershell
python -m autospine_workbench.benchmark.seam_translation_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-continuous/alice-v1.json `
  --directory ../tmp/r2b-seam-translation/alice `
  --output ../tmp/r2b-seam-translation/alice-v1.json `
  --zip ../tmp/r2b-seam-translation/alice-v1.zip
```

换用 lingxian／crino 可生成另两角色。CLI 精确重建连续源链，reader 按 `source_continuous_sha256` 重放后核对新 CAS 地址。所有纹理文件保持原内容，新增的只有诊断动画和报告。ZIP／逐文件摘要继续校验。

使用已有 `tools/verify-ownership-runtime.mjs`，把第一个参数设为 `r2b-seam-translation` 的绝对路径；依赖与参数见[Runtime 说明](how-to-ownership-spine43.md)。JSON 目标 4.3.26，实际官方 Runtime 为 4.3.13。可播放不代表接缝验收，完整角色与发布权继续阻塞。
