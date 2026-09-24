/* =============================================================================
 * 求索下载 · 前端数据层（模拟业务逻辑）
 * -----------------------------------------------------------------------------
 * 职责边界：
 *   - 唯一持有业务状态（任务/配置/日志/下载状态），对外只输出 JSON 快照；
 *   - 不引用、不修改任何 DOM，不依赖任何 UI 结构；
 *   - 通过事件总线向 UI 推送事件（state / log / toast / done），载荷均为纯 JSON；
 *   - 控制器层（app.js）只消费本层快照与事件，业务与界面互不感知。
 *
 * 后续如需接入真实后端（如 yt-dlp / ffmpeg / 钉钉接口），
 * 只需把本文件内部的模拟逻辑替换为 fetch 调用，对外 API 保持不变。
 * =========================================================================== */
(function (global) {
  'use strict';

  /* ---------------------------------------------------------------------------
   * 事件总线（UI 订阅，数据层发布；载荷一律 JSON）
   * ------------------------------------------------------------------------- */
  var listeners = {};

  function on(evt, fn) {
    (listeners[evt] = listeners[evt] || []).push(fn);
  }

  function emit(evt, data) {
    (listeners[evt] || []).forEach(function (fn) { fn(data); });
  }

  /* ---------------------------------------------------------------------------
   * 内存状态（唯一权威数据源）
   * ------------------------------------------------------------------------- */
  var state = {
    app: { name: '求索下载', version: 'v1.0' },
    env: { ready: true, tools: ['GoDingtalk', 'MediaGo', 'FFmpeg'] },
    config: {
      saveDir: 'F:\\资料库\\求索下载\\video',
      threads: 10,
      concurrency: 2,
      notify: true,
      autoupdate: true
    },
    tasks: [
      { id: 1, name: '产品周会回放_20260920', src: '群回放 · 产品研发群',
        size: '248 MB', progress: 100, status: 'done', speed: '' },
      { id: 2, name: '季度复盘会议录像', src: '群回放 · 管理层季度会',
        size: '1.2 GB', progress: 62, status: 'downloading', speed: '2.4 MB/s' },
      { id: 3, name: '新人培训直播回放', src: '直播短链 · HR培训',
        size: '856 MB', progress: 0, status: 'waiting', speed: '' }
    ],
    logs: [
      { time: '[14:53:41]', msg: '当前已是最新版本 v1.0', type: 'ok' },
      { time: '[14:53:38]', msg: '环境检测完成：GoDingtalk ✓ MediaGo ✓ FFmpeg ✓', type: '' },
      { time: '[14:53:35]', msg: '求索下载已加载', type: '' },
      { time: '', msg: '路漫漫其修远兮，吾将上下而求索。', type: 'poem' }
    ],
    downloading: false
  };

  var engineTimer = null;   // 模拟下载引擎的定时器
  var SPEED_BAND = [1.8, 2.6, 3.2, 4.1];

  /* ---------------------------------------------------------------------------
   * 内部工具
   * ------------------------------------------------------------------------- */
  function nowClock() {
    var d = new Date();
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return '[' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + ']';
  }

  function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

  function nextId() {
    var max = 0;
    state.tasks.forEach(function (t) { if (t.id > max) max = t.id; });
    return max + 1;
  }

  function addLog(msg, type) {
    type = type || '';
    var entry = { time: nowClock(), msg: msg, type: type };
    state.logs.push(entry);
    if (state.logs.length > 200) state.logs = state.logs.slice(-200);
    emit('log', clone(entry));
    return clone(entry);
  }

  /* ---------------------------------------------------------------------------
   * 统计（每次由明细现算，不缓存）
   * ------------------------------------------------------------------------- */
  function computeStats() {
    var total = state.tasks.length;
    var done = 0, sum = 0, speed = '';
    state.tasks.forEach(function (t) {
      if (t.status === 'done') done++;
      sum += t.progress;
      if (t.status === 'downloading' && t.speed && !speed) speed = t.speed;
    });
    return {
      done: done,
      total: total,
      avg: total ? Math.round(sum / total) : 0,
      speed: speed || '—'
    };
  }

  /* ---------------------------------------------------------------------------
   * 对外 JSON 快照（UI 唯一取数入口）
   * ------------------------------------------------------------------------- */
  function snapshot() {
    return {
      app: clone(state.app),
      env: clone(state.env),
      config: clone(state.config),
      tasks: clone(state.tasks),
      stats: computeStats(),
      logs: clone(state.logs),
      downloading: state.downloading
    };
  }

  /* ---------------------------------------------------------------------------
   * 任务操作
   * ------------------------------------------------------------------------- */
  function addTask(name, src, size, progress, status, speed) {
    var task = {
      id: nextId(),
      name: name,
      src: src || '',
      size: size || '—',
      progress: (progress == null ? 0 : progress),
      status: status || 'waiting',
      speed: speed || ''
    };
    state.tasks.push(task);
    emit('state', snapshot());
    return clone(task);
  }

  function removeTasks(ids) {
    var before = state.tasks.length;
    state.tasks = state.tasks.filter(function (t) { return ids.indexOf(t.id) < 0; });
    emit('state', snapshot());
    return { removed: before - state.tasks.length };
  }

  function updateTask(id, fields) {
    state.tasks.forEach(function (t) {
      if (t.id === id) {
        Object.keys(fields).forEach(function (k) { t[k] = fields[k]; });
      }
    });
  }

  /* ---------------------------------------------------------------------------
   * 解析链接 → 任务列表
   * ------------------------------------------------------------------------- */
  function parseLinks(text) {
    var lines = String(text || '').split('\n').map(function (s) { return s.trim(); })
      .filter(Boolean);
    if (!lines.length) return { count: 0, empty: true };
    var count = 0;
    lines.forEach(function (link, i) {
      addTask('下载任务 ' + (i + 1), '链接解析 · ' + link.replace(/^https?:\/\//, '').slice(0, 24), '', 0, 'waiting');
      count++;
    });
    addLog('解析链接完成，已添加 ' + count + ' 个任务', 'ok');
    return { count: count, empty: false };
  }

  /* ---------------------------------------------------------------------------
   * 模拟下载引擎（业务演示：开始 / 停止）
   * ------------------------------------------------------------------------- */
  function promoteTasks(concurrency) {
    var running = state.tasks.filter(function (t) { return t.status === 'downloading'; }).length;
    state.tasks.forEach(function (t) {
      if (running >= concurrency) return;
      if (t.status === 'waiting') { t.status = 'downloading'; running++; }
    });
  }

  function engineTick() {
    var finishedAll = true;
    state.tasks.forEach(function (t) {
      if (t.status !== 'downloading') return;
      finishedAll = false;
      var step = 1.2 + Math.random() * 2.3;
      var next = Math.min(100, t.progress + step);
      t.progress = Math.round(next * 10) / 10;
      t.speed = SPEED_BAND[Math.floor(Math.random() * SPEED_BAND.length)].toFixed(1) + ' MB/s';
      if (next >= 100) {
        t.progress = 100;
        t.status = 'done';
        t.speed = '';
        addLog(t.name + ' 下载完成', 'ok');
        emit('task_done', { name: t.name });
      }
    });
    // 补充等待中的任务
    promoteTasks(Math.max(1, state.config.concurrency | 0));
    state.tasks.forEach(function (t) {
      if (t.status === 'waiting' || t.status === 'downloading') finishedAll = false;
    });
    emit('state', snapshot());
    if (finishedAll) engineFinish();
  }

  function engineFinish() {
    if (engineTimer) { clearInterval(engineTimer); engineTimer = null; }
    state.downloading = false;
    addLog('全部下载任务已完成', 'ok');
    emit('done', {});
    if (state.config.notify) emit('toast', '全部下载任务已完成');
  }

  function startAll() {
    if (state.downloading) return { already: true };
    state.downloading = true;
    var dl = state.tasks.find ? state.tasks.find(function (t) { return t.status === 'downloading'; }) : null;
    promoteTasks(Math.max(1, state.config.concurrency | 0));
    addLog(dl ? '开始下载任务：' + dl.name : '已开始下载', 'ok');
    emit('state', snapshot());
    engineTimer = setInterval(engineTick, 300);
    return { already: false };
  }

  function stopAll() {
    if (!state.downloading) return { already: true };
    if (engineTimer) { clearInterval(engineTimer); engineTimer = null; }
    state.tasks.forEach(function (t) {
      if (t.status === 'downloading') { t.status = 'paused'; t.speed = ''; }
    });
    state.downloading = false;
    addLog('下载已暂停', 'warn');
    emit('state', snapshot());
    return { already: false };
  }

  /* ---------------------------------------------------------------------------
   * 一键批量采集（模拟扫描已打开的群回放页）
   * ------------------------------------------------------------------------- */
  function smartGrab() {
    addLog('正在扫描已打开的钉钉群回放页面…', '');
    setTimeout(function () {
      addTask('群回放录制 1', '群名 · 自动采集', '', 0, 'waiting');
      addTask('群回放录制 2', '群名 · 自动采集', '', 0, 'waiting');
      addLog('发现 2 个已加载的群回放，已按群名保存', 'ok');
      emit('toast', '已获取 2 个群回放链接');
    }, 800);
    return { scanning: true };
  }

  /* ---------------------------------------------------------------------------
   * 其他业务动作（登录 / 更新检查）
   * ------------------------------------------------------------------------- */
  function relogin() {
    addLog('正在跳转钉钉授权登录…', '');
    return { ok: true };
  }

  function updateCheck() {
    addLog('当前已是最新版本 ' + state.app.version, 'ok');
    return { ok: true, version: state.app.version };
  }

  /* ---------------------------------------------------------------------------
   * 配置
   * ------------------------------------------------------------------------- */
  function getConfig() { return clone(state.config); }

  function setConfig(patch) {
    Object.keys(patch).forEach(function (k) {
      if (k in state.config) state.config[k] = patch[k];
    });
    emit('state', snapshot());
    return clone(state.config);
  }

  /* ---------------------------------------------------------------------------
   * 导出
   * ------------------------------------------------------------------------- */
  global.DataLayer = {
    on: on,
    snapshot: snapshot,
    getConfig: getConfig,
    setConfig: setConfig,
    addTask: addTask,
    removeTasks: removeTasks,
    parseLinks: parseLinks,
    startAll: startAll,
    stopAll: stopAll,
    smartGrab: smartGrab,
    relogin: relogin,
    updateCheck: updateCheck
  };
})(window);
