// @ts-check
/* Рабочая страница как движок окна «Листы и альбом» нового интерфейса (/next/, ui/src/albumhost.js) по адресу /old?embed=album:
   скрытая рамка iframe внутри нового интерфейса (сборка и печать альбома, albumapi.js) или, по кнопке «Подробно»,
   отдельное окно браузера (рамки листов на карте, «Слои и листы», макет надписей).
   Ставится до отрисовки: класс embed на <html> прячет шапку, ленту и панели (стили в index.html), тема — как у нового интерфейса.
   Проект приходит из нового интерфейса (applyProject), правки уходят туда же (project.js markDirty → EMBED_HOST.gradoEmbed);
   своего автосохранения, входа и совместной работы у этого окна нет. Новый интерфейс закрыт — страница обычная. */
var EMBED = "", EMBED_HOST = null;
try {
  EMBED = new URLSearchParams(location.search).get("embed") || "";
  if (EMBED && window.parent !== window && /** @type {any} */ (window.parent).gradoEmbed) EMBED_HOST = window.parent;          // скрытый движок в iframe
  else if (EMBED && window.opener && !window.opener.closed && window.opener.gradoEmbed) EMBED_HOST = window.opener;   // окно «Подробно»
} catch (e) { EMBED_HOST = null; }
if (EMBED && EMBED_HOST) {
  document.documentElement.classList.add("embed");
  var embedTheme = new URLSearchParams(location.search).get("theme");
  if (embedTheme === "dark" || embedTheme === "light") document.documentElement.dataset.theme = embedTheme;
} else EMBED = "";
window.EMBED = EMBED;
window.EMBED_HOST = EMBED_HOST;
