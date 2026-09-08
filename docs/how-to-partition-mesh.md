# 分区多区域 Mesh/Weight 实验

`build-partition-mesh` 从原始无损分区生成左右区域独立的网格与权重，
直接检验双侧资产的变形问题。它不要求把候选伪装成已批准绑定。
残余沿用原分区完整保留，4px残余试算不会隐式采用。

```powershell
python -m autospine_workbench.benchmark build-partition-mesh `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --partitions ../tmp/r2b-partitions/alice-v1.json `
  --html ../tmp/r2b-region-mesh/alice-v1.html `
  --output ../tmp/r2b-region-mesh/alice-v1.json
```

## 数据和数值边界

每个区域保持原分区纹理和PSD偏移；在原规则网格生成器上独立建网格。
腿/臂使用对应侧三骨链的关节平面权重，鞋使用对应 foot 骨单骨权重。
不会让左侧顶点受右侧骨骼影响。每个顶点最多三个影响并归一化，
setup 局部坐标通过 LBS 重建验证。

每条链的每个关节分别测试 -90/-60/-30/-15/0/15/30/60/90 度，
包括髋、膝、踝以及腕等远端关节。检测三角形翻转、面积比和边长拉伸。
实验门槛为面积比0.5–2、边长比≤2；这些探针不证明连续时间或组合动作安全。
另以像素中心检测alpha>0区域是否落在网格三角形内；任何漏覆盖均阻塞。
该检查不是纹理采样/raster或官方Runtime认证。

独立 `partition-mesh/v1` 存入16MiB网格工件存储；reader 重建完整来源和计算结果。
旧Mesh/profile不修改。报告记录原分区、骨架、每区域纹理摘要和残余文件摘要，
残余状态为 preserved_unbound，所有权威字段保持 none/false。

## 首批真实结果

六层成功生成12个区域网格，但12个区域均未通过完整QA：

- 六个腿区域、两个手臂区域在远端关节探针出现翻转；Alice右脚+30°已出现翻转。
- 四个鞋区域单骨旋转没有翻转，但均有少量alpha边缘像素漏覆盖。
- 其他部分区域也有覆盖缺口；这些像素仍存在于原分区纹理，没有删除。

失败候选完整保存，可在页面展开逐关节结果。
这是可复现的失败基线，不是R3里程碑通过，也未输出新的Spine动画包。
详见[验证记录](benchmark/partition-mesh-2026-09-08.json)。

下一步先补齐全alpha网格覆盖，再修正踝/腕过渡区域的权重与拓扑，
随后接入腿部组合动作和跨层接缝QA。继续保留当前失败基线作对照，不能通过缩小探针范围掩盖问题。
