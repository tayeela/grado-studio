<!-- ГРАДО 2 · шапка совместной работы (общий сервер, hub.js): открытый проект и ваша роль, состояние отправки правок,
     кто сейчас в проекте, кнопки «Доступ», «Комментарии», «История», метка комментария на карте и меню учётной записи
     (команды, пользователи и приглашения — у администратора, смена пароля, выход). -->
<template>
  <span v-if="hub.me" class="hubbar">
    <wa-button size="s" appearance="outlined" :title="hub.pid ? `Проект «${hub.name}». Ваша роль: ${ROLE[myRole()] || '—'}. Совместные проекты: открыть, создать, загрузить` : 'Совместные проекты: открыть, создать, загрузить'"
               @click="openWin('projects')"><FolderOpen :size="14" /> {{ hub.pid ? hub.name || "Проект" : "Выберите проект" }}</wa-button>
    <span v-if="hub.pid" class="pill">{{ ROLE[myRole()] || "" }}</span>
    <span v-if="hub.pid" class="sync" :data-state="C.status" :title="SYNC[C.status]?.[1]"><i></i>{{ SYNC[C.status]?.[0] }}</span>
    <span class="avs" :title="others.length ? 'Сейчас в проекте: ' + others.map(u => u.name || u.login).join(', ') : 'Кроме вас, в проекте сейчас никого нет'">
      <span v-for="u in others.slice(0, 4)" :key="u.login" class="av" :style="{ background: safeColor(u.color), color: ink(safeColor(u.color)) }">{{ initials(u.name, u.login) }}</span>
      <span v-if="others.length > 4" class="more">+{{ others.length - 4 }}</span>
    </span>
    <wa-button size="s" appearance="plain" :disabled="!hub.pid" aria-label="Доступ" title="Доступ: участники, роли, ссылка, команда" @click="openWin('share')"><Users :size="15" /></wa-button>
    <wa-button size="s" appearance="plain" :disabled="!hub.pid" aria-label="Комментарии" :title="`Комментарии${nOpen ? ': открытых ' + nOpen : ''}`" @click="winApi.open('comments')">
      <MessageSquare :size="15" /><span v-if="nOpen" class="cnt">{{ nOpen }}</span></wa-button>
    <wa-button size="s" :appearance="hub.cMode ? 'filled' : 'plain'" :variant="hub.cMode ? 'brand' : 'neutral'" :disabled="!hub.pid"
               aria-label="Комментарий на карте" title="Комментарий на карте: щёлкните по карте, где нужна метка (Esc — отмена)" @click="setCMode(!hub.cMode)"><MessageSquarePlus :size="15" /></wa-button>
    <wa-button size="s" appearance="plain" :disabled="!hub.pid" aria-label="История" title="История: сохранённые версии и кто что делал" @click="openWin('history')"><History :size="15" /></wa-button>
    <wa-dropdown @wa-select="onAcc">
      <wa-button slot="trigger" size="s" appearance="plain" with-caret :title="`Вы вошли как ${hub.me.name || hub.me.login} (${hub.me.login})`"><CircleUser :size="15" /> {{ hub.me.name || hub.me.login }}</wa-button>
      <wa-dropdown-item value="teams">Команды</wa-dropdown-item>
      <wa-dropdown-item v-if="hub.me.admin" value="admin">Пользователи и приглашения</wa-dropdown-item>
      <wa-dropdown-item v-if="!hub.me.guest" value="pw">Сменить пароль</wa-dropdown-item>
      <wa-dropdown-item v-if="hub.login.tg && !hub.me.guest && !hub.me.tg" value="tg">Привязать Telegram</wa-dropdown-item>
      <wa-divider></wa-divider>
      <wa-dropdown-item value="out">Выйти</wa-dropdown-item>
    </wa-dropdown>
    <span v-if="viewer()" class="pill ro" title="У вас права только на просмотр: можно смотреть и оставлять комментарии">только просмотр</span>

    <wa-dialog label="Смена пароля" :open="pwDlg" @wa-after-hide="pwDlg = false">
      <form class="pwform" @submit.prevent="savePw">
        <label>Старый пароль<input v-model="pw.old" type="password" autocomplete="current-password"></label>
        <label>Новый пароль<input v-model="pw.nw" type="password" autocomplete="new-password"></label>
        <label>Новый пароль ещё раз<input v-model="pw.nw2" type="password" autocomplete="new-password"></label>
        <p v-if="pw.msg" class="warn">{{ pw.msg }}</p>
        <button type="submit" hidden></button>
      </form>
      <wa-button slot="footer" size="s" appearance="plain" @click="pwDlg = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" @click="savePw">Сменить</wa-button>
    </wa-dialog>
  </span>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { CircleUser, FolderOpen, History, MessageSquare, MessageSquarePlus, Users } from "@lucide/vue";
import { C, ROLE, SYNC, changePassword, hub, initials, ink, logout, myRole, openComments, openWin, safeColor, setCMode, tgBind, viewer } from "../hub.js";
import { winApi } from "../store.js";

const others = computed(() => { const seen = new Set(); return hub.others.filter(u => u.login !== hub.me?.login && !seen.has(u.login) && seen.add(u.login)); });
const nOpen = computed(() => openComments());
const pwDlg = ref(false), pw = reactive({ old: "", nw: "", nw2: "", msg: "" });
function onAcc(e) {
  const v = e.detail.item.value;
  if (v === "pw") { Object.assign(pw, { old: "", nw: "", nw2: "", msg: "" }); pwDlg.value = true; }
  else if (v === "out") logout();
  else if (v === "tg") tgBind();
  else openWin(v);
}
async function savePw() {
  if (pw.nw.length < 8) { pw.msg = "Новый пароль должен быть не короче 8 знаков."; return; }
  if (pw.nw !== pw.nw2) { pw.msg = "Новые пароли не совпадают."; return; }
  try { await changePassword(pw.old, pw.nw); pwDlg.value = false; } catch (e) { pw.msg = e.message; }
}
</script>

<style>
.hubbar { display: inline-flex; align-items: center; gap: 4px; margin-right: var(--wa-space-s); }
.hubbar wa-button::part(label) { display: inline-flex; gap: 5px; align-items: center; }
.hubbar .pill { font-size: var(--wa-font-size-2xs); padding: 1px 6px; border-radius: 9px; background: var(--wa-color-neutral-fill-quiet); color: var(--g-muted); white-space: nowrap; }
.hubbar .pill.ro { background: color-mix(in srgb, var(--wa-color-warning-fill-loud) 22%, transparent); color: var(--wa-color-text-normal); }
.hubbar .sync { display: inline-flex; align-items: center; gap: 4px; font-size: var(--wa-font-size-xs); color: var(--g-muted); white-space: nowrap; }
.hubbar .sync i { width: 7px; height: 7px; border-radius: 50%; background: #3a9b5c; }
.hubbar .sync[data-state=sending] i, .hubbar .sync[data-state=conflict] i { background: #d9822b; }
.hubbar .sync[data-state=offline] i, .hubbar .sync[data-state=full] i { background: #c4392d; }
.hubbar .sync[data-state=readonly] i { background: #8a8d91; }
.hubbar .avs { display: inline-flex; }
.hubbar .av { width: 22px; height: 22px; border-radius: 50%; display: inline-grid; place-items: center; font: 600 10px/1 system-ui, sans-serif; border: 2px solid var(--g-bar); margin-left: -5px; }
.hubbar .avs .av:first-child { margin-left: 0; }
.hubbar .more { font-size: var(--wa-font-size-2xs); color: var(--g-muted); margin-left: 3px; }
.hubbar .cnt { font-size: 10px; min-width: 14px; padding: 0 3px; border-radius: 7px; background: #d9822b; color: #fff; }
.pwform { display: flex; flex-direction: column; gap: 8px; font-size: var(--wa-font-size-s); }
.pwform label { display: flex; flex-direction: column; gap: 3px; color: var(--g-muted); }
.pwform input { font: inherit; padding: 5px 8px; border: 1px solid var(--g-line); border-radius: 5px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
</style>
