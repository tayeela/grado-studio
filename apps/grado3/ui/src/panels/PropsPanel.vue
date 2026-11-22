<!-- ГРАДО · окно «Свойства» (план 09.11.2026, шаг И3): оформление активного слоя — способ (единый, категории,
     диапазоны, правила, знаки ЛГР), слои знака (parts: линия, полоса внутрь, штриховка, значки вдоль линии — рисует
     ядро Rust в WebAssembly), библиотека градостроительных знаков, импорт стиля QGIS (.qml через POST /api/style/qml),
     подписи, прозрачность и роль слоя. Каждая правка идёт через шину команд и отменяется Ctrl+Z. -->
<template>
  <div class="g3-panel g3-props">
    <p v-if="!layer" class="g3-muted">Выберите слой в окне «Слои» — здесь настраивается его оформление.</p>
    <template v-else>
      <div class="ph">
        <span class="sw" :class="{ dash: swatch.dash, line: layer.geom === 'line' }"
              :style="{ background: swatch.fill, borderColor: swatch.stroke }" />
        <div class="pt">
          <b class="pn" :title="layer.title || layer.key">{{ layer.title || layer.key }}</b>
          <span class="g3-muted sub">{{ GEOM_LABEL[layer.geom || 'poly'] || layer.geom }} · объектов: {{ count }}</span>
        </div>
        <wa-switch size="small" :checked="layer.visible !== false"
                   @change="cmd.run((layer.visible !== false ? 'скрыть ' : 'показать ') + layer.key)" />
      </div>

      <div class="sec-hd">
        <h3>Оформление</h3>
        <wa-button size="small" appearance="outlined" title="Открыть файл стиля QGIS (.qml)" @click="qmlInput?.click()">
          Стиль из QGIS (.qml)…
        </wa-button>
        <input ref="qmlInput" type="file" accept=".qml" hidden @change="onQmlFile" />
      </div>
      <p v-if="qmlMsg" class="note" :class="{ err: qmlErr }">{{ qmlMsg }}</p>

      <details class="lib">
        <summary>Библиотека знаков ({{ presets.length }})</summary>
        <div class="lib-grid">
          <button v-for="p in presets" :key="p.id" type="button" class="lib-it" :title="p.title" @click="applyPreset(p.style)">
            <span class="sw" :class="{ dash: !!p.style.dash?.length, line: p.geom === 'line' }"
                  :style="{ background: p.geom === 'line' ? 'transparent' : (p.style.fill || '#999'), borderColor: p.style.stroke || p.style.fill || '#333' }" />
            <span class="lib-nm">{{ p.title }}</span>
          </button>
        </div>
      </details>

      <label class="f">
        <span>Способ</span>
        <select :value="st.mode" @change="setMode(($event.target as HTMLSelectElement).value as LayerStyle['mode'])">
          <option value="single">Единый цвет</option>
          <option value="cat">Категории по полю</option>
          <option value="grad">Диапазоны чисел</option>
          <option value="rules">Правила</option>
          <option v-if="hasLgr" value="lgr">Знаки ЛГР (REDLN97)</option>
        </select>
      </label>

      <p v-if="st.mode === 'lgr'" class="g3-muted sub">
        Типы линий ЛГР выбираются по коду линии объекта и рисуются ядром Rust по стандарту REDLN97.
      </p>

      <!-- Категории -->
      <template v-else-if="st.mode === 'cat'">
        <label class="f">
          <span>Поле</span>
          <select :value="st.cat?.field || ''" @change="setCatField(($event.target as HTMLSelectElement).value)">
            <option v-for="k in fields" :key="k" :value="k">{{ k }}</option>
          </select>
        </label>
        <wa-button size="small" appearance="outlined" @click="reclassify">Классифицировать</wa-button>
        <div class="cat-list">
          <div v-for="[v, n] in cats.slice(0, 60)" :key="v" class="cat-row">
            <input type="checkbox" :checked="!(st.cat?.off || []).includes(v)" @change="toggleCatOff(v, !($event.target as HTMLInputElement).checked)" />
            <input type="color" :value="st.cat?.colors?.[v] || OTHER" @change="setCatColor(v, ($event.target as HTMLInputElement).value)" />
            <span class="cat-v" :title="v">{{ v || "—" }}</span>
            <span class="g3-muted">{{ n }}</span>
          </div>
          <p v-if="cats.length > 60" class="g3-muted sub">Показаны первые 60 значений из {{ cats.length }}.</p>
        </div>
      </template>

      <!-- Диапазоны -->
      <template v-else-if="st.mode === 'grad'">
        <p v-if="!nFields.length" class="g3-muted sub">В слое нет числовых полей.</p>
        <template v-else>
          <label class="f">
            <span>Поле</span>
            <select :value="st.grad?.field || ''" @change="patchStyle(s => { s.grad!.field = ($event.target as HTMLSelectElement).value; })">
              <option v-for="k in nFields" :key="k" :value="k">{{ k }}</option>
            </select>
          </label>
          <label class="f">
            <span>Классы</span>
            <select :value="String(st.grad?.n || 5)" @change="patchStyle(s => { s.grad!.n = +($event.target as HTMLSelectElement).value; })">
              <option v-for="n in [3, 4, 5, 6]" :key="n" :value="String(n)">{{ n }}</option>
            </select>
          </label>
          <label class="f">
            <span>Шкала</span>
            <select :value="st.grad?.ramp || 'blue'" @change="patchStyle(s => { s.grad!.ramp = ($event.target as HTMLSelectElement).value; })">
              <option v-for="(t, k) in RAMP_TITLES" :key="k" :value="k">{{ t }}</option>
            </select>
          </label>
        </template>
      </template>

      <!-- Правила -->
      <template v-else-if="st.mode === 'rules'">
        <div v-for="(r, i) in st.rules?.list || []" :key="i" class="rule">
          <div class="r-row">
            <select :value="r.field" @change="patchStyle(s => { s.rules!.list![i].field = ($event.target as HTMLSelectElement).value; })">
              <option v-for="k in fields" :key="k" :value="k">{{ k }}</option>
            </select>
            <select class="op" :value="r.op" @change="patchStyle(s => { s.rules!.list![i].op = ($event.target as HTMLSelectElement).value; })">
              <option v-for="o in OPS" :key="o" :value="o">{{ o }}</option>
            </select>
            <input class="val" type="text" :value="String(r.val ?? '')" placeholder="значение"
                   @change="patchStyle(s => { s.rules!.list![i].val = ($event.target as HTMLInputElement).value; })" />
          </div>
          <div class="r-row">
            <input type="color" :value="r.fill" @change="patchStyle(s => { s.rules!.list![i].fill = ($event.target as HTMLInputElement).value; })" />
            <label v-if="layer.geom !== 'line'" class="chk">
              <input type="checkbox" :checked="!!r.hatch" @change="patchStyle(s => { s.rules!.list![i].hatch = ($event.target as HTMLInputElement).checked; })" />
              <span>штриховка</span>
            </label>
            <span class="g3-muted grow">{{ ruleCount(r, fc) }} об.</span>
            <button type="button" class="xbtn" title="Удалить правило" @click="patchStyle(s => { s.rules!.list!.splice(i, 1); })">×</button>
          </div>
        </div>
        <wa-button size="small" appearance="outlined" @click="addRule">+ Правило</wa-button>
      </template>

      <!-- Основной знак -->
      <template v-if="st.mode !== 'lgr'">
        <div v-if="layer.geom === 'poly' || !layer.geom" class="f">
          <span>Заливка</span>
          <div class="fc">
            <input v-if="st.mode === 'single'" type="color" :value="st.fill || '#9aa1a8'"
                   @change="patchStyle(s => { s.fill = ($event.target as HTMLInputElement).value; })" />
            <input class="rng" type="range" min="0" max="100" :value="Math.round((st.opacity ?? 0.35) * 100)"
                   @change="patchStyle(s => { s.opacity = +($event.target as HTMLInputElement).value / 100; })" />
            <span class="g3-muted num">{{ Math.round((st.opacity ?? 0.35) * 100) }}%</span>
          </div>
        </div>
        <div v-else-if="st.mode === 'single'" class="f">
          <span>Цвет</span>
          <input type="color" :value="st.fill || '#2a78d6'" @change="patchStyle(s => { s.fill = ($event.target as HTMLInputElement).value; })" />
        </div>

        <label v-if="layer.geom === 'poly' || !layer.geom" class="f">
          <span>Штриховка</span>
          <select :value="st.hatch ? (st.hatchPat || '45') : 'none'" @change="setHatch(($event.target as HTMLSelectElement).value)">
            <option value="none">нет</option>
            <option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</option>
          </select>
        </label>

        <div class="f">
          <span>{{ layer.geom === 'line' ? 'Толщина' : 'Контур' }}</span>
          <div class="fc">
            <input v-if="layer.geom !== 'line' && !st.lgrLine" type="color" :value="st.stroke || st.fill || '#3d3d3d'"
                   @change="patchStyle(s => { s.stroke = ($event.target as HTMLInputElement).value; s.strokeOwn = true; })" />
            <input class="w-in" type="number" step="0.2" min="0" max="10" :value="st.width ?? 1.2"
                   @change="patchStyle(s => { s.width = Math.max(0, +($event.target as HTMLInputElement).value || 0); })" />
            <span class="g3-muted">пикс.</span>
          </div>
        </div>

        <label v-if="layer.geom !== 'point'" class="f">
          <span>Линия</span>
          <select :value="dashKey" @change="setDash(($event.target as HTMLSelectElement).value)">
            <option v-for="(t, k) in DASHES" :key="k" :value="k">{{ t }}</option>
            <optgroup v-if="lgrLines.length" label="Знаки ЛГР (Эталон, REDLN97)">
              <option v-for="x in lgrLines" :key="x.code" :value="'lgr:' + x.code">{{ x.code }} · {{ x.title }}</option>
            </optgroup>
          </select>
        </label>

        <label v-if="st.lgrLine && layer.geom !== 'point'" class="f">
          <span>Сторона</span>
          <select :value="st.lgrLine > 0 ? '1' : '-1'" @change="patchStyle(s => { s.lgrLine = Math.abs(s.lgrLine || 1) * +($event.target as HTMLSelectElement).value; })">
            <option value="1">{{ layer.geom === 'poly' ? 'внутрь объекта' : 'справа по ходу' }}</option>
            <option value="-1">{{ layer.geom === 'poly' ? 'наружу' : 'слева по ходу' }}</option>
          </select>
        </label>

        <!-- Слои знака (parts, рендер через ядро Rust) -->
        <template v-if="layer.geom !== 'point'">
          <div class="sec-hd">
            <h3>Слои знака (QGIS / Rust)</h3>
          </div>
          <div v-for="(p, i) in st.parts || []" :key="i" class="part">
            <div class="r-row">
              <select :value="p.k" @change="setPartKind(i, ($event.target as HTMLSelectElement).value as SymbolPart['k'])">
                <option v-for="(t, k) in partKinds" :key="k" :value="k">{{ t }}</option>
              </select>
              <input type="color" :value="p.c || '#333333'" @change="patchStyle(s => { s.parts![i].c = ($event.target as HTMLInputElement).value; })" />
              <button type="button" class="xbtn" :disabled="i === 0" title="Ниже" @click="movePart(i, -1)">↓</button>
              <button type="button" class="xbtn" :disabled="i === (st.parts?.length || 0) - 1" title="Выше" @click="movePart(i, 1)">↑</button>
              <button type="button" class="xbtn" title="Убрать слой знака" @click="dropPart(i)">×</button>
            </div>
            <div class="r-row">
              <template v-if="p.k === 'band'">
                <span class="g3-muted">ширина</span>
                <input class="w-in" type="number" min="1" max="60" :value="p.b ?? 8" @change="patchStyle(s => { s.parts![i].b = +($event.target as HTMLInputElement).value || 8; })" />
                <span class="g3-muted">прозр.</span>
                <input class="rng" type="range" min="0" max="100" :value="Math.round((p.a ?? 0.35) * 100)"
                       @change="patchStyle(s => { s.parts![i].a = +($event.target as HTMLInputElement).value / 100; })" />
              </template>
              <template v-else-if="p.k === 'hatch'">
                <select :value="p.hp || '45'" @change="patchStyle(s => { s.parts![i].hp = ($event.target as HTMLSelectElement).value; })">
                  <option v-for="(t, k) in HATCHES" :key="k" :value="k">{{ t }}</option>
                </select>
                <span class="g3-muted">шаг</span>
                <input class="w-in" type="number" min="4" max="40" :value="p.hs ?? 8" @change="patchStyle(s => { s.parts![i].hs = +($event.target as HTMLInputElement).value || 8; })" />
              </template>
              <template v-else-if="p.k === 'marks'">
                <select :value="p.shape || 'tick'" @change="patchStyle(s => { s.parts![i].shape = ($event.target as HTMLSelectElement).value; })">
                  <option v-for="(t, k) in MARKS" :key="k" :value="k">{{ t }}</option>
                </select>
                <span class="g3-muted">шаг</span>
                <input class="w-in" type="number" min="4" max="120" :value="p.step ?? 16" @change="patchStyle(s => { s.parts![i].step = +($event.target as HTMLInputElement).value || 16; })" />
                <select :value="String(p.side ?? 1)" @change="patchStyle(s => { s.parts![i].side = +($event.target as HTMLSelectElement).value; })">
                  <option value="1">внутрь</option>
                  <option value="-1">наружу</option>
                </select>
              </template>
              <template v-else>
                <span class="g3-muted">толщина</span>
                <input class="w-in" type="number" step="0.2" min="0.2" max="10" :value="p.w ?? 1.2"
                       @change="patchStyle(s => { s.parts![i].w = +($event.target as HTMLInputElement).value || 1; })" />
              </template>
            </div>
          </div>
          <select class="add-part" value="" @change="addPart(($event.target as HTMLSelectElement).value as SymbolPart['k']); ($event.target as HTMLSelectElement).value = ''">
            <option value="">+ добавить слой знака…</option>
            <option v-for="(t, k) in partKinds" :key="k" :value="k">{{ t }}</option>
          </select>
        </template>
      </template>

      <h3>Подписи</h3>
      <label class="f">
        <span>Поле</span>
        <select :value="st.label || ''" @change="patchStyle(s => { s.label = ($event.target as HTMLSelectElement).value; })">
          <option value="">без подписей</option>
          <option v-for="k in fields" :key="k" :value="k">{{ k }}</option>
        </select>
      </label>
      <div v-if="st.label" class="f">
        <span>Шрифт</span>
        <div class="fc">
          <input type="color" :value="st.labelColor || '#1d1d1f'" @change="patchStyle(s => { s.labelColor = ($event.target as HTMLInputElement).value; })" />
          <input class="w-in" type="number" min="7" max="24" :value="st.labelSize || 11"
                 @change="patchStyle(s => { s.labelSize = +($event.target as HTMLInputElement).value || 11; })" />
          <span class="g3-muted">пт</span>
        </div>
      </div>

      <h3>Слой</h3>
      <div class="f">
        <span>Непрозр.</span>
        <div class="fc">
          <input class="rng" type="range" min="0" max="100" :value="Math.round((layer.layerOpacity ?? 1) * 100)"
                 @change="cmd.exec('слой-прозрачность', [layer.key, String(+($event.target as HTMLInputElement).value / 100)])" />
          <span class="g3-muted num">{{ Math.round((layer.layerOpacity ?? 1) * 100) }}%</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  assignCats, CAT, catValues, DASHES, fieldsOf, fullStyle, HATCHES, LGR_LINES, loadSymbologyLibs,
  MARKS, numFields, OPS, OTHER, PART_DEF, PARTS, RAMP_TITLES, ruleCount, swatchOf, SYMBOL_LIBRARY,
  type LayerStyle, type SymbolPart,
} from "../symbology";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";
import { useCommands } from "../stores/commands";

const GEOM_LABEL: Record<string, string> = { poly: "Полигоны", line: "Линии", point: "Точки" };

const project = useProject(), ui = useUi(), cmd = useCommands();
const qmlInput = ref<HTMLInputElement | null>(null);
const qmlMsg = ref("");
const qmlErr = ref(false);
const lgrLines = ref<{ code: number; title: string }[]>([]);

const layer = computed(() => {
  if (ui.selectedLayer) {
    const found = project.layer(ui.selectedLayer);
    if (found) return found;
  }
  return project.layers[0] || null;
});
const fc = computed(() => { void project.dataTick; return layer.value ? project.data(layer.value.key) : null; });
const count = computed(() => fc.value?.features?.length || 0);
const st = computed(() => fullStyle((layer.value?.style || {}) as Partial<LayerStyle>));
const swatch = computed(() => (layer.value ? swatchOf(layer.value) : { fill: OTHER, stroke: "#333", dash: false }));
const fields = computed(() => fieldsOf(fc.value));
const nFields = computed(() => numFields(fc.value));
const cats = computed(() => catValues(fc.value, st.value.cat?.field));
const hasLgr = computed(() => st.value.mode === "lgr" || (fc.value?.features || []).some(f => f.properties?._lt));
const presets = computed(() => {
  const g = layer.value?.geom || "poly";
  return SYMBOL_LIBRARY.filter(p => p.geom === "any" || p.geom === g);
});
const partKinds = computed(() =>
  layer.value?.geom === "line" ? { line: PARTS.line, marks: PARTS.marks } : PARTS,
);
const dashKey = computed(() => {
  if (st.value.lgrLine) return "lgr:" + Math.abs(st.value.lgrLine);
  const d = (st.value.dash || []).join(",");
  return !d ? "solid" : Object.prototype.hasOwnProperty.call(DASHES, d) ? d : "solid";
});

function commitStyle(next: LayerStyle) {
  if (!layer.value) return;
  cmd.exec("стиль", [layer.value.key, JSON.stringify(next)]);
}

function patchStyle(fn: (s: LayerStyle) => void) {
  const next = fullStyle(st.value);
  fn(next);
  commitStyle(next);
}

function applyPreset(preset: LayerStyle) {
  qmlMsg.value = "";
  commitStyle(fullStyle(JSON.parse(JSON.stringify(preset))));
}

function setMode(m: LayerStyle["mode"]) {
  patchStyle(s => {
    s.mode = m || "single";
    if (s.mode === "cat" && !Object.keys(s.cat?.colors || {}).length) assignCats(s, fc.value, false);
    if (s.mode === "grad" && !nFields.value.includes(s.grad?.field || "")) s.grad!.field = nFields.value[0] || "";
  });
}

function setCatField(field: string) {
  patchStyle(s => {
    s.cat!.field = field;
    assignCats(s, fc.value, false);
  });
}

function reclassify() {
  patchStyle(s => { assignCats(s, fc.value, false); });
}

function setCatColor(v: string, c: string) {
  patchStyle(s => { s.cat!.colors![v] = c; });
}

function toggleCatOff(v: string, off: boolean) {
  patchStyle(s => {
    const arr = s.cat!.off || [];
    s.cat!.off = off ? [...new Set([...arr, v])] : arr.filter(x => x !== v);
  });
}

function addRule() {
  patchStyle(s => {
    const list = s.rules!.list!;
    list.push({ field: fields.value[0] || "", op: "=", val: "", fill: CAT[list.length % CAT.length] });
  });
}

function setHatch(v: string) {
  patchStyle(s => {
    if (v === "none") s.hatch = false;
    else { s.hatch = true; s.hatchPat = v; }
  });
}

function setDash(v: string) {
  patchStyle(s => {
    if (v.startsWith("lgr:")) {
      s.lgrLine = +v.slice(4) * ((s.lgrLine || 1) < 0 ? -1 : 1);
      delete s.dash;
      return;
    }
    delete s.lgrLine;
    if (v === "solid") delete s.dash;
    else s.dash = v.split(",").map(Number);
  });
}

function addPart(k: SymbolPart["k"]) {
  if (!k || !PART_DEF[k]) return;
  patchStyle(s => {
    s.parts = [...(s.parts || []), { k, ...JSON.parse(JSON.stringify(PART_DEF[k])) }];
  });
}

function setPartKind(i: number, k: SymbolPart["k"]) {
  patchStyle(s => {
    const cur = s.parts![i];
    s.parts![i] = { k, ...JSON.parse(JSON.stringify(PART_DEF[k])), c: cur.c };
  });
}

function movePart(i: number, d: number) {
  patchStyle(s => {
    const j = i + d;
    if (j < 0 || j >= (s.parts?.length || 0)) return;
    [s.parts![i], s.parts![j]] = [s.parts![j], s.parts![i]];
  });
}

function dropPart(i: number) {
  patchStyle(s => {
    s.parts = (s.parts || []).filter((_, j) => j !== i);
    if (!s.parts.length) delete s.parts;
  });
}

async function onQmlFile(ev: Event) {
  const inp = ev.target as HTMLInputElement;
  const file = inp.files?.[0];
  inp.value = "";
  if (!file || !layer.value) return;
  qmlMsg.value = "";
  qmlErr.value = false;
  try {
    const r = await fetch("/api/style/qml", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ text: await file.text(), geom: layer.value.geom || "poly" }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `Сервер ответил ${r.status}`);
    commitStyle(fullStyle(j.style));
    const rep = (j.report || []) as string[];
    qmlMsg.value = `Стиль «${file.name}» применён` + (rep.length ? `. Не перенесено: ${rep.join("; ")}` : "");
  } catch (e) {
    qmlErr.value = true;
    qmlMsg.value = "Стиль QGIS не открылся: " + (e as Error).message;
  }
}

onMounted(() => {
  loadSymbologyLibs().then(() => { lgrLines.value = LGR_LINES.slice(); });
});
</script>

<style scoped>
.g3-props { display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
.ph { display: flex; align-items: center; gap: 8px; padding-bottom: 6px; border-bottom: 1px solid var(--wa-color-neutral-border-quiet); }
.pt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.pn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub { font-size: 11px; margin: 0; }
.sw { width: 16px; height: 16px; border-radius: 3px; border: 1.5px solid; flex-shrink: 0; box-sizing: border-box; }
.sw.dash { border-style: dashed; }
.sw.line { height: 0; border-width: 2.5px 0 0 0; border-radius: 0; }
.sec-hd { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-top: 4px; }
h3 { margin: 6px 0 0; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--wa-color-text-quiet); }
.sec-hd h3 { margin: 0; }
.note { margin: 0; padding: 6px 8px; border-radius: 6px; background: var(--wa-color-surface-lowered); font-size: 11px; }
.note.err { color: var(--wa-color-danger-on-quiet); background: var(--wa-color-danger-fill-quiet); }
.lib { border: 1px solid var(--wa-color-neutral-border-quiet); border-radius: 6px; padding: 4px 6px; }
.lib summary { cursor: pointer; font-size: 11px; font-weight: 600; color: var(--wa-color-text-quiet); }
.lib-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 6px; }
.lib-it { display: flex; align-items: center; gap: 6px; padding: 4px 6px; border: 1px solid var(--wa-color-neutral-border-quiet); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; font: inherit; font-size: 11px; cursor: pointer; text-align: left; }
.lib-it:hover { background: var(--wa-color-surface-lowered); }
.lib-nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.f { display: grid; grid-template-columns: 78px 1fr; align-items: center; gap: 6px; }
.f select, .rule select, .part select, .add-part, .val, .w-in {
  padding: 4px 6px; border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px;
  background: var(--wa-color-surface-default); color: inherit; font: inherit; font-size: 12px; min-width: 0;
}
.fc { display: flex; align-items: center; gap: 6px; min-width: 0; }
.rng { flex: 1; min-width: 60px; }
.num { width: 34px; text-align: right; font-variant-numeric: tabular-nums; }
.w-in { width: 62px; }
.cat-list { max-height: 220px; overflow: auto; display: flex; flex-direction: column; gap: 3px; border: 1px solid var(--wa-color-neutral-border-quiet); border-radius: 6px; padding: 4px; }
.cat-row { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.cat-v { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rule, .part { border: 1px solid var(--wa-color-neutral-border-quiet); border-radius: 6px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
.r-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.r-row .op { width: 62px; }
.r-row .val { flex: 1; min-width: 70px; }
.grow { flex: 1; }
.chk { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; cursor: pointer; }
.xbtn { border: 0; background: none; color: var(--wa-color-text-quiet); cursor: pointer; padding: 2px 5px; border-radius: 4px; }
.xbtn:hover:not(:disabled) { background: var(--wa-color-surface-lowered); color: var(--wa-color-text-normal); }
.add-part { width: 100%; }
</style>
