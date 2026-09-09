import test from 'node:test';
import assert from 'node:assert/strict';
import {brushHitsTriangle,brushStrokePoints} from './modules/sleeve-brush.js';

test('brush covers triangle interior and edge without requiring vertex inclusion', () => {
  const triangle=[[0,0],[100,0],[0,100]];
  assert.equal(brushHitsTriangle([20,20],2,triangle),true);
  assert.equal(brushHitsTriangle([20,-3],4,triangle),true);
  assert.equal(brushHitsTriangle([20,-3],2,triangle),false);
  assert.equal(brushHitsTriangle([20,20],2,[...triangle].reverse()),true);
});

test('larger radius covers distant triangles and drag interpolates fast movement', () => {
  const triangle=[[48,1],[52,1],[50,3]];
  assert.equal(brushHitsTriangle([0,0],4,triangle),false);
  assert.equal(brushHitsTriangle([0,0],60,triangle),true);
  const samples=brushStrokePoints([0,0],[100,0],4);
  assert.ok(samples.some(p => brushHitsTriangle(p,4,triangle)));
  assert.deepEqual(samples.at(-1),[100,0]);
  assert.deepEqual(brushStrokePoints(null,[2,3],4),[[2,3]]);
});
