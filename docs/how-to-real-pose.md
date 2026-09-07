# R2-B：运行真实 DWPose 并检查观测

已接入 DWPose WholeBody ONNX CPU，独立 venv，不改核心依赖。
首版假定完整画布内只有一个角色，没有运行人物检测，不支持多人选择。
真实运行不等于关节正确；三个开发角色的 GT 仍为零，R2-B 精度验收尚未完成。

## 安装与模型

在仓库目录运行：

```powershell
python -m venv ../tmp/pose-runner-env
../tmp/pose-runner-env/Scripts/python.exe -m pip install -r requirements-pose-runner.txt
```

本次已完成安装及下载，模型位于 `../tmp/pose-models/dwpose/dw-ll_ucoco_384.onnx`。
模型134,399,116字节，SHA256为
`724f4ff2439ed61afb86fb8a1951ec39c6220682803b4a8bd4f598cd913b1843`。
Runner 只接受此固定权重，不在导入或执行时自动下载。
[固定模型文件](https://huggingface.co/yzd-v/DWPose/resolve/1a7144101628d69ee7a3768d1ee3a094070dc388/dw-ll_ucoco_384.onnx)。

## 运行已有开发角色

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
../tmp/pose-runner-env/Scripts/python.exe -m autospine_workbench.runners.pose --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --model ../tmp/pose-models/dwpose/dw-ll_ucoco_384.onnx --state-root workspace --output ../tmp/r2b/crino-pose-v4.json
python -m autospine_workbench.benchmark build-r2a --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --pose-observations ../tmp/r2b/crino-pose-v4.json --html ../tmp/r2b/crino-skeleton-v4.html --pose-comparison-html ../tmp/r2b/crino-comparison-v4.html --output ../tmp/r2b/crino-run-v4.json
```

角色名称可以换为 `alice.psd`、`lingxian.psd`。入口自动解析 Benchmark 的真实 character ID
和源图 SHA；不要把 PSD 文件名当成内部 project ID。已有同内容输出可复用，内容改变应使用新输出名。
专业入口也接受配对 `--image/--project`，不能与 Benchmark 选择参数混用。

镜像/视角缺省 `unknown`。仅在有依据时显式传入 `--mirror-state` 和 `--view`；
这些是调用者声明，不是模型检测或人工决定。模型不提供可靠遮挡标签，全部 visibility 保持 unknown。
所以现有 R2-A 的镜像/可见性门槛会阻塞骨架，返回退出码2和零骨骼；仍会生成原始观测对照页。

## 分数与坐标

保留原始133点以及完整 SimCC X/Y 张量，前17点按 COCO17顺序送入现有 Adapter。
不插入 neck、不进行 OpenPose重排。透明像素固定白底，网络输入为BGR、线性仿射黑边，
全画布bbox加1.25 padding，288×384输入；记录正逆仿射并还原到PSD合成图画布。

SimCC 分数是双轴峰值较小者，可能超过1。本次 Alice 左膝实际出现1.02843。
原值不裁剪；进入既有 `[0,1]` 合同前采用显式 `positive-simcc-s-over-one-plus-s-v1`
单调编码 `s/(1+s)`。它不是概率校准，不应沿用旧0.5阈值。原始分数可从 raw 工件读取。
非正分数或前17点越界则拒绝适配，不为其生成替代坐标；原始推理工件继续保留。

原始数值算法参考 [固定官方实现](https://raw.githubusercontent.com/IDEA-Research/DWPose/3dca5db79d9f9ffdd378753ddf6ec66535aace88/ControlNet-v1-1-nightly/annotator/dwpose/onnxpose.py)。
保留 [Apache-2.0 许可证及归属](third-party/dwpose-LICENSE.txt)，模型不随仓库分发。

## 回读与验收

`read_dwpose_raw(path, request)` 在12MiB预算内验证源图、内容地址、固定profile、
完整张量形状与哈希，并重新解码133点。此操作验证保存结果的一致性，不冒充再次推理。
另外的 opt-in 集成测试实际执行两次模型并比较内容地址。

本次51项相关测试通过，真实 ONNX opt-in 1项通过；未运行全量回归或官方 Spine Runtime。
三个真实raw另经JSON Schema与语义reader校验。数值与地址见
[三角色清单](benchmark/r2b-dwpose-2026-09.json)。Chrome已实际渲染琪露诺对照页：
肉眼可见部分手臂点落在冰翼附近，不能把结构可读称为准确定位。

下一步先在已有[独立关节标注页](how-to-benchmark-joints.md)完成三个开发角色GT，
保持GT录入页不叠加模型建议以减少锚定偏差；再做误差对照、镜像/可见性策略及分数校准。
RTMPose/HumanArt的相同输入横向比较仍待接入，本次仅完成DWPose真实观测链。
