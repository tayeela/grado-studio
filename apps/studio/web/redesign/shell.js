/* =============================================================================
   ГРАДО Студия — каркас нового интерфейса (Фаза 1), интерактив.
   Настоящие взаимодействия хромки; движок черчения ещё не подключён
   (холст-заглушка). В Фазе 2 обработчики заменяются вызовами реального ядра.
   ============================================================================= */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* ---- тост ---- */
  let toastT;
  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg; el.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => (el.hidden = true), 1900);
  }

  /* ---- тема ---- */
  $('#btn-theme').addEventListener('click', () => {
    const r = document.documentElement;
    r.dataset.theme = r.dataset.theme === 'dark' ? 'light' : 'dark';
  });

  /* ---- инструменты ---- */
  function selectTool(name) {
    $$('.tool').forEach(t => t.classList.toggle('active', t.dataset.tool === name));
    $('#st-tool').textContent = 'Инструмент: ' + name;
  }
  $$('.tool').forEach(t => t.addEventListener('click', () => selectTool(t.dataset.tool)));
  $$('[data-tool-chip]').forEach(c => c.addEventListener('click', () => {
    selectTool(c.dataset.toolChip); toast('Инструмент: ' + c.dataset.toolChip);
  }));

  /* ---- выделение на холсте (контекстные Свойства) ---- */
  function setSelection(on) {
    $('#prop-card').hidden = !on;
    $('#prop-empty').hidden = on;
    $('#handles').hidden = !on;
  }
  $$('#scene .pick').forEach(p => p.addEventListener('click', e => {
    e.stopPropagation(); setSelection(true);
  }));
  $('#bg-empty').addEventListener('click', () => setSelection(false));

  /* ---- слои ---- */
  $$('#layers .layer').forEach(l => {
    l.addEventListener('click', () => {
      $$('#layers .layer').forEach(x => x.classList.remove('active'));
      l.classList.add('active');
      const nm = l.dataset.layer;
      $('#st-active').innerHTML =
        '<span class="dot" style="background:var(--zone-a);box-shadow:inset 0 0 0 1px var(--zone-a-line)"></span>Черчу в: ' + nm;
    });
    l.querySelector('.eye').addEventListener('click', e => {
      e.stopPropagation();
      const off = l.classList.toggle('hidden-lyr');
      l.querySelector('.eye use').setAttribute('href', off ? '#i-eye-off' : '#i-eye');
    });
  });

  /* ---- закрыть все всплывающие ---- */
  function closeFloaters() {
    $$('.menu, .pop').forEach(el => (el.hidden = true));
    $$('[data-menu],[data-pop]').forEach(b => b.classList.remove('on', 'phon'));
    $$('.phbtn').forEach(b => b.classList.remove('on'));
  }

  /* ---- меню в шапке (Данные/Проект/Выпуск) ---- */
  $$('[data-menu]').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    const m = $('#' + btn.dataset.menu);
    const wasOpen = !m.hidden;
    closeFloaters();
    if (wasOpen) return;
    const r = btn.getBoundingClientRect();
    m.style.left = Math.min(r.left, innerWidth - 250) + 'px';
    m.style.top = r.bottom + 6 + 'px';
    m.style.right = 'auto';
    m.hidden = false;
  }));

  /* ---- поповеры панели (Подложка/Сетка/Источники) ---- */
  $$('.phbtn[data-pop]').forEach(btn => btn.addEventListener('click', e => {
    e.stopPropagation();
    const p = $('#' + btn.dataset.pop);
    const wasOpen = !p.hidden;
    closeFloaters();
    if (wasOpen) return;
    p.hidden = false;
    btn.classList.add('on');
  }));

  /* ---- модалки ---- */
  function openModal(id) { closeFloaters(); closeCmdk(); $('#' + id).hidden = false; }
  function closeModals() { $$('.scrim').forEach(s => (s.hidden = true)); }
  $$('[data-modal]').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation(); openModal(b.dataset.modal);
  }));
  $$('.scrim').forEach(s => s.addEventListener('click', e => {
    if (e.target === s || e.target.closest('[data-close]')) closeModals();
  }));
  // сегмент в «Оформление слоя»
  $$('#style-seg button').forEach(b => b.addEventListener('click', () => {
    $$('#style-seg button').forEach(x => x.classList.remove('on')); b.classList.add('on');
  }));
  // чекбоксы в «Данные»
  $$('#m-data .srcitem').forEach(it => it.addEventListener('click', () => {
    const on = it.classList.toggle('on');
    const c = it.querySelector('.chk'); c.classList.toggle('on', on);
    c.innerHTML = on ? '<svg class="ic"><use href="#i-check"/></svg>' : '';
  }));
  // тумблеры-свитчи
  $$('.switch').forEach(s => s.addEventListener('click', () => s.querySelector('.tg').classList.toggle('off')));

  /* ---- командная палитра ---- */
  const COMMANDS = [
    { sec: 'Инструменты', items: [
      { t: 'Выбор и правка объектов', k: 'V', act: () => selectTool('Выбор') },
      { t: 'Линия', act: () => selectTool('Линия') },
      { t: 'Полигон', act: () => selectTool('Полигон') },
      { t: 'Дуга по трём точкам', act: () => selectTool('Дуга') },
      { t: 'Поворот выделения', k: 'R', act: () => selectTool('Поворот') },
      { t: 'Масштаб выделения', act: () => selectTool('Масштаб') },
      { t: 'Зеркало', act: () => selectTool('Зеркало') },
      { t: 'Обрезать по границе', k: 'T', act: () => selectTool('Обрезать') },
      { t: 'Сопрячь угол (fillet)', act: () => selectTool('Сопрячь') },
    ]},
    { sec: 'Данные', items: [
      { t: 'Данные по видимой области…', k: '⌘D', act: () => openModal('m-data') },
      { t: 'Импорт ГИС ОГД (ZIP / GeoJSON / папка)', act: () => toast('Импорт ГИС ОГД') },
      { t: 'Административные границы (OSM)', act: () => toast('Границы OSM') },
      { t: 'Рельеф: горизонтали из DEM', act: () => toast('Горизонтали') },
    ]},
    { sec: 'Вид и проект', items: [
      { t: 'Переключить тему (свет/тёмная)', act: () => $('#btn-theme').click() },
      { t: 'Подложка: спутник Sentinel-2', act: () => toast('Подложка Sentinel-2') },
      { t: 'Вписать всё в экран', k: 'F', act: () => toast('Вписать всё') },
      { t: 'Собрать альбом АГК', act: () => toast('Сборка альбома…') },
    ]},
  ];
  let cmdkFlat = [], cmdkSel = 0;
  const cmdk = $('#cmdk'), cmdkQ = $('#cmdk-q'), cmdkList = $('#cmdk-list');

  function renderCmdk(q) {
    q = (q || '').trim().toLowerCase();
    cmdkFlat = []; let html = '';
    for (const g of COMMANDS) {
      const items = g.items.filter(i => !q || i.t.toLowerCase().includes(q));
      if (!items.length) continue;
      html += `<div class="cmdk-sec">${g.sec}</div>`;
      for (const i of items) {
        const idx = cmdkFlat.push(i) - 1;
        html += `<div class="cmdk-row" data-i="${idx}"><svg class="ic"><use href="#i-dot"/></svg>${i.t}${i.k ? `<span class="hint">${i.k}</span>` : ''}</div>`;
      }
    }
    cmdkList.innerHTML = html || '<div class="cmdk-empty">Ничего не найдено</div>';
    cmdkSel = 0; highlight();
    $$('.cmdk-row', cmdkList).forEach(r => {
      r.addEventListener('mousemove', () => { cmdkSel = +r.dataset.i; highlight(); });
      r.addEventListener('click', () => runCmdk(+r.dataset.i));
    });
  }
  function highlight() {
    $$('.cmdk-row', cmdkList).forEach(r => r.classList.toggle('sel', +r.dataset.i === cmdkSel));
  }
  function runCmdk(i) { const c = cmdkFlat[i]; closeCmdk(); if (c) c.act(); }
  function openCmdk() { closeFloaters(); cmdk.hidden = false; cmdkQ.value = ''; renderCmdk(''); cmdkQ.focus(); }
  function closeCmdk() { cmdk.hidden = true; }
  $('#open-cmdk').addEventListener('click', openCmdk);
  cmdkQ.addEventListener('input', () => renderCmdk(cmdkQ.value));
  cmdkQ.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); cmdkSel = Math.min(cmdkFlat.length - 1, cmdkSel + 1); highlight(); scrollSel(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cmdkSel = Math.max(0, cmdkSel - 1); highlight(); scrollSel(); }
    else if (e.key === 'Enter') { e.preventDefault(); runCmdk(cmdkSel); }
  });
  function scrollSel() { const r = $(`.cmdk-row[data-i="${cmdkSel}"]`, cmdkList); if (r) r.scrollIntoView({ block: 'nearest' }); }
  cmdk.addEventListener('click', e => { if (e.target === cmdk) closeCmdk(); });

  /* ---- глобальные клавиши ---- */
  addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openCmdk(); return; }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); openModal('m-data'); return; }
    if (e.key === 'Escape') { closeCmdk(); closeModals(); closeFloaters(); }
    // хоткеи инструментов — только когда фокус не в поле ввода
    if (!/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      const map = { v: 'Выбор', r: 'Поворот', t: 'Обрезать', e: 'Продлить', m: 'Измерение', d: 'Размер' };
      const n = map[e.key.toLowerCase()];
      if (n && !e.metaKey && !e.ctrlKey) selectTool(n);
    }
  });

  /* ---- клик вне — закрыть меню/поповеры ---- */
  document.addEventListener('click', () => closeFloaters());

  /* ---- прочие кнопки с тостом ---- */
  $$('[data-toast]').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    if (b.hasAttribute('data-close')) closeModals();
    toast(b.dataset.toast);
  }));

  /* холст-заглушка: движения курсора → координаты в статусе (демо) */
  $('#scene').addEventListener('mousemove', e => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = 43000 + (e.clientX - r.left) * 2, y = 6179500 - (e.clientY - r.top) * 2;
    $('#st-coords').innerHTML = `X ${x.toLocaleString('ru').replace(/,/g,' ')}&nbsp;&nbsp;Y ${y.toLocaleString('ru').replace(/,/g,' ')}`;
  });
})();
