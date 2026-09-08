# 连续 alpha 像素边缘与候选锚点

本切片将完整纹理的 alpha≥8 像素单元边缘追踪为有向曲线，承接同帧走廊诊断。它不改变旧的像素中心对应、骨链、权重或动画。

## 方法与边界

每个可见像素只贡献与透明区域相邻的边，边方向使可见单元位于图像坐标的右侧。正常轮廓闭合，孔洞方向相反。对角接触顶点有多个出入边时，保留为歧义断点，不按任意转向规则跨接。

原有每个参与接缝对应的边界像素中心投影到自己的外露单元边中点，输出曲线、边索引、局部参数 `t`、按纹理弧长归一化的 `u`，以及 UV 三角形中的重心坐标。单元边都是单位长度，因此 `u=(edge+0.5)/edge_count`。

同一个像素有多条外露边时保留全部投影选项，标记 `ambiguous_projection`；投影不在 Mesh 内时标记 `unmapped_mesh`，不夹回三角形。唯一且可嵌入的锚点也只是 `candidate_anchor`，不能据此认定跨 attachment 配对正确。

这里提取的是阈值化像素单元边缘，不是双线性 alpha 等值线。旧的像素中心与新的单元边界相差半个像素，不能直接替换旧验收口径。当前输出完整曲线为后续局部选段提供依据，不将整个鞋轮廓直接绑定到腿侧短链。

## 入口与回放

设置 `PYTHONPATH=src` 后，从仓库根运行：

```powershell
python -m autospine_workbench.benchmark.alpha_curve_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-seam-remap/alice-v1.json `
  --output ../tmp/r2b-alpha-curves/alice-v1.json `
  --html ../tmp/r2b-alpha-curves/alice/index.html
```

`autospine.alpha-curve-anchors/v1` 引用精确重配来源。编译先重放原来源链和核对文件摘要；reader 重新生成并比对内容地址。JSON Schema 检查结构，语义 validator 检查边唯一性、闭合、锚点引用、参数和有限归一化权重。

复核页显示完整素材、轮廓与锚点：蓝色正常轮廓、橙色歧义路径、绿色唯一可嵌入锚点、红色多解或 Mesh 外锚点。无接缝关系的角色显示无候选，不算接缝通过。

## 下一项

在曲线上按原接缝证据选择局部弧段，消解尖角投影多解，再建立顺序一致的跨层参数配对。随后求解距离、切线与面积约束，并继续用冻结的同帧 CPU 走廊和官方 Runtime 分别验算。

本切片未运行形状求解器、未修改动画、未新增 Runtime 通过声明，所有工件均无生产权。
