/* Оформление подписей альбома (albums.js): железнодорожные станции и кавычки. Чистые функции, без карты.
   Правило 15 (владелец 05.10.2026): станция подписывается «ст. ж/д Калошино», сокращение не отрывается от названия
   (неразрывные пробелы). Станция — по признакам данных, а не по названию: землепользование OSM «railway» с названием,
   тег railway = station / halt / yard и т. п., типы Яндекса «транспорт: станция». Депо, заводы и прочее на железной
   дороге, и названия без признаков станции не переименовываются. Запуск проверок — tests/test_labelfmt_js.py. */
(function (root) {
  const NB = " ", STN_PREFIX = "ст." + NB + "ж/д" + NB;
  const HAS_PREFIX = /^(?:ж\/д[\s ]+)?(?:ст\.?|станция)(?:[\s ]+ж\/д)?(?=[\s ]|$)[\s ]*|^ж\/д[\s ]+(?=\S)/i;
  const NOT_STATION = /(^|[\s ])(депо|тч|завод|склад|терминал|тяговая|мастерские|вагонное|локомотивное|эксплуатационное|платформа|пл\.|о\.п\.|парк|тэц|ремонтн[а-яё]*|пост)([\s .,\-–№\d]|$)/i;
  const RAIL_TAGS = /^(station|halt|yard|stop|railway_station|train_station)$/i;
  const YA_TYPES = /transport-(railway-)?(station|halt|platform)|railway-station/i;
  const pick = (p, ...ks) => { for (const k of ks) { const v = p && (typeof p.get === "function" ? p.get(k) : p[k]); if (v != null && v !== "") return String(v); } return ""; };
  // признак станции по атрибутам объекта (OSM: Землепользование / Железная дорога; Яндекс: ft_type_name; ЕГКО: Тип)
  function isStation(p) {
    if (/^railway$/i.test(pick(p, "Землепользование"))) return true;
    if (RAIL_TAGS.test(pick(p, "Железная дорога", "railway"))) return true;
    if (YA_TYPES.test(pick(p, "ft_type_name", "Тип", "Вид"))) return true;
    return false;
  }
  // «Калошино» → «ст. ж/д Калошино»; уже с «ст.» / «станция» — приводится к одному виду, без двойной приставки
  function stationLabel(name) {
    let n = String(name || "").replace(/[\s ]+/g, " ").trim();
    n = n.replace(HAS_PREFIX, "").trim();
    return n ? STN_PREFIX + n.split(" ")[0] + (n.includes(" ") ? " " + n.slice(n.indexOf(" ") + 1) : "") : "";
  }
  // подпись объекта: станция получает приставку, остальное — как есть (null — подписи нет)
  function placeLabel(props, name) {
    const n = String(name || "").trim(); if (!n) return null;
    return isStation(props) && !NOT_STATION.test(n) ? stationLabel(n) : n;
  }
  // прямые кавычки в подписях листа → «ёлочки»: открывающая — в начале или после пробела / скобки / тире, закрывающая — иначе;
  // нечётное число кавычек (обрезанное название) не трогаем
  function guillemets(s) {
    s = String(s == null ? "" : s).replace(/[\u201c\u201d\u201e]/g, '"');
    if (!s.includes('"') || (s.match(/"/g).length % 2)) return s;
    return s.replace(/"/g, (m, i) => !s[i - 1] || /[\s\u00a0(\[\u2014\u2013-]/.test(s[i - 1]) ? "\u00ab" : "\u00bb");
  }
  const api = { NB, STN_PREFIX, isStation, stationLabel, placeLabel, guillemets };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LabelFmt = api;
})(typeof window !== "undefined" ? window : globalThis);
