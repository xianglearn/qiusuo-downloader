/* =============================================================================
 * 求索下载 · 前端控制器（UI 逻辑层）
 * -----------------------------------------------------------------------------
 * 职责边界：
 *   - 只负责 DOM 渲染与交互绑定；所有数据取自 DataLayer 的 JSON 快照 / 事件；
 *   - 渲染模板与原始 UI（ui/index.html 内联演示脚本）逐字符一致，视觉 1:1；
 *   - 不直接持有业务状态，不感知业务实现细节。
 * =========================================================================== */
(function () {
  'use strict';

  var D = window.DataLayer;
  var $ = function (id) { return document.getElementById(id); };

  var statusMap = {
    downloading: { label: '下载中', cls: 'downloading' },
    done: { label: '已完成', cls: 'done' },
    waiting: { label: '等待中', cls: 'waiting' },
    error: { label: '失败', cls: 'error' },
    paused: { label: '已暂停', cls: 'paused' }
  };

  var activeFilter = 'all';

  /* ---------------------------------------------------------------------------
   * 渲染：任务表（模板与原始 UI 一致）
   * ------------------------------------------------------------------------- */
  function renderTasks(filter) {
    filter = filter || 'all';
    var body = $('taskBody');
    var snap = D.snapshot();
    var filtered = filter === 'all'
      ? snap.tasks
      : snap.tasks.filter(function (t) { return t.status === filter; });

    if (filtered.length === 0) {
      body.innerHTML = '<div class="empty-state"><div class="empty-ic"><svg viewBox="0 0 256 256" fill="currentColor"><path d="M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40ZM40,56H216V88H40Zm0,144V104H216v96Z"/></svg></div><b>暂无' + (filter === 'all' ? '' : (statusMap[filter] || {}).label || '') + '任务</b><p>在左侧粘贴钉钉链接，点击「解析到任务列表」即可开始下载</p></div>';
      return;
    }

    body.innerHTML = '<table class="task-table"><thead><tr><th class="col-check"></th><th>文件名</th><th class="col-size">大小</th><th class="col-progress">进度</th><th class="col-speed">速度</th><th class="col-status">状态</th><th class="col-ops"></th></tr></thead><tbody>' +
      filtered.map(function (t) {
        var st = statusMap[t.status];
        var barCls = t.status === 'done' ? 'done'
          : t.status === 'error' ? 'error'
          : t.status === 'paused' ? 'paused' : '';
        return '<tr data-id="' + t.id + '"><td class="col-check"><span class="checkbox on"><svg viewBox="0 0 256 256" fill="currentColor"><path d="M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z"/></svg></span></td><td><div class="task-name"><div class="file-ic video"><svg viewBox="0 0 256 256" fill="currentColor"><path d="M251.77,73a8,8,0,0,0-8.21.39L208,97.05V72a16,16,0,0,0-16-16H32A16,16,0,0,0,16,72V184a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V159l35.56,23.71A8,8,0,0,0,248,184a8,8,0,0,0,8-8V80A8,8,0,0,0,251.77,73ZM192,184H32V72H192V184Zm48-22.95-32-21.33V116.28L240,95Z"/></svg></div><div class="meta"><span class="title">' + t.name + '</span><span class="src">' + t.src + '</span></div></div></td><td class="col-size num">' + t.size + '</td><td class="col-progress"><div class="progress"><div class="progress-bar ' + barCls + '"><i style="width:' + t.progress + '%"></i></div><span class="pct num">' + t.progress + '%</span></div></td><td class="col-speed num">' + (t.speed || '—') + '</td><td class="col-status"><span class="tag ' + st.cls + '">' + st.label + '</span></td><td class="col-ops"><div class="row-ops"><button class="op-open" title="打开文件"><svg viewBox="0 0 256 256" fill="currentColor"><path d="M216,72H131.31L104,44.69A15.86,15.86,0,0,0,92.69,40H40A16,16,0,0,0,24,56V200.62A15.4,15.4,0,0,0,39.38,216H216.89A15.13,15.13,0,0,0,232,200.89V88A16,16,0,0,0,216,72ZM40,56H92.69l16,16H40ZM216,200H40V88H216Z"/></svg></button><button class="op-del" title="删除"><svg viewBox="0 0 256 256" fill="currentColor"><path d="M216,48H176V40a24,24,0,0,0-24-24H104A24,24,0,0,0,80,40v8H40a8,8,0,0,0,0,16h8V208a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V64h8a8,8,0,0,0,0-16ZM96,40a8,8,0,0,1,8-8h48a8,8,0,0,1,8,8v8H96Zm96,168H64V64H192ZM112,104v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Zm48,0v64a8,8,0,0,1-16,0V104a8,8,0,0,1,16,0Z"/></svg></button></div></td></tr>';
      }).join('') + '</tbody></table>';

    // 行内操作（打开 / 删除）
    body.querySelectorAll('.op-open').forEach(function (btn) {
      btn.onclick = function () {
        var id = Number(btn.closest('tr').dataset.id);
        var t = D.snapshot().tasks.find(function (x) { return x.id === id; });
        showToast('已打开文件：' + (t ? t.name : ''));
      };
    });
    body.querySelectorAll('.op-del').forEach(function (btn) {
      btn.onclick = function () {
        var id = Number(btn.closest('tr').dataset.id);
        D.removeTasks([id]);
        showToast('已删除任务');
      };
    });
  }

  /* ---------------------------------------------------------------------------
   * 渲染：总进度 / 统计
   * ------------------------------------------------------------------------- */
  function updateOverall() {
    var stats = D.snapshot().stats;
    $('doneCount').textContent = stats.done;
    $('totalCount').textContent = stats.total;
    $('taskTotal').textContent = stats.total;
    $('overallTrack').style.width = stats.avg + '%';
    $('overallSpeed').textContent = stats.speed;
  }

  /* ---------------------------------------------------------------------------
   * 渲染：日志区
   * ------------------------------------------------------------------------- */
  function renderLogs() {
    var area = $('logArea');
    var logs = D.snapshot().logs;
    area.innerHTML = logs.map(function (l) {
      // 与原始 UI 一致：无时间戳的行（如诗句）不渲染 time span，
      // 避免 flex gap 造成 8px 水平偏移
      var timeHtml = l.time ? '<span class="time">' + l.time + '</span>' : '';
      return '<div class="log-line">' + timeHtml + '<span class="msg ' + l.type + '">' + l.msg + '</span></div>';
    }).join('');
    area.scrollTop = area.scrollHeight;
  }

  /* ---------------------------------------------------------------------------
   * Toast
   * ------------------------------------------------------------------------- */
  var toastTimer = null;
  function showToast(msg) {
    var t = $('toast');
    $('toastMsg').textContent = msg;
    t.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('on'); }, 2000);
  }

  /* ---------------------------------------------------------------------------
   * 设置弹窗
   * ------------------------------------------------------------------------- */
  function openModal(on) {
    $('scrim').classList.toggle('on', on);
    $('settingsModal').classList.toggle('on', on);
  }

  /* ---------------------------------------------------------------------------
   * 数据层事件订阅
   * ------------------------------------------------------------------------- */
  D.on('state', function () {
    renderTasks(activeFilter);
    updateOverall();
  });
  D.on('log', function () { renderLogs(); });
  D.on('toast', function (msg) { showToast(msg); });
  D.on('done', function () { renderTasks(activeFilter); updateOverall(); });

  /* ---------------------------------------------------------------------------
   * 初始化：首屏渲染（与锁定 UI 的初始截图一致）
   * ------------------------------------------------------------------------- */
  renderLogs();
  renderTasks('all');
  updateOverall();

  /* ---------------------------------------------------------------------------
   * 交互绑定（按钮 / 分段 / 复选框 / 主题 / 弹窗 / 开关）
   * ------------------------------------------------------------------------- */
  document.querySelectorAll('#filterSeg button').forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll('#filterSeg button').forEach(function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      activeFilter = b.dataset.filter;
      renderTasks(activeFilter);
    };
  });

  $('selectAll').onclick = function () {
    var c = $('allCheck');
    c.classList.toggle('on');
    showToast(c.classList.contains('on') ? '已全选所有任务' : '已取消全选');
  };

  $('startBtn').onclick = function () {
    var r = D.startAll();
    if (r.already) { showToast('任务已在下载中'); return; }
    showToast('已开始下载');
  };

  $('stopBtn').onclick = function () {
    var r = D.stopAll();
    if (r.already) { showToast('当前没有进行中的下载'); return; }
    showToast('已暂停下载');
  };

  $('parseBtn').onclick = function () {
    var ta = document.querySelector('.import-textarea');
    var r = D.parseLinks(ta.value);
    if (r.empty) { showToast('请先粘贴下载链接'); return; }
    showToast('已解析到任务列表');
  };

  $('openDirBtn').onclick = function () { showToast('已打开保存目录'); };
  $('reloginBtn').onclick = function () { D.relogin(); showToast('正在打开登录页面'); };
  $('updateBtn').onclick = function () { D.updateCheck(); showToast('当前已是最新版本'); };

  $('importText').onclick = function () {
    document.querySelector('.import-textarea').value = 'https://dingtalk.com/live/xxxxxx\nhttps://dingtalk.com/group/playback/yyyyyy';
    showToast('已导入文本链接');
  };

  $('importQr').onclick = function () { showToast('请选择二维码图片'); };

  $('clearInput').onclick = function () {
    document.querySelector('.import-textarea').value = '';
    showToast('已清空输入');
  };

  $('batchCheckWrap').addEventListener('click', function (e) {
    e.preventDefault();
    $('batchCheck').classList.toggle('on');
  });

  $('smartGrab').onclick = function () { D.smartGrab(); };

  $('themeBtn').onclick = function () {
    var cur = document.documentElement.getAttribute('data-theme') || 'dark';
    var next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    showToast(next === 'light' ? '已切换到浅色主题' : '已切换到深色主题');
  };

  $('settingsBtn').onclick = function () { openModal(true); };
  $('scrim').onclick = function () { openModal(false); };
  document.querySelectorAll('[data-close]').forEach(function (b) {
    b.onclick = function () { openModal(false); };
  });
  document.querySelectorAll('.switch').forEach(function (s) {
    s.onclick = function () { s.classList.toggle('on'); };
  });

  // 设置弹窗：保存时写回数据层
  document.querySelectorAll('#settingsModal [data-close]').forEach(function (b) {
    b.onclick = function () {
      if (b.textContent.indexOf('保存') >= 0) {
        var inputs = document.querySelectorAll('#settingsModal input');
        D.setConfig({
          saveDir: inputs[0].value,
          threads: Number(inputs[1].value) || 1,
          concurrency: Number(inputs[2].value) || 1
        });
        // 同步配置栏数值
        var cfg = D.getConfig();
        var nums = document.querySelectorAll('.config-bar .num-input');
        if (nums.length >= 2) {
          nums[0].value = cfg.threads;
          nums[1].value = cfg.concurrency;
        }
        showToast('设置已保存');
      }
      openModal(false);
    };
  });

  // 配置栏：线程 / 并发输入写回数据层
  (function () {
    var nums = document.querySelectorAll('.config-bar .num-input');
    if (nums.length >= 2) {
      nums[0].addEventListener('change', function () {
        D.setConfig({ threads: Number(nums[0].value) || 1 });
      });
      nums[1].addEventListener('change', function () {
        D.setConfig({ concurrency: Number(nums[1].value) || 1 });
      });
    }
  })();

  // 浏览按钮（前端演示：无系统对话框时给出提示；接入真实后端后可替换为文件夹选择）
  document.querySelectorAll('.btn-browse').forEach(function (b) {
    b.onclick = function () { showToast('请选择保存目录'); };
  });

  // 流体布局：内容直接铺满窗口并随尺寸重排（替代整屏等比缩放）
  // 原因：等比缩放只有长宽同比例增长时才能填满窗口；只拉宽/只拉高会产生
  // 留白，造成“边框拉大、内容框分开”。改为流体后，内部 grid/flex 按可用
  // 空间重排，始终铺满窗口边框。
  (function () {
    var win = document.querySelector('.window');
    var wrap = document.querySelector('.scale-wrap');
    if (!win || !wrap) return;
    wrap.style.width = '100%';
    wrap.style.height = '100%';
    wrap.style.left = '0';
    wrap.style.top = '0';
    wrap.style.transform = 'none';
  })();

  /* ---------------------------------------------------------------------------
   * 客户端式窗口缩放（基础交互）：四边 + 四角 均可拖动调整
   * ---------------------------------------------------------------------------
   * 根因：原实现仅用 CSS `resize:both`，只提供右下角角拖，上下左右无法调整；
   *       现改为自定义 8 向缩放（n/s/e/w/ne/nw/se/sw），拖哪条边窗口就朝哪
   *       个方向变大变小；内容为流体布局，随窗口尺寸自动重排铺满。
   * ------------------------------------------------------------------------- */
  (function () {
    var win = document.querySelector('.window');
    if (!win || !window.PointerEvent) return;

    var MIN_W = 480, MIN_H = 320;

    // 注：不覆盖 resize:both，保留原生角拖字形以维持视觉 1:1；
    // 自定义 8 向手柄（z-index 更高）负责真正的四边四角拖动。

    // 注入手柄样式（仅出现在交付入口；静止时透明不可见，不改变视觉）
    var st = document.createElement('style');
    st.textContent = [
      '.q-rh{position:absolute;z-index:60;touch-action:none;-webkit-user-select:none;user-select:none;background:transparent;border-radius:2px;}',
      '.q-rh-n{top:0;left:12px;right:12px;height:6px;cursor:ns-resize;}',
      '.q-rh-s{bottom:0;left:12px;right:12px;height:6px;cursor:ns-resize;}',
      '.q-rh-e{right:0;top:12px;bottom:12px;width:6px;cursor:ew-resize;}',
      '.q-rh-w{left:0;top:12px;bottom:12px;width:6px;cursor:ew-resize;}',
      '.q-rh-ne{top:0;right:0;width:16px;height:16px;cursor:nesw-resize;}',
      '.q-rh-nw{top:0;left:0;width:16px;height:16px;cursor:nwse-resize;}',
      '.q-rh-se{bottom:0;right:0;width:16px;height:16px;cursor:nwse-resize;}',
      '.q-rh-sw{bottom:0;left:0;width:16px;height:16px;cursor:nesw-resize;}'
    ].join('\n');
    document.head.appendChild(st);

    // 读取 .window 当前的 transform 平移量（拖动时用于补偿居中漂移）
    function getTranslate() {
      var m = window.getComputedStyle(win).transform;
      if (!m || m === 'none') return { x: 0, y: 0 };
      var p = m.replace(/matrix\(|\)/g, '').split(',').map(Number);
      return { x: p[4] || 0, y: p[5] || 0 };
    }

    function onDown(dir, e) {
      e.preventDefault();
      e.stopPropagation();
      var startX = e.clientX, startY = e.clientY;
      var base = { w: win.offsetWidth, h: win.offsetHeight };
      var t0 = getTranslate();
      // 上限：不超出可视区（留 16px 边距）
      var maxW = Math.max(MIN_W, document.documentElement.clientWidth - 32);
      var maxH = Math.max(MIN_H, document.documentElement.clientHeight - 32);
      var dragging = { dir: dir, startX: startX, startY: startY, base: base, t0: t0, maxW: maxW, maxH: maxH };

      function move(ev) {
        if (!dragging) return;
        var dx = ev.clientX - dragging.startX;
        var dy = ev.clientY - dragging.startY;
        var d = dragging.dir;
        var w = dragging.base.w, h = dragging.base.h;
        if (d.indexOf('e') > -1) w = dragging.base.w + dx;
        if (d.indexOf('s') > -1) h = dragging.base.h + dy;
        if (d.indexOf('w') > -1) w = dragging.base.w - dx;
        if (d.indexOf('n') > -1) h = dragging.base.h - dy;
        w = Math.max(MIN_W, Math.min(dragging.maxW, w));
        h = Math.max(MIN_H, Math.min(dragging.maxH, h));

        // flex 居中会让窗口随尺寸变化向两侧对称漂移；
        // 用 transform 补偿漂移，使「拖动的对边」保持不动 → 真桌面缩放手感。
        var sE = d.indexOf('e') > -1 ? 1 : 0;
        var sW = d.indexOf('w') > -1 ? 1 : 0;
        var sS = d.indexOf('s') > -1 ? 1 : 0;
        var sN = d.indexOf('n') > -1 ? 1 : 0;
        var tx = (sE - sW) * (w - dragging.base.w) / 2;
        var ty = (sS - sN) * (h - dragging.base.h) / 2;

        win.style.width = w + 'px';
        win.style.height = h + 'px';
        win.style.transform = 'translate(' + (dragging.t0.x + tx) + 'px,' + (dragging.t0.y + ty) + 'px)';
        // ResizeObserver(fit) 自动把 960x640 内容等比缩放填充
      }
      function up() {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        document.body.style.userSelect = '';
        dragging = null;
      }
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up);
      document.body.style.userSelect = 'none';
    }

    ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'].forEach(function (dir) {
      var h = document.createElement('div');
      h.className = 'q-rh q-rh-' + dir;
      h.setAttribute('data-dir', dir);
      h.addEventListener('pointerdown', function (e) { onDown(dir, e); });
      win.appendChild(h);
    });
  })();
})();
