/**
 * 前端数据层冒烟测试（Node 运行，无需浏览器/DOM）
 * 用法: node tools/smoke_test.js
 * 验证: 初始快照 / 统计 / 事件总线 / 解析 / 删除 / 配置 / 下载引擎启停
 */
'use strict';
const fs = require('fs');
const path = require('path');

global.window = {};
eval(fs.readFileSync(path.join(__dirname, '..', 'frontend', 'data.js'), 'utf8'));
const D = global.window.DataLayer;

let failures = 0;
function check(name, cond, extra) {
  if (cond) { console.log('  ✔ ' + name); }
  else { failures++; console.error('  ✘ ' + name + (extra ? '  ' + extra : '')); }
}

// 1. 初始快照（应与锁定 UI 的演示数据一致）
const s0 = D.snapshot();
check('初始 3 个任务', s0.tasks.length === 3);
check('统计 done=1 total=3 avg=54', s0.stats.done === 1 && s0.stats.total === 3 && s0.stats.avg === 54, JSON.stringify(s0.stats));
check('统计速度 2.4 MB/s', s0.stats.speed === '2.4 MB/s', s0.stats.speed);
check('配置含保存目录', typeof s0.config.saveDir === 'string' && s0.config.saveDir.includes('求索下载'));
check('初始日志 4 行（含诗句）', s0.logs.length === 4 && s0.logs[3].msg.includes('路漫漫'));
check('快照为纯 JSON 可序列化', (function () { try { JSON.parse(JSON.stringify(s0)); return true; } catch (e) { return false; } })());

// 2. 事件总线
let logEvt = 0, stateEvt = 0, toastEvt = 0;
D.on('log', function () { logEvt++; });
D.on('state', function () { stateEvt++; });
D.on('toast', function () { toastEvt++; });

// 3. 解析链接
const r1 = D.parseLinks('');
check('空文本 → empty=true', r1.empty === true && r1.count === 0);
const r2 = D.parseLinks('https://a.com/x\nhttps://b.com/y');
check('解析 2 行 → 新增 2 任务（共 5）', r2.count === 2 && D.snapshot().tasks.length === 5, JSON.stringify(r2));
check('解析产生 log 事件', logEvt > 0);

// 4. 删除任务
const id = D.snapshot().tasks[0].id;
const rm = D.removeTasks([id]);
check('删除 1 个任务（剩 4）', rm.removed === 1 && D.snapshot().tasks.length === 4);
check('删除产生 state 事件', stateEvt > 0);

// 5. 配置
D.setConfig({ threads: 20, concurrency: 3 });
check('配置更新生效', D.getConfig().threads === 20 && D.getConfig().concurrency === 3);

// 6. 下载引擎：启动 → 推进 → 停止
const st = D.startAll();
check('startAll 成功启动', st.already === false && D.snapshot().downloading === true);
setTimeout(function () {
  const snap = D.snapshot();
  const dl = snap.tasks.filter(function (t) { return t.status === 'downloading'; });
  console.log('  [运行 1.2s] downloading 任务数=' + dl.length +
    ' | 事件 log/state/toast=' + logEvt + '/' + stateEvt + '/' + toastEvt);
  check('运行中确有任务在下载', dl.length > 0);

  const stp = D.stopAll();
  const after = D.snapshot();
  check('stopAll → downloading=false', stp.already === false && after.downloading === false);
  check('进行中任务转为 paused', after.tasks.some(function (t) { return t.status === 'paused'; }));

  const s2 = D.startAll();
  check('二次启动（引擎已停）可用', s2.already === false && D.snapshot().downloading === true);
  D.stopAll();

  console.log(failures === 0 ? '\nSMOKE PASS' : '\nSMOKE FAIL: ' + failures);
  process.exit(failures === 0 ? 0 : 1);
}, 1200);
