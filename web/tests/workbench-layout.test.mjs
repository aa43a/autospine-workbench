import test from 'node:test';
import assert from 'node:assert/strict';
import { workbenchLayout } from '../modules/workbench-layout.js';

class Element extends EventTarget {
  constructor(tag) { super(); this.tagName = tag; this.children = []; this.attrs = {}; }
  append(...nodes) { for (const n of nodes) { if (n.parentNode) n.parentNode.children = n.parentNode.children.filter(x => x !== n); n.parentNode = this; this.children.push(n); } }
  before(node) { const parent = this.parentNode; node.parentNode = parent; parent.children.splice(parent.children.indexOf(this), 0, node); }
  setAttribute(k, v) { this.attrs[k] = v; }
  closest(tag) { return this.tagName === tag ? this : this.parentNode?.closest(tag); }
}
function setup() {
  const main = new Element('main'), canvas = new Element('section'), legacy = new Element('nav'); main.append(canvas);
  const ids = { workspace: main, 'main-content': canvas, workflowNav: legacy };
  const doc = { getElementById: id => ids[id] || null, createElement: tag => new Element(tag) };
  const layout = workbenchLayout(doc);
  const all = () => { const walk = n => [n, ...n.children.flatMap(walk)]; return walk(main); };
  return { doc, layout, canvas, main, legacy, all };
}
test('workspace switching preserves existing canvas, unsaved form node and listeners', () => {
  const h = setup(), input = new Element('input'); input.value = 'unsaved'; let clicks = 0;
  input.addEventListener('click', () => clicks++); h.layout.mount('bindings', input);
  h.layout.showBinding('bindings'); h.layout.show('animation'); h.layout.showBinding('bindings');
  assert.equal(input.value, 'unsaved'); input.dispatchEvent(new Event('click')); assert.equal(clicks, 1);
  assert.equal(h.all().filter(n => n === input).length, 1);
  assert.equal(h.all().filter(n => n === h.canvas).length, 1);
  assert.equal(h.all().find(n => n.id === 'workbench-binding').hidden, false);
  assert.equal(h.all().find(n => n.id === 'workbench-animation').hidden, true);
  assert.equal(workbenchLayout(h.doc), h.layout); assert.equal(h.legacy.hidden, true);
});
test('issue sources are separated from properties and only the selected queue is visible', () => {
  const h = setup(), queue = new Element('ul'); h.layout.mountIssues('static', queue);
  const button = h.all().find(n => n.tagName === 'button' && n.textContent === '静态异常');
  button.dispatchEvent(new Event('click')); assert.equal(queue.parentNode.hidden, false);
  h.all().find(n => n.tagName === 'button' && n.textContent === '动画异常').dispatchEvent(new Event('click'));
  assert.equal(queue.parentNode.hidden, true);
});
