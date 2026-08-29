export function handleCandidateKeyboard(event, container, chooseAction) {
  if (isTyping(event.target)) return;
  const cards = [...container.querySelectorAll("[data-candidate-id]")].filter((card) => !card.hidden);
  if (!cards.length) return;
  const current = event.target.closest?.("[data-candidate-id]");
  const index = Math.max(0, cards.indexOf(current));
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const direction = event.key === "ArrowDown" ? 1 : -1;
    cards[(index + direction + cards.length) % cards.length].focus();
    return;
  }
  const action = { a: "accept", x: "adjust", r: "reject", u: "unobservable" }[event.key.toLowerCase()];
  if (!action || !current) return;
  const radio = current.querySelector(`[data-action="${action}"]`);
  if (!radio || radio.disabled) return;
  event.preventDefault();
  radio.checked = true;
  chooseAction(current.dataset.candidateId, action, current);
}

function isTyping(target) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
}
