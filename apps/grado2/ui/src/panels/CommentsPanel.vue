<!-- ГРАДО 2 · окно «Комментарии» (совместная работа, hub.js; как окно рабочей страницы web/hub.js): комментарий на
     карте (щелчок по карте ставит метку) или к выбранному объекту, список открытых, решённых или всех с номерами меток,
     ответы, «Решено», удаление (автор или владелец, двумя нажатиями). Щелчок по комментарию — карта к его метке. -->
<template>
  <div class="pane comments">
    <p v-if="!hub.pid" class="hint">Комментарии — в совместном проекте на общем сервере. Сначала откройте проект: окно «Совместные проекты».</p>
    <template v-else>
      <div class="btns">
        <wa-button size="s" :appearance="hub.cMode ? 'filled' : 'outlined'" :variant="hub.cMode ? 'brand' : 'neutral'" title="Щёлкните по карте там, где нужна метка. Esc — отмена"
                   @click="setCMode(!hub.cMode)"><MessageSquarePlus :size="14" /> Комментарий на карте</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="!sel.length" title="Метка встанет на выбранный объект и будет ходить вместе с ним" @click="commentSelected">К выбранному объекту</wa-button>
      </div>
      <div v-if="hub.draft" class="compose">
        <div class="where">{{ hub.draft.anchor.lonlat ? "Комментарий к точке на карте" : `Комментарий к объекту слоя «${lyTitle(hub.draft.anchor.layer)}»` }}</div>
        <textarea ref="txt" v-model="text" rows="3" maxlength="4000" placeholder="Текст комментария" aria-label="Текст комментария" @keydown="onKey"></textarea>
        <div class="btns"><wa-button size="s" appearance="plain" @click="cancel">Отмена</wa-button><wa-button size="s" variant="brand" :disabled="!text.trim()" @click="send">Отправить</wa-button>
          <span class="hint">Ctrl+Enter — отправить</span></div>
      </div>
      <div class="filter" role="group" aria-label="Какие комментарии показывать">
        <button v-for="(t, f) in FILTERS" :key="f" :aria-pressed="hub.cFilter === f" @click="hub.cFilter = f">{{ t }}</button>
      </div>
      <p v-if="!shownList.length" class="hint">{{ hub.comments.length ? "В этом списке комментариев нет." : "Комментариев пока нет. Нажмите «Комментарий на карте» и щёлкните по карте, или выберите объект и нажмите «К выбранному объекту»." }}</p>
      <div v-for="{ c, n } in shownList" :key="c.id" class="card" :class="{ done: c.resolved, sel: c.id === hub.cSel }" :data-cid="c.id" @click="pick(c, $event)">
        <div class="h"><span class="pin">{{ n }}</span><b>{{ uname(c.author) }}</b><span class="t">{{ when(c.created) }}</span></div>
        <div class="b">{{ c.text }}</div>
        <div class="a">{{ anchorText(c.anchor) }}{{ c.resolved ? " · решён" : "" }}</div>
        <div v-for="(x, i) in c.replies || []" :key="i" class="r"><div class="h"><b>{{ uname(x.author) }}</b><span class="t">{{ when(x.created) }}</span></div><div>{{ x.text }}</div></div>
        <div v-if="replyFor === c.id" class="compose">
          <textarea v-model="reply" v-focus rows="2" maxlength="4000" placeholder="Ваш ответ" aria-label="Ваш ответ" @keydown.ctrl.enter="doReply(c)" @keydown.meta.enter="doReply(c)"></textarea>
          <div class="btns"><wa-button size="s" appearance="plain" @click="replyFor = null">Отмена</wa-button><wa-button size="s" variant="brand" :disabled="!reply.trim()" @click="doReply(c)">Ответить</wa-button></div>
        </div>
        <div class="btns">
          <wa-button size="s" appearance="plain" @click="replyFor = c.id; reply = ''">Ответить</wa-button>
          <wa-button size="s" appearance="plain" @click="commentAct('resolve', c)">{{ c.resolved ? "Вернуть в работу" : "Решено" }}</wa-button>
          <wa-button v-if="c.author === hub.me?.login || isOwner(myRole())" size="s" :appearance="armed === c.id ? 'filled' : 'plain'" :variant="armed === c.id ? 'danger' : 'neutral'"
                     title="Комментарий удаляется вместе с ответами" @click="del(c)">{{ armed === c.id ? "Точно удалить?" : "Удалить" }}</wa-button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { MessageSquarePlus } from "@lucide/vue";
import { commentAct, commentSelected, hub, isOwner, loadComments, myRole, sendComment, setCMode, sortedComments, uname, when } from "../hub.js";
import { anchorPoint, flyTo } from "../hubmap.js";
import { lyr } from "../edit.js";
import { sel } from "../features.js";
import { notice } from "../project.js";

defineProps({ params: Object });
const vFocus = { mounted: el => el.focus() };
const FILTERS = { open: "Открытые", done: "Решённые", all: "Все" };
const lyTitle = key => lyr(key)?.title || key;
const anchorText = a => a?.lonlat ? "точка на карте" : a?.uid ? (anchorPoint(a) ? `объект слоя «${lyTitle(a.layer)}»` : "объект удалён") : "";
const shownList = computed(() => sortedComments().map((c, i) => ({ c, n: i + 1 })).filter(x => hub.cFilter === "all" || (hub.cFilter === "open") === !x.c.resolved));

const text = ref(""), txt = ref(null), reply = ref(""), replyFor = ref(null), armed = ref(null);
watch(() => hub.draft, async d => { if (d) { await nextTick(); txt.value?.focus(); } });
watch(() => hub.cSel, cid => { const c = hub.comments.find(x => x.id === cid); if (c) { if (!flyTo(anchorPoint(c.anchor))) notice.value = "Объект этого комментария удалён — метки на карте нет"; nextTick(() => document.querySelector(`.comments [data-cid="${CSS.escape(cid)}"]`)?.scrollIntoView({ block: "nearest" })); } });
function pick(c, e) { if (e.target.closest("wa-button, textarea")) return; if (hub.cSel === c.id) { if (!flyTo(anchorPoint(c.anchor))) notice.value = "Объект этого комментария удалён — метки на карте нет"; } else hub.cSel = c.id; }
function cancel() { hub.draft = null; hub.cMode = false; text.value = ""; }
async function send() { const t = text.value.trim(); if (t && await sendComment(t)) text.value = ""; }
function onKey(e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); if (e.key === "Escape") cancel(); }
async function doReply(c) { const t = reply.value.trim(); if (t && await commentAct("reply", c, t)) { replyFor.value = null; reply.value = ""; } }
function del(c) { if (armed.value === c.id) { armed.value = null; commentAct("delete", c); return; } armed.value = c.id; setTimeout(() => { if (armed.value === c.id) armed.value = null; }, 4000); }
loadComments();
</script>

<style>
.comments .btns { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 4px 0; }
.comments wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
.comments .compose { display: flex; flex-direction: column; gap: 4px; margin: 6px 0; }
.comments .compose .where { font-size: var(--wa-font-size-xs); color: var(--g-muted); }
.comments textarea { font: inherit; font-size: var(--wa-font-size-s); padding: 5px 7px; border: 1px solid var(--g-line); border-radius: 5px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); resize: vertical; }
.comments .filter { display: flex; gap: 2px; margin: 6px 0; }
.comments .filter button { border: 1px solid var(--g-line); background: none; padding: 2px 8px; border-radius: 4px; font: inherit; font-size: var(--wa-font-size-xs); color: var(--g-muted); cursor: pointer; }
.comments .filter button[aria-pressed=true] { background: var(--wa-color-neutral-fill-quiet); color: var(--wa-color-text-normal); }
.comments .card { border: 1px solid var(--g-line); border-radius: 6px; padding: 6px 8px; margin: 6px 0; font-size: var(--wa-font-size-s); cursor: pointer; }
.comments .card.sel { border-color: var(--wa-color-brand-border-loud); box-shadow: 0 0 0 1px var(--wa-color-brand-border-loud); }
.comments .card.done { opacity: .7; }
.comments .card .h { display: flex; gap: 6px; align-items: baseline; }
.comments .card .t { color: var(--g-muted); font-size: var(--wa-font-size-2xs); }
.comments .card .b { white-space: pre-wrap; margin: 3px 0; }
.comments .card .a { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.comments .card .r { margin: 4px 0 0 12px; padding-left: 8px; border-left: 2px solid var(--g-line); }
.comments .pin { display: inline-grid; place-items: center; min-width: 18px; height: 18px; border-radius: 9px; background: #d9822b; color: #fff; font: 600 10px/1 system-ui, sans-serif; }
.comments .card.done .pin { background: #8a8d91; }
</style>
