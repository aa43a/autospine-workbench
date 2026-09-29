import test from 'node:test';
import assert from 'node:assert/strict';
import {inventoryLines,jointResultSummary,jointBuildTimingText} from '../modules/motion-joint-editor-view.js';
test('successful execution keeps blocked secondary channels and inherited QA failures visible',()=>{
  const summary=jointResultSummary({status:'succeeded',result:{geometry_passed:false,runtime:{status:'unavailable'},
    joint_summary:{face:{status:'disabled'},secondary:{status:'blocked',skipped:[{reason:'camera_inertia_requires_unprojected_body_driver'}]},loop:{status:'needs_changes'}},
    issues:[{reason_code:'motion_visible_depth_needs_changes'}]}});
  assert.ok(summary.lines.includes('脸部：未启用'));assert.ok(summary.issues.includes('发束、裙袖与挂饰无法应用'));
  assert.ok(summary.issues.includes('网格变形检查未通过'));assert.ok(summary.issues.includes('官方 Runtime 尚未验证'));
  assert.ok(summary.issues.includes('身体动作仍有前后遮挡异常'));
});
test('real inventory includes material limitations and individual secondary targets',()=>{
  const rows=inventoryLines({face:{capabilities:{blink:true,mouth:false},limitations:['turn_is_limited_feature_shift_not_side_view_reconstruction']},
    hair:[{slot:'hair-back',state:'unsupported',reason:'existing_hair_deform'}],cloth:[{slot:'skirt',state:'available'}]});
  assert.ok(rows.includes('眨眼：可用'));assert.ok(rows.some(row=>row.includes('保留现有结果')));
  assert.ok(rows.some(row=>row.includes('尚无真实侧脸重建')));
});
test('enabled procedural mouth template is identified without claiming an authored mouth asset',()=>{
  const inventory={face:{capabilities:{mouth:true},mouth_template_available:true,
    limitations:['mouth_is_source_art_parameterization_not_phoneme_or_new_open_mouth_art']}};
  assert.ok(inventoryLines(inventory).some(row=>row.includes('尚无新增')));
  const rows=inventoryLines(inventory,{face:{mouth:{template_enabled:true}}});
  assert.ok(rows.some(row=>row.includes('程序绘制')));assert.equal(rows.some(row=>row.includes('尚无新增')),false);
});
test('a geometry guard reducing requested movement remains visible even when all channels applied',()=>{
  const result=jointResultSummary({result:{joint_summary:{secondary:{status:'applied',regions:[{slot:'hair',requested_config:{strength:1},effective_config:{strength:.25},post_solve_gain:.25}]}}}});
  assert.ok(result.lines.some(line=>line.includes('从 1 降为 0.25（保留 25%）')));
});

test('new effects passing their loop check does not approve a non-looping body source',()=>{
  const result=jointResultSummary({result:{joint_summary:{loop:{requested:true,status:'needs_changes',source_body:{loop_ready:false},added_effects:{passed:true}}}}});
  assert.ok(result.lines.includes('新增表情与次级运动循环：检查通过'));
  assert.ok(result.issues.includes('原身体动作尚未首尾闭合；联合效果不会自动修复身体循环。'));
});

test('non-looping motion does not report intentionally open endpoints as a loop failure',()=>{
  const result=jointResultSummary({result:{joint_summary:{loop:{requested:false,status:'not_requested',source_body:{loop_ready:false},added_effects:{passed:false}}}}});
  assert.deepEqual(result.issues,[]);assert.deepEqual(result.lines,['循环：未要求循环']);
});

test('build durations show the real measured total and slowest stages while running or completed',()=>{
  const timing={status:'running',elapsed_seconds:12.345,stages:[{step:'joint_inventory',seconds:.2},{step:'joint_secondary',seconds:8.1},{step:'joint_geometry',seconds:3.4}]};
  const live=jointBuildTimingText({progress:{build_timing:timing}});assert.match(live,/已用 12\.3 秒/);
  assert.ok(live.indexOf('随动计算')<live.indexOf('几何检查'));
  assert.match(jointBuildTimingText({result:{build_timing:{...timing,status:'completed'}}}),/用时 12\.3 秒/);
  const current=jointBuildTimingText({elapsed_seconds:42.3,progress:{build_timing:{...timing,active_step:'runtime'}}});
  assert.match(current,/已用 42\.3 秒/);assert.match(current,/当前：官方渲染/);
  assert.equal(jointBuildTimingText({}), '');
});
