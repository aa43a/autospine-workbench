"""Static calibration diagnostics, separate from annotation authority."""

from html import escape

_REASONS = {
    "underconstrained_validation": "只有两对点，无法用冗余点验证拟合；建议至少增加第三对。",
    "anchor_span_insufficient": "锚点沿某个坐标轴分布过窄，无法稳定估算缩放。",
    "anchor_residual_high": "最大残差超过当前诊断阈值，未应用拟合变换。",
    "anchor_transform_singular": "对应点无法产生可逆的缩放变换。",
    "anchor_numeric_failure": "拟合出现无效数值，未应用变换。",
}


def render_calibration_summary(report):
    if report is None:
        return ""
    if report.get("authority") != "none":
        raise ValueError("benchmark_mapping_calibration_authority_invalid")
    blocked = report["status"] == "blocked"
    title = "锚点校准被阻塞：继续显示原候选" if blocked else "锚点校准结果：仍需复核"
    reasons = "".join("<li>" + escape(_REASONS.get(code, code)) + "</li>" for code in report["reason_codes"])
    metrics = ""
    if report["rmse_px"] is not None:
        metrics = (f'<p>均方根误差 {report["rmse_px"]:.3f} px；最大残差 '
                   f'{report["max_residual_px"]:.3f} px（PSD 高度的 '
                   f'{report["max_residual_relative_height"] * 100:.3f}%）。</p>')
    rows = "".join(f'<tr><td>{escape(row["id"])}</td><td>{row["delta"][0]:.3f}</td>'
                   f'<td>{row["delta"][1]:.3f}</td><td>{row["distance_px"]:.3f}</td></tr>'
                   for row in report["residuals"])
    table = ('<table><caption>每对锚点的拟合残差（像素）</caption><thead><tr><th>锚点</th>'
             '<th>ΔX</th><th>ΔY</th><th>距离</th></tr></thead><tbody>' + rows + '</tbody></table>') if rows else ""
    return ('<section class="notice" aria-label="锚点校准诊断"><h2>' + title + '</h2>' + metrics
            + '<ul>' + reasons + '</ul>' + table
            + '<p>误差仅对应生成本页时的锚点拟合（阻塞时未应用），不随下方手动变换更新。'
              '调整变换后须重新校准，不能沿用本报告作为当前变换的验证。</p>'
            + '<p>当前诊断使用 PSD 高度 3% 的最大残差阈值；它不是标注准确性或自动采用认证。'
              '模型只表达逐轴缩放和平移，不表达旋转、剪切或角色形变。</p></section>')
