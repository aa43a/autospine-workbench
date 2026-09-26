import assert from 'node:assert/strict';
import {appendSkirtChecks} from '../web/modules/motion-related-skirt.js';
class Node {constructor(tag){this.tag=tag;this.children=[];this.textContent='';}append(...items){this.children.push(...items);}}
global.document={createElement:tag=>new Node(tag)};
const parent=new Node('section');let sought=null;
appendSkirtChecks(parent,{poses:1,rows:[{pair:['leg','skirt'],time:.9,status:'requires_partition_or_more_depth'}]},t=>{sought=t;});
const detail=parent.children[0];assert.match(detail.children[1].textContent,/未覆盖整段/);
const line=detail.children[2];assert.match(line.textContent,/深度仍不确定/);
line.children[0].onclick();assert.equal(sought,.9);
console.log('Passed: labelled hypothesis, unmeasured scope and exact diagnostic time callback');
