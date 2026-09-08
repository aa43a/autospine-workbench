# 共享源纹理分区 v2

这一步承接独立的 v1 ownership 分区与已经存在的全alpha区域网格，
将“一张源图层 → 左右分区 → 每区骨链和混合权重 → 共享源纹理”写入可重放工件。
没有重做分区算法，没有移动残余像素，没有采用残余复核草稿或远端权重实验。

```powershell
python -m autospine_workbench.benchmark.shared_partition_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --mesh ../tmp/r2b-region-mesh/alice-coverage-v2.json --html ../tmp/r2b-shared/alice-v2.html --output ../tmp/r2b-shared/alice-v2.json --zip ../tmp/r2b-shared/alice-v2.zip
```

每个源图层在ZIP中只有 `source.png` 与 `ownership.png`。左右区域引用同一源PNG；
不再把左右遮罩PNG作为这份工件的两张纹理。`partition-v2.json`包含几何、源纹理UV、
完整逐顶点混合权重、骨链、旧区域网格身份、QA、待复核状态和无绑定残余。
ZIP内manifest不包含自身ZIP地址，外部报告额外记录 `zip_sha256`，避免循环身份。

ownership的1／2／3分别表示左、右、残余。三者是互斥像素所有权，
必须包括alpha为零时的隐藏RGB，合并后逐字节重建源RGBA。
关节附近允许多骨影响；`weight_support`统计纯单骨与过渡顶点，不能被解释为新的硬像素分割。
当前只支持已有的左右组件及其1／3骨链，没有宣称任意数量分区或任意服装自动分区已经完成。

`combine_layer`检查源图、ownership、旧左右区域像素、UV到画布坐标映射和骨影响。
它保留原始权重及骨架，不产生新的置信度数字；区域置信度标记uncalibrated，残余标记unresolved。
`read_shared`重建完整来源、v2报告和确定性ZIP，并拒绝内容不一致。
源码分为纯分析、CLI/store编排和view三个新模块，旧模块原位保留。

## 当前结果与边界

三个角色6个源图层、12个左右运动区均通过RGBA与共享UV检查。
残余可见像素数：Alice 570、铃仙30,893、琪露诺12,361，和旧分区一致。
原区域变形QA沿用旧结果：4个刚性鞋区为数值候选，8个三骨区域仍阻塞；全部绑定仍待复核。

共享纹理不等于可直接交给Spine。现有区域网格可能跨越ownership边界，
直接替换为源PNG会采样到其它区或残余的像素。Spine Adapter尚未实现该ownership的采样隔离，
因此每层都有 `shared_texture_ownership_not_compiled` 目标阻塞原因。
它是版本中立实验包，不是Spine运行包，不能通过删除掩码或忽略残余绕过阻塞。

下一步优先实现分区边界与纹理采样隔离的QA，确定共享源纹理下的边界裁剪方案，
再与区域Mesh及组合动作验证连接。残余始终作为明确的不确定区域保留；
需要改变归属时再生成独立候选，不能把“继续开发”当成采用残余草稿。

24项针对性测试通过，覆盖隐藏RGB、未知owner、错误源图／区域、UV错位、篡改拒绝，
并回归旧分区、残余与网格。三个真实Schema及ZIP清单／内容地址检查通过。
Alice完整来源回放通过，页面经Chrome截图检查；未运行完整Python/Web套件或官方Runtime。
详见[实验记录](benchmark/shared-partitions-2026-09-08.json)。
