# 查看实际像素分区候选

在仓库目录运行，不需要填写 SHA：

```powershell
$env:PYTHONPATH='src'
python tools/build-component-partitions.py --output ../tmp/r3a-component-partitions lumia huiye uuz yaomeng
```

项目需要已有当前全角色规划和有效动画来源。工具读取完整来源链，为加权 Mesh、分区 Mesh、语义异常三类图层生成候选。
打开输出目录的 `index.html`，选择角色。每层显示原纹理和实际像素分区，可关闭叠加、悬停查看区域及打开候选 JSON。

算法按 alpha≥8 的四连通区域记录 layer-local 半开游程 `[y,x_start,x_end]`，bbox 保持原画布坐标。
所有 0<alpha<8 像素独立保留，不根据距离分配给骨骼；透明像素不属于可见覆盖集合，原纹理字节始终保留。
各区域 owner 为 null，bone_ids 为空。连通域不等于左右归属、服装语义或可安全变形的 Mesh。

候选按内容地址保存在 `project-component-partitions/candidates-v1` 报告集合中，引用完整来源地址与原规划 SHA。
读取后用原图重新计算并验证结果。重复运行复用相同内容地址，不修改已保存绑定、语义或纹理。
报告是独立检查入口；本切片尚未把分区加入主工作台的正式绑定保存或 Spine 编译。

## 2026-09-09 实际结果

| 角色 | 图层 | 连通区域 | 低 alpha 残余像素 |
| --- | ---: | ---: | ---: |
| lumia | 5 | 8 | 5407 |
| huiye | 4 | 13 | 2573 |
| uuz | 6 | 13 | 6128 |
| yaomeng | 6 | 51 | 44845 |

全部 21 层可见像素无遗漏、无重复；6 项算法与文件长度测试通过，包括对角不连通、低 alpha 独立保留、坐标偏移、空层阻塞及来源/归属篡改拒绝。
这些结果不表示残余像素有错，更不构成 Mesh、接缝或官方 Runtime 验收。

下一步：明确区域语义及归属，保留多物件/遮挡异常，再形成能被编译器消费的分区决定。

## 区域归属草稿

新版报告支持点击区域或通过下拉框选择，填写语义、角色侧别及当前骨架中的 1–4 根骨骼。
点击「将当前选择写入草稿」后，可下载全部区域草稿；没有点击写入的表单选择不会导出。
「保留未归属」清除当前区域填写，「撤销至上次载入草稿」恢复最近一次载入内容（初始为空草稿）。
关闭页面前请下载草稿；页面不自动保存。载入 JSON 时会核对项目、输入、规划、全部候选及区域集合。
黄色低 alpha 残余本版不能指定归属。骨骼集合只记录复核意图，不表示已有权重或合法连续骨链。

在仓库中验证并封存下载的草稿：

```powershell
python tools/build-component-partitions.py --output ../tmp/r3a-component-ownership --draft C:/path/component-ownership-draft-lumia.json lumia
```

工具会重读当前来源，拒绝过期/跨项目草稿，并以内容地址保存到 `ownership-drafts-v1`；不会写入正式绑定。
2026-09-09 已生成四角色空草稿页面，85 个连通区域和 21 个低 alpha 残余记录均待复核。
9 项 Python/质量检查和 462 项 Web 回归通过。本轮未通过浏览器渲染检查，不宣称页面截图验收；未替用户提交区域归属。
