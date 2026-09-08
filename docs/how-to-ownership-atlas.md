# 分区共享纹理页的采样隔离

把partition v2的ownership掩码编译到派生PNG中：每个源图层对应一个纹理页，
左、右和残余占三个不重叠区域，共享该页。源PNG、ownership、v1/v2分区都原样保留。
这是源纹理的派生打包布局，不是继续使用源PNG的原位UV。

```powershell
python -m autospine_workbench.benchmark.ownership_atlas_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --partitions ../tmp/r2b-shared/alice-v2.json --html ../tmp/r2b-isolation/alice-v1.html --output ../tmp/r2b-isolation/alice-v1.json --zip ../tmp/r2b-isolation/alice-v1.zip
```

每块区域保留原始整幅图层尺寸，只有该owner的像素写入，包括alpha为零时的隐藏RGB。
其它像素和外围2px隔离边全部为零。这样区域采样不会读到另一owner的可见像素。
代价是约三倍的未压缩像素空间；首版优先确保行为清晰，尚未裁掉各区域空白边。
布局从1／2／3列中按面积和最长边确定，最大边4096、最大页像素8Mi，超限明确阻塞。

## 坐标与采样合同

- `geometry.source_uvs`保留旧图层局部UV。
- `geometry.uvs`为新的整页归一化UV；`uv_space=normalized_page`。
- 原顶点、三角形、逐骨局部坐标、权重和残余状态不变。
- 仅支持level-0 linear、无mipmap、clamp-to-edge，固定UV位于各自区域范围内。
- 逐像素检查每块区域等于对应owner的遮罩源图，并检查全部2px透明隔离边。
- 线性过滤足迹最多接触区域外一圈纹素；在固定UV域和此采样合同内，它只接触透明隔离边。
- 自动测试使用独立双线性采样器，在边界／角点／亚像素点与遮罩图比较，绝对容差1e-9。
  像素字节和隔离边仍要求完全一致。此证据不覆盖mipmap、各向异性过滤、动态UV或所有GPU实现。

目前未生成Spine JSON/Atlas文本：Spine附件通常需要局部region UV，Adapter不能直接把整页UV
当成region UV使用。下一切片应显式接入这项坐标转换和纹理页布局，再做目标加载与固定帧采样检查。
当前阻塞项变为`ownership_atlas_adapter_not_integrated`；旧分区v2的原位共享纹理阻塞状态不改写。
现有变形失败、残余未绑定和人工复核状态继续保留。

## 真实样本与验证

三个角色共生成6页，12个运动区域和6个残余区域独立隔离。
全部页通过像素重建、透明隔离边、UV域检查；真实几何、权重、残余与输入逐字段一致。
三个报告通过Schema与ZIP哈希检查。Alice完整来源回放通过，页面通过Chrome截图检查。
18项针对性测试通过，包含双线性边界采样、源图／UV错误、资源限制、篡改拒绝和旧网格回归。
未运行完整Python/Web套件、官方Runtime或组合动作测试。

代码位于`asset/joints/ownership_atlas.py`与独立`benchmark/ownership_atlas_cli.py`，
用原16MiB报告存储与32MiB ZIP上限。精确reader从完整partition v2来源重建页面和包，
不会通过修改待复核决定使输出获得发布权。
见[验证记录](benchmark/ownership-atlas-2026-09-08.json)。
