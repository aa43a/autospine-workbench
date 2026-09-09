"""Store, replay and export the current component mesh experiment."""
from .component_mesh import build, validate
from .component_mesh_review import render
from ...benchmark.mesh_storage import publish_mesh_report, read_mesh_report, export_mesh


def export(state, output, entries, source, draft, plan_sha, transition=False):
    document = build(entries, source.skeleton, draft, source.source_addresses, plan_sha)
    source.assert_current()
    digest = publish_mesh_report(state, 'project-component-partitions', document)
    checked = read_mesh_report(state, 'project-component-partitions', digest)
    validate(checked, entries, source.skeleton, draft, source.source_addresses, plan_sha)
    source.assert_current()
    export_mesh(output / f'{digest}.json', checked)
    (output / 'mesh.html').write_text(render(checked, source.skeleton), encoding='utf-8')
    count = sum(r['mesh'] is not None and bool(r['mesh']['vertices_xy']) for r in checked['records'])
    passed = sum(r['status'] == 'candidate_requires_review' for r in checked['records'])
    print(f"{draft['project_id']}: {count} meshes; {passed} pass numeric gates; seams/runtime not evaluated")
    if transition:
        from .component_transition_export import export as export_transition
        export_transition(state, output, checked, source, entries)
