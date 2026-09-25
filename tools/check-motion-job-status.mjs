import assert from 'node:assert/strict';
import {jobStatus} from '../web/modules/motion-job-status.js';
const states={pending:'等待解析',succeeded:'解析完成',failed:'失败',interrupted:'服务重启中断'};
const reasons={motion_decode_timeout:'解析超时',motion_import_interrupted:'重新解析'};
function label(kind,status,extra={}){return jobStatus({kind,status,...extra},states,reasons,{generate_motion:'生成模型推理'});}
assert.equal(label('generate','pending').state,'等待生成');
assert.equal(label('generate','succeeded').state,'生成完成');
assert.equal(label('adapt','pending').state,'等待构建');
assert.equal(label('adapt','succeeded').state,'角色候选已生成');
assert.equal(label('import','succeeded').state,'解析完成');
assert.equal(label('generate','running',{cancel_requested:true}).state,'正在停止');
assert.equal(label('generate','running',{step:'generate_motion'}).detail,'生成模型推理');
for(const [kind,word] of [['generate','生成'],['adapt','构建'],['import','解析']]){
  assert.match(label(kind,'failed',{reason_code:'motion_decode_timeout'}).detail,new RegExp(word+'超过处理时限'));
  assert.match(label(kind,'interrupted',{reason_code:'motion_import_interrupted'}).detail,/创建新任务/);
}
assert.match(label('generate','interrupted',{reason_code:'motion_import_interrupted'}).detail,/不是模型断点续算/);
assert.equal(label('generate','failed',{reason_code:'unknown_failure'}).detail,'unknown_failure');
assert.doesNotMatch(label('generate','interrupted').detail,/undefined/);
console.log('Motion operation status regression passed');
