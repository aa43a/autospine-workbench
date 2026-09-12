import test from 'node:test';
import assert from 'node:assert/strict';
import {createReviewStopwatch} from '../modules/workbench-review-stopwatch.js';
test('explicit clock excludes paused time and does not invent old measurements',()=>{
 let now=0;const document={createElement(){return {children:[],append(...c){this.children.push(...c);},addEventListener(_,f){this.click=f;}};}};
 const timer=createReviewStopwatch(document,()=>now),button=timer.element.children[0];
 timer.load(null);timer.sync(true);now=10000;assert.equal(timer.snapshot(),null);
 button.click();now=25000;button.click();now=45000;assert.equal(timer.snapshot().seconds,15);
 button.click();now=50000;timer.sync(false);now=90000;assert.equal(timer.snapshot().seconds,20);
 timer.load({seconds:90});timer.sync(true);button.click();now=95000;assert.equal(timer.snapshot().seconds,95);
 timer.load(null);assert.equal(timer.snapshot(),null);
});
