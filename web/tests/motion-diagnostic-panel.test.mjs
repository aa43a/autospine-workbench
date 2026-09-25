import test from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticPanel} from '../modules/motion-diagnostic-panel.js';

class Element {
  constructor(tag){this.tag=tag;this.children=[];this.attributes={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this.attributes[name]=value;}
}
globalThis.document={createElement:tag=>new Element(tag)};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};

test('collapse during loading and after completion retains editor, without duplicate requests',async()=>{
  const parent=new Element('main'), wait=deferred();let calls=0,renders=0;
  diagnosticPanel(parent,{label:'定位',load:()=>{calls++;return wait.promise;},render:panel=>{
    renders++;panel.append(new Element('textarea'));
  }});
  const [button,panel]=parent.children;
  const request=button.onclick();
  assert.match(panel.children[0].textContent,/已等待/);
  assert.equal(panel.attributes['aria-busy'],'true');
  button.onclick();assert.equal(panel.hidden,true);
  button.onclick();assert.equal(panel.hidden,false);
  button.onclick();wait.resolve({});await request;
  assert.equal(panel.hidden,true);
  button.onclick();const editor=panel.children[0];editor.value='尚未保存的修正';
  button.onclick();button.onclick();
  assert.equal(panel.children[0],editor);assert.equal(editor.value,'尚未保存的修正');
  assert.equal(calls,1);assert.equal(renders,1);
  assert.equal(panel.attributes['aria-busy'],'false');
  assert.equal(button.attributes['aria-expanded'],'true');
});

test('failed request is retryable and does not render an invalid report',async()=>{
  const parent=new Element('main');let calls=0,renders=0;
  diagnosticPanel(parent,{label:'定位',load:async()=>{if(++calls===1)throw Error('候选版本已变化');return {};},
    render:()=>{renders++;}});
  const [button,panel]=parent.children;
  await button.onclick();
  assert.equal(renders,0);assert.match(panel.children[0].textContent,/候选版本已变化/);
  assert.match(button.textContent,/重试/);assert.equal(panel.attributes['aria-busy'],'false');
  await button.onclick();assert.equal(calls,2);assert.equal(renders,1);
});

test('separate candidate panels never share requests or editor state',async()=>{
  const parent=new Element('main');let calls=0;
  for(const id of ['a','b'])diagnosticPanel(parent,{label:id,load:async()=>{calls++;return id;},
    render:(panel,value)=>panel.append(value)});
  await parent.children[0].onclick();await parent.children[2].onclick();
  assert.equal(calls,2);assert.deepEqual(parent.children[1].children,['a']);
  assert.deepEqual(parent.children[3].children,['b']);
});
