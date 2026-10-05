/* Источник дорог листа альбома (albums.js): решение «полигоны какого источника». Чистая функция, без карты.
   Решение 06.10.2026 (T84, владелец: «сделай на всех векторных схемах дороги ЕГКО, чтобы остались только полигональные»):
   — векторные схемы (основа не снимок: листы 4–8): сначала полигоны ЕГКО (egko.roads); полигоны Яндекса — только там, где
     у ЕГКО в рамке ничего пригодного: площадь ЕГКО меньше 20 % площади Яндекса либо её нет;
   — снимок (листы 3, 9): сначала полигоны Яндекса (решение 05.10.2026), ЕГКО — запасной источник;
   — дороги по осям (calc.uds_ya, calc.uds_osm) не рисуются ни на одном листе альбома: только полигоны.
   Запуск проверок — tests/test_roadsrc_js.py. */
(function (root) {
  const MIN_SHARE = .2;
  // ya, egko — площади (м²) в рамке листа: полигоны Яндекса и egko.roads; vector — основа листа не снимок
  function pickRoadSource({ ya = 0, egko = 0 } = {}, { vector = false, minShare = MIN_SHARE } = {}) {
    if (vector) { if (egko > 0 && (ya <= 0 || egko >= minShare * ya)) return "egko"; return ya > 0 ? "yandex" : "none"; }
    if (ya > 0) return "yandex";
    return egko > 0 ? "egko" : "none";
  }
  const api = { MIN_SHARE, pickRoadSource };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RoadSrc = api;
})(typeof window !== "undefined" ? window : globalThis);
