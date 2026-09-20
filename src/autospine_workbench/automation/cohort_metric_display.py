"""Display measured cohort metrics without turning defaults into human labels."""
from html import escape


def number(value, suffix=''):
    return '未测量' if value is None else escape(f'{value:g}{suffix}')


def render(metrics):
    rate = metrics.get('runtime_failure_rate')
    parts = [f'<p>当前候选 Runtime 失败率：{number(None if rate is None else rate*100, "%")}；'
             '分母为本快照中已测角色，不包含全部历史构建或重试。</p>']
    timing = metrics.get('visual_review_timing')
    if timing:
        parts.append(f'<p>当前候选视觉复核计时：{timing["measured_characters"]}/{timing["total_characters"]} 名角色；'
                     f'已测部分合计 {number(timing["measured_minutes"], " 分钟")}。'
                     '未计时部分不按零计算，不包含标注、修正或历史返工耗时。</p>')
    audit = metrics.get('auto_binding_audit')
    if audit:
        parts.append('<p>自动归属默认沿用，未逐项抽查不阻塞工作流；已记录的异常仍需修改。'
                     f'默认沿用且未单独抽查 {audit.get("default_unreviewed_bindings", audit.get("not_reviewed", "未记录"))} 项。'
                     '默认沿用不等于人工验证正确。</p>')
        if audit.get('carried_exception_layers'):
            parts.append(f'<p>跨重建保留的未修复异常：{audit["carried_exception_layers"]} 层；不重复计入当前人工抽查。</p>')
        rate = audit['sampled_error_rate']
        parts.append(f'<p>可选自动绑定抽查：明确判断 {audit["assessed_bindings"]}/{audit["eligible_bindings"]} 项，'
                     f'需修改 {audit["incorrect"]} 项，无法判断 {audit.get("unobservable", "未记录")} 项；'
                     f'抽查错误率 {number(None if rate is None else rate*100, "%")}。'
                     '这是人工所选样本，不是全部输入的准确率。</p>')
        timing = audit.get('audit_timing')
        history = audit.get('historical_audit')
        if history:
            parts.append(f'<p>历史记录覆盖 {history["measured_projects"]} 个项目；按原自动决定去重，'
                         f'曾明确判断 {history["assessed_decisions"]} 项，曾标记异常 {history["ever_flagged_decisions"]} 项，'
                         f'其中已不属于当前自动决定 {history["flagged_decisions_no_longer_current"]} 项。'
                         '包含后来撤回的异常标记，不作为错误率；决定变更不等于修复验收通过。</p>')
        if timing:
            parts.append(f'<p>当前自动绑定抽查计时：{timing["measured_projects"]}/{timing["total_projects"]} 个项目；'
                         f'已测部分合计 {number(timing["measured_minutes"], " 分钟")}。'
                         '此项不包含关节标注、修改和全部历史返工。</p>')
    work = metrics.get('project_work_timing')
    if work:
        parts.append(f'<p>已记录项目操作耗时：{number(work["recorded_minutes"], " 分钟")}；'
                     f'覆盖 {work["measured_projects"]}/{work["total_projects"]} 个项目。'
                     '仅包含显式计时并保存的导入后操作片段；不与视觉或抽查计时相加，避免重复计算。'
                     '未记录的历史操作无法补算为零。</p>')
    parts.append('<p>人工总耗时：未测量。错误自动采用率：未测量。'
                 '部分会话计时不代表全部人工耗时；这些角色不作为独立 holdout 精度证明。</p>')
    return ''.join(parts)
