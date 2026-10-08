// @ts-check
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
  // кавычки в подписях листа (правило 17): внешние «ёлочки», вложенные „лапки“. « и „ — всегда открывающие, » — закрывающая;
  // прямые и “ ” — по контексту: открывающая в начале, после пробела / скобки / тире / открывающей кавычки, иначе закрывающая.
  // Не сошлись открывающие и закрывающие (обрезанное название) — строку не трогаем
  function guillemets(s) {
    s = String(s == null ? "" : s);
    if (!/["\u00ab\u00bb\u201c\u201d\u201e]/.test(s)) return s;
    let depth = 0, out = "", prevOpen = false;
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (!/["\u00ab\u00bb\u201c\u201d\u201e]/.test(c)) { out += c; prevOpen = false; continue; }
      const p = s[i - 1];
      const open = c === "\u00ab" || c === "\u201e" ? true : c === "\u00bb" ? false
        : !p || prevOpen || /[\s\u00a0(\[\u2014\u2013-]/.test(p);
      if (open) { depth++; out += depth === 1 ? "\u00ab" : "\u201e"; }
      else { if (depth < 1) return s; out += depth === 1 ? "\u00bb" : "\u201c"; depth--; }
      prevOpen = open;
    }
    return depth ? s : out;
  }
  // F5 (06.10.2026): ВРИ в таблице — с заглавной буквы (как в ЕГРН, слайд-правило 6.13); предлог или союз не длиннее трёх букв не
  // остаётся в конце строки — связывается со следующим словом неразрывным пробелом (п. 12)
  const SHORT = "в|во|на|к|ко|с|со|у|о|об|от|до|по|из|за|для|при|без|над|под|про|и|а|но|да|не|ни|или";
  const SHORT_RE = new RegExp("(^|[\\s(«])(" + SHORT + ")[ \\t]+(?=\\S)", "gi");
  const capFirst = s => String(s == null ? "" : s).replace(/^(\s*[«"(]?)([а-яёa-z])/, (m, a, b) => a + b.toUpperCase());
  const tieShort = s => String(s == null ? "" : s).replace(SHORT_RE, (m, a, w) => a + w + NB).replace(SHORT_RE, (m, a, w) => a + w + NB);   // второй проход — «и в»
  const vri = s => tieShort(capFirst(s));
  // ширины колонок таблицы по содержимому (F5): колонка не уже самого длинного слова и заголовка, остаток поровну по «нужде» —
  // длине текста в колонке (не больше cap знаков). budget — сколько знаков помещается в ширину таблицы; min — доля не меньше
  function colWidths(cols, rows, { budget = 80, cap = 60, min = .05 } = {}) {
    const len = x => String(x == null ? "" : x).length, words = x => String(x == null ? "" : x).split(/[\s]+/).filter(Boolean);
    const mn = cols.map((h, i) => Math.max(1, ...[h, ...rows.map(r => r[i])].flatMap(x => words(x).map(len)))),
      want = cols.map((h, i) => Math.min(cap, Math.max(len(h), ...rows.map(r => Math.max(...String(r[i] == null ? "" : r[i]).split("\n").map(len)))))).map((w, i) => Math.max(w, mn[i]));
    const room = Math.max(0, budget - mn.reduce((a, b) => a + b, 0)), need = want.map((w, i) => w - mn[i]), tot = need.reduce((a, b) => a + b, 0) || 1;
    const raw = mn.map((m, i) => m + room * need[i] / tot), sum = raw.reduce((a, b) => a + b, 0);
    let w = raw.map(r => Math.max(min, r / sum)); const k = w.reduce((a, b) => a + b, 0);
    return w.map(x => Math.round(x / k * 1000) / 1000);
  }
  // F6 (правило 17): «Жилой комплекс «Сиреневый парк»» → «ЖК «Сиреневый парк»»
  const complexLabel = s => String(s == null ? "" : s).replace(/^Жилой[\s\u00a0]+комплекс(?=[\s\u00a0]|$)/i, "ЖК");
  // длинное название — в две строки примерно равной длины; у «ЖК» не по середине кавычек: «ЖК / «Квартал Метроном»», а не «ЖК «Квартал / Метроном»» (остальные названия — как раньше, СНТ «Светлая / Поляна»)
  function splitLabel(n, max = 14) {
    const w = String(n || "").split(" "); if (n.length <= max || w.length < 2) return n;
    const bal = t => (t.match(/\u00ab/g) || []).length === (t.match(/\u00bb/g) || []).length, c = [];
    for (let i = 1; i < w.length; i++) c.push([i, Math.abs(w.slice(0, i).join(" ").length - w.slice(i).join(" ").length), bal(w.slice(0, i).join(" "))]);
    const pool = /^ЖК /.test(n) && c.some(x => x[2]) ? c.filter(x => x[2]) : c, best = pool.reduce((a, b) => b[1] < a[1] ? b : a);
    return w.slice(0, best[0]).join(" ") + "\n" + w.slice(best[0]).join(" ");
  }
  // F12: «вл.1» из реестра → «вл. 1» (правило 11: из источника правятся только пробелы и кавычки); пробел неразрывный
  const dotDigit = s => String(s == null ? "" : s).replace(/(^|[\s(«])(вл|д|корп|стр|соор|кв|пом)\.(?=\d)/gi, "$1$2." + NB);
  const api = { dotDigit, NB, STN_PREFIX, isStation, stationLabel, placeLabel, guillemets, capFirst, tieShort, vri, colWidths, complexLabel, splitLabel };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LabelFmt = api;
})(typeof window !== "undefined" ? window : globalThis);
