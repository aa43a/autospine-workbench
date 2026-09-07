# R2-B 独立参考与误差评估

`joint-review` 保存的是未批准草稿。新增 `record-joint-reference` 将明确复核过的独立标注
记录为 Benchmark Reference；`evaluate-pose-benchmark` 比较旧bbox、原始Pose、优化候选。
两者都保持 `authority:none`，不更改生产 RigIR、自动采用策略或既有关节可见性门槛。

## 人工标注入口

### 一次加载自动点，直接拖动修正

新版页面为 `../tmp/r2b-gt/{alice,lingxian,crino}-assisted-v1.html`。
一次显示17个建议点：可用Pose四肢点覆盖旧基线，其余中轴点来自旧基线。
金色表示未复核自动建议，红色是当前选择，蓝色是已修改或确认。
直接在画布点击点并拖动，松开即保留修改；不需要逐点选择下拉框或提交。
支持一次撤销整次拖动、不可观测、清除、批量确认全部有坐标的点，最后点击“保存全部标注”。
下载的 `assisted-joint-draft.json` 可在同来源页面恢复；未复核点也可先保存后继续。

```powershell
python -m autospine_workbench.benchmark joint-review --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character alice.psd --pose-observations ../tmp/r2b/alice-pose-v4.json --html ../tmp/r2b-gt/alice-assisted-v1.html --output ../tmp/r2b-gt/alice-assisted-v1.json
```

CLI恢复时增加 `--draft path/to/assisted-joint-draft.json` 并选新HTML输出名。
模型辅助草稿封存原Pose、基线和候选身份，`reviewed_joint_ids` 初始为空，
`annotation_mode=model_assisted`、`independent_annotation=false` 永久保留。
批量确认只表示本份辅助草稿中的复核状态，不产生生产批准或独立GT。
既有 `record-joint-reference` 会拒绝整个辅助草稿，不能把它直接用于独立精度验收。

本次13项测试通过，包括实际JavaScript的缩放坐标拖动、撤销、拖动取消、批量确认和导出，
以及CLI恢复、身份篡改、源图变化与文件预算检查；Chrome已渲染检查Alice页面。

### 独立 GT 入口

已在工作区生成 `../tmp/r2b-gt/{alice,lingxian,crino}-annotation-v1.html`。
页面没有模型点或bbox建议。选择关节后点击图像，左右以角色自身为准；不能从图像判断的
点填写原因并标记不可观测，不根据模型预测代填。下载草稿可恢复继续标注。
先完成双侧肩/肘/腕/髋/膝/踝12点状态，中央5点可随后补齐。

独立标注是操作者声明，不是系统验证了盲测。若按模型建议修改坐标，不应声明独立GT。
至少一个 observed 点才可记录Reference；部分标注仍保留 unmarked/unobservable 状态。
不要求在被裙子完全遮住的关节上猜坐标来达到覆盖率目标。

## 显式记录参考

在人工完成草稿并核对独立性后，由操作者运行：

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -m autospine_workbench.benchmark record-joint-reference --manifest docs/benchmark/manifest-frozen-v1.json --evidence docs/benchmark/development-audit-2026-09.json --workspace .. --character crino.psd --draft path/to/downloaded-draft.json --reviewer "标注者姓名或代号" --confirm-human-review --confirm-independent-annotation --output ../tmp/r2b-gt/crino-reference-v1.json
```

两个确认旗标缺一即拒绝；请求、草稿和参考分别封存，精确绑定原候选和源图。
操作者无需填写任何SHA。代码测试只生成合成参考，没有替真实角色提交上述确认。
参考修正通过新草稿与新记录产生新地址，旧结果保留，不继承生产权威。

## 评估

```powershell
python -m autospine_workbench.benchmark evaluate-pose-benchmark --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --run ../tmp/r2b/crino-run-v4.json --reference ../tmp/r2b-gt/crino-reference-v1.json --html ../tmp/r2b-gt/crino-evaluated-v1.html --output ../tmp/r2b-gt/crino-evaluated-v1.json
```

省略 `--reference` 可运行缺GT报告；此时 `accuracy_evaluated=false`，所有误差为null。
直接传草稿、其他角色参考或未发布的伪造Reference会拒绝。reader重放来源图像、R2-A链、
Reference的草稿/请求闭包、旧基线和评估，改变源字节或结果数字将无法精确读取。

三种方法分别显示可用点数、与GT可比点数、中位像素误差、核心肩/髋/踝误差。
归一化分母是合成图非零alpha外接高度，含头发/配饰，并非人工复核的人体高度。
方法差值仅用双方共同拥有的observed参考点，计算逐点误差差值的中位数；负数表示更近。
不拿不同覆盖率的两个总体中位数直接宣称改善。不可观测点与优化blocked都不补零。

## 本切片验证与后续

参考合同、数值算法、CLI精确回读及质量检查共18项通过；合成数据覆盖部分标注、共同
点集合、blocked、巨大数值、来源错误与篡改。三角色真实缺GT报告也已生成并重放，
Chrome实际检查评估页。没有重新运行模型、全量Python或官方Spine Runtime。
所有新源码均低于300行，历史认证链未改。

真实三角色各12个四肢参考状态仍全部未标注，本切片没有数值精度结论。
下一步由人工完成独立参考，随后按真实误差决定模型对照、镜像/可见性处理与阈值校准；
不把新增评估能力当作R2-B精度验收完成。
