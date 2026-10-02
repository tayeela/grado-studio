/* Размер интерфейса, выбранный в «Окна» → «Размер интерфейса»: ставится до отрисовки, чтобы страница не прыгала.
   Отдельный файл, а не скрипт в index.html: политика страницы (CSP script-src 'self') встроенные скрипты не выполняет. */
try { var u = localStorage.getItem("grado2.uisize"); if (u === "normal" || u === "large") document.documentElement.dataset.ui = u; } catch (e) { }
