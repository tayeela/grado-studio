/* ГРАДО 2 · список шрифтов для подписей (владелец 10.10.2026: «любой шрифт, в том числе один из нескольких предустановленных»).
   Сервер (apps/grado2/fonts.py, GET /api/fonts) отдаёт готовые (PT Sans, PT Serif, Montserrat) и шрифты с кириллицей этого
   компьютера и свои файлы; свой файл добавляется POST /api/fonts. Шрифт в печати — «f:<id>» (жирное — «f:<id>-bold»).
   Список один на все окна (вкладка альбома, «Макет надписей»), читается при первом открытии выбора. */
import { reactive } from "vue";

export const fonts = reactive({ list: [], presets: [], loaded: false, busy: false, err: "" });

async function api(url, body) {
  const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || String(r.status));
  return j;
}
const take = j => { fonts.list = j.fonts || []; fonts.presets = j.presets || []; fonts.loaded = true; fonts.err = ""; };

/* refresh — перечитать папки шрифтов (новый шрифт поставлен, пока программа открыта) */
export async function loadFonts(refresh = false) {
  if ((fonts.loaded && !refresh) || fonts.busy) return;
  fonts.busy = true;
  try { take(await api("/api/fonts" + (refresh ? "?refresh=1" : ""))); } catch (e) { fonts.err = e.message || String(e); } finally { fonts.busy = false; }
}

/* свой файл шрифта (TTF, OTF, TTC) → id его семейств; ошибка сервера — понятной фразой */
export async function addFontFile(file) {
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  fonts.busy = true;
  try { const j = await api("/api/fonts", { name: file.name, b64: btoa(bin) }); take(j); return j.ids || []; }
  catch (e) {
    const m = String(e.message || e);
    throw new Error(/Cyrillic|cannot be read/.test(m) ? "в шрифте нет русских букв или файл не читается" : /larger/.test(m) ? "файл шрифта больше 20 МБ" : /not a font/.test(m) ? "это не файл шрифта: нужен TTF, OTF или TTC" : m);
  } finally { fonts.busy = false; }
}

export const fontName = id => fonts.list.find(f => f.id === String(id || "").replace(/-bold$/, ""))?.name || "";
