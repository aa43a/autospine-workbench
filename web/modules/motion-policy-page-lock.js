const MUTABLE_CONTROL = "button, input, select, textarea";

export function createMotionPolicyPageLock(doc) {
  const saved = new Map();
  const publishPanel = doc.getElementById("p9PublishPanel");
  const main = doc.querySelector("main");
  let locked = false;

  return { setLocked, isLocked: () => locked };

  function setLocked(value) {
    const next = value === true;
    if (next === locked) return;
    locked = next;
    if (locked) {
      for (const control of doc.querySelectorAll(MUTABLE_CONTROL)) {
        if (publishPanel?.contains(control)) continue;
        saved.set(control, control.disabled === true);
        control.disabled = true;
      }
      main?.setAttribute("aria-busy", "true");
      main?.setAttribute("data-motion-policy-locked", "true");
      return;
    }
    for (const [control, wasDisabled] of saved) control.disabled = wasDisabled;
    saved.clear();
    main?.removeAttribute("aria-busy");
    main?.removeAttribute("data-motion-policy-locked");
  }
}
