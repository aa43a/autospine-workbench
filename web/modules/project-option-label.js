// Disambiguate versions without renaming projects or changing their identities.
export function projectOptionLabel(project, projects) {
  const name = project.name || project.id;
  if (projects.filter(p => (p.name || p.id) === name).length < 2) return name;
  const version = project.id.startsWith('imported-')
    ? `导入版本 ${project.id.slice(9, 21)}` : `原项目 ${project.id}`;
  return `${name} · ${version}`;
}
