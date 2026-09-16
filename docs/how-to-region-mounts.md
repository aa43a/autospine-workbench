# 将已有区域绑定到骨骼

同一源图层包含多个已经分离的区域时，可一次为指定区域选择父骨骼，
不重新切纹理、不改变绘制顺序。当前适用于静态单骨加权区域；有附件动画、
绘制顺序动画或混合权重的区域会拒绝处理。输入只使用区域 ID 和骨骼 ID，
目标转换位于 Spine 4.3.26 adapter，不包含角色名特例。

工作台 API：`GET/POST /api/projects/{project}/automation/character/region-mounts`。
POST 必须使用与其他编辑入口相同的同源与 intent 请求头。
先 GET 获取当前 `head_sha256`；提交 `action: replace`、`expected_head_sha256`、
`job_id` 和如下 decision：

```json
{
  "schema": "autospine.region-mount-decision/v1",
  "source_bundle_sha256": "当前候选的64位内容地址",
  "parents": {"已有区域ID": "chest"},
  "decision_source": "human_confirmation",
  "reversible": true
}
```

父骨骼必须存在，所有选中区域必须仍为 static_reference。一次最多 64 个。
替换操作完整替换本阶段映射，不是追加。撤销提交 `action: revoke` 和当前
`expected_head_sha256`；版本记录只追加，旧候选与源素材保留。
保存不代替 Runtime 和整角色视觉验收；实际修改在下次构建中执行。

构建先重现已有自动边缘处理，再校验精确来源并应用区域挂接，然后执行
已确认的分区后排除。改变其他构建来源会拒绝套用旧映射，需要在新候选上
重新检查；本版不会跨来源猜测迁移决定。

转换保留每个顶点的 setup 世界位置，以目标父骨骼逆矩阵重算局部坐标；
保持图集、纹理、UV、三角形、slot 顺序与已有动作。数值参考重新生成，
逐帧比较未选区域，禁止改变邻近部件。未选静态区域仍标为待处理。

2026-09-16：琪露诺独立翼轮廓及上衣内四个翼区域使用同一通用合同随 chest。
任务 `job-a1d11e2ed4b540eab75486cde9081efd`，候选
`fc2a0b083793ef2e5e6c4e611e9d3897cb0c9f71515d18428911fabb9de0b7a5`，
官方 Runtime 四动作 1,028 帧通过，最大顶点误差约 0.000137 px；
setup 对照无新增或缺失可见像素。两处未确认残余在此版本中仍保持静态。
随后用户明确允许排除两处残余，后续候选单独保存验收。
