// Keep unchanged cards attached so polling preserves review panels and focus.
export function reconcileMotionJobs(container, jobs, build, context = '') {
  const existing = new Map([...container.children]
    .filter(node => node.dataset.jobId)
    .map(node => [node.dataset.jobId, node]));
  const retained = new Set();
  jobs.forEach((job, index) => {
    const signature = JSON.stringify([job, context]);
    let card = existing.get(job.job_id);
    if (!card || card.motionJobSignature !== signature) {
      const replacement = build(job);
      replacement.dataset.jobId = job.job_id;
      replacement.motionJobSignature = signature;
      if (card) card.replaceWith(replacement);
      card = replacement;
    }
    if (container.children[index] !== card) {
      container.insertBefore(card, container.children[index] || null);
    }
    retained.add(card);
  });
  for (const child of [...container.children]) {
    if (!retained.has(child)) child.remove();
  }
}
