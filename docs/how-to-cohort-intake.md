# 首批十角色准备清单

在扩展整角色验收前，从冻结 Benchmark 和工作台资产目录生成只读清单：

```powershell
$env:PYTHONPATH='src'
python tools/assess-cohort-intake.py --output ../tmp/character-first-ten
```

核验旧审计时增加 `--verify-workspace ..`：读取当前项目来源，核对本地审计文件的
字节身份、审计声明的 PSD 身份和冻结候选 PSD 的实际字节。输出 v2 报告及
`source-checks.json`、`project-documents.json`，不修改旧审计或人工决定。
有证据的旧审计不再要求名称一致；任何来源变化都会保留未核验状态。

打开输出目录中的 `index.html`，按“下一步”核对来源、选择 PSD 版本、恢复或导入项目。
每个现有项目提供工作台链接。工具不导入素材、不提交复核、不运行构建。

只有资产目录提供的 PSD 字节身份与冻结候选一致，才记作来源匹配。
旧审计的同名项目只是核对线索；多版本和多项目不会自动选取。
匹配不证明原 PNG 与 PSD 视觉对应，也不证明关节、完整绑定或 Runtime 通过。

`report.json` 引用同目录 `manifest.json`、`catalog.json` 的 SHA256，便于复查盘点时的输入。
目录是可重新生成的快照，不是认证工件仓库；再次执行会覆盖这份盘点。
冻结的 3/4/3 分组不改写。独立性必须检查开发使用记录，尤其已经参与袖装开发的
八云蓝及新项目流程验证的芙兰，不能仅因原标签为 holdout 就计入独立泛化结论。

完整角色、多动作指标仍由 `assess-character-cohort.py` 的精确候选与官方捕获证据提供。
本清单的未测项目保持未测，不填零，也不并入已验证三角色的成功率。
