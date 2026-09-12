import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultCharacterMotion} from '../modules/workbench-character-motion-choice.js';
const full={choice_id:'a'.repeat(64),available:true,animations:['idle','walk','wave-left']};
test('only a unique current complete set is automatically selected',()=>{
 assert.equal(defaultCharacterMotion([full]),full.choice_id);
 assert.equal(defaultCharacterMotion([{...full,available:false},full]),full.choice_id);
 assert.equal(defaultCharacterMotion([full,{...full,choice_id:'b'.repeat(64)}]),'');
 for(const change of [{available:false},{available:'true'},{animations:['idle','walk']},{animations:null},{choice_id:'bad'}])
  assert.equal(defaultCharacterMotion([{...full,...change}]),'');
 assert.equal(defaultCharacterMotion([]),'');
});
