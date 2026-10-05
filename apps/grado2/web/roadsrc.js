/* Источник дорог листа альбома (albums.js): решение «полигоны Яндекса или запасной источник». Чистая функция, без карты.
   Решение 05.10.2026 (T76): на всех листах дороги — только полигоны проезжей части Яндекса (владелец). Там, где у Яндекса
   полигонов нет или их мало (деревни ТиНАО, «Безобразово»), лист не остаётся без дорог: берётся запасной источник
   ЭТОГО листа — полигоны ЕГКО (egko.roads), если они есть в рамке, иначе УДС по осям (calc.uds_ya: оси Яндекса с
   шириной по классу). «Мало» — полигоны Яндекса в рамке меньше 20 % площади calc.uds_ya в той же рамке либо их нет
   вовсе. В обычном (московском) случае запасные слои пусты и не рисуются. Запуск проверок — tests/test_roadsrc_js.py. */
(function (root) {
  const MIN_SHARE = .2;
  // ya, uds, egko — площади (м²) в рамке листа: полигоны Яндекса, calc.uds_ya, egko.roads
  function pickRoadSource({ ya = 0, uds = 0, egko = 0 } = {}, minShare = MIN_SHARE) {
    if (ya > 0 && (uds <= 0 || ya >= minShare * uds)) return "yandex";
    if (egko > 0) return "egko";
    if (uds > ya) return "uds";
    return ya > 0 ? "yandex" : "none";
  }
  const api = { MIN_SHARE, pickRoadSource };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RoadSrc = api;
})(typeof window !== "undefined" ? window : globalThis);
