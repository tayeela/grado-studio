<!-- ГРАДО 2 · экран входа на общем сервере (совместная работа, hub.js): вход через Telegram (если сервер настроен,
     tglogin.py) — главный; логин и пароль — под ссылкой; регистрация по коду приглашения, гостевой вход (если сервер его
     разрешает). Пока экран открыт, программа под ним недоступна. -->
<template>
  <Teleport to="body"><div v-if="hub.login.open" class="hublogin" role="dialog" aria-modal="true" aria-label="Вход в ГРАДО 2">
    <form class="card" @submit.prevent="go">
      <b class="brand">ГРАДО 2</b>
      <div class="tabs" role="tablist">
        <button type="button" role="tab" :aria-selected="f.mode === 'in'" @click="mode('in')">Вход</button>
        <button type="button" role="tab" :aria-selected="f.mode === 'reg'" @click="mode('reg')">Регистрация по приглашению</button>
      </div>
      <label v-if="f.mode === 'reg'">Код приглашения<input v-model="f.invite" autocomplete="off" spellcheck="false"></label>
      <template v-if="hub.login.tg">
        <wa-button variant="brand" class="tg" :disabled="wait || (f.mode === 'reg' && !f.invite.trim())" @click="tg">
          {{ f.mode === "in" ? "Войти через Telegram" : "Зарегистрироваться через Telegram" }}</wa-button>
        <p v-if="hub.login.msg && !pwOpen" class="msg" role="alert">{{ hub.login.msg }}</p>
        <button v-if="!pwOpen" type="button" class="more" @click="openPw">{{ f.mode === "in" ? "Войти по логину и паролю" : "Без Telegram: логин и пароль" }}</button>
      </template>
      <template v-if="!hub.login.tg || pwOpen">
      <label>Логин<input ref="lg" v-model="f.login" autocomplete="username" autocapitalize="off" spellcheck="false"></label>
      <label v-if="f.mode === 'reg'">Как вас зовут<input v-model="f.name" autocomplete="name"></label>
      <label>Пароль<input ref="pw" v-model="f.pw" type="password" :autocomplete="f.mode === 'in' ? 'current-password' : 'new-password'"></label>
      <label v-if="f.mode === 'reg'">Пароль ещё раз<input v-model="f.pw2" type="password" autocomplete="new-password"></label>
      <p v-if="hub.login.msg" class="msg" role="alert">{{ hub.login.msg }}</p>
      <button type="submit" hidden></button>
      <wa-button :variant="hub.login.tg ? 'neutral' : 'brand'" :loading="wait" @click="go">{{ f.mode === "in" ? "Войти" : "Зарегистрироваться" }}</wa-button>
      </template>
      <wa-button v-if="hub.login.guest" appearance="outlined" :disabled="wait" @click="guest">Войти гостем</wa-button>
      <p class="hint">Учётную запись выдаёт администратор: он даёт код приглашения для регистрации.{{ hub.login.tg ? " Вход через Telegram запоминается на 30 дней." : "" }}</p>
    </form>
  </div></Teleport>
</template>

<script setup>
import { nextTick, reactive, ref, watch } from "vue";
import { guestLogin, hub, submitLogin, tgLogin } from "../hub.js";

const f = reactive({ mode: "in", login: "", pw: "", pw2: "", invite: "", name: "" }), wait = ref(false), lg = ref(null), pw = ref(null), pwOpen = ref(false);
function mode(m) { f.mode = m; hub.login.msg = ""; }
function tg() { wait.value = true; tgLogin(f.mode === "reg" ? f.invite.trim() : ""); }
async function openPw() { pwOpen.value = true; await nextTick(); lg.value?.focus(); }
async function go() { if (wait.value) return; wait.value = true; try { if (await submitLogin(f)) { f.pw = f.pw2 = ""; } } finally { wait.value = false; } }
async function guest() { wait.value = true; try { await guestLogin(); } finally { wait.value = false; } }
/* под экраном входа программа недоступна: ни щелчков, ни клавиш */
watch(() => hub.login.open, async on => {
  document.querySelectorAll(".shell").forEach(e => { e.inert = on; });
  if (on) { f.mode = "in"; await nextTick(); (f.login ? pw.value : lg.value)?.focus(); }   /* при входе через Telegram полей нет: фокуса тоже */
}, { immediate: true });
</script>

<style>
.hublogin { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; background: color-mix(in srgb, var(--g-canvas) 82%, transparent); backdrop-filter: blur(3px); }
.hublogin .card { width: min(360px, calc(100vw - 32px)); display: flex; flex-direction: column; gap: 10px; padding: 22px 22px 16px; background: var(--wa-color-surface-raised);
  border: 1px solid var(--g-line); border-radius: 10px; box-shadow: var(--wa-shadow-l); font-size: var(--wa-font-size-s); }
.hublogin .brand { font-size: 18px; letter-spacing: .02em; }
.hublogin .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--g-line); }
.hublogin .tabs button { border: 0; background: none; padding: 6px 4px; color: var(--g-muted); cursor: pointer; font: inherit; border-bottom: 2px solid transparent; }
.hublogin .tabs button[aria-selected=true] { color: var(--wa-color-text-normal); border-bottom-color: var(--wa-color-brand-fill-loud); }
.hublogin label { display: flex; flex-direction: column; gap: 3px; color: var(--g-muted); }
.hublogin input { font: inherit; padding: 6px 8px; border: 1px solid var(--g-line); border-radius: 5px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
.hublogin input:focus { outline: 2px solid var(--wa-color-brand-border-loud); outline-offset: -1px; }
.hublogin .msg { margin: 0; color: var(--wa-color-danger-on-quiet); }
.hublogin .more { align-self: center; border: 0; background: none; padding: 2px; color: var(--g-muted); cursor: pointer; font: inherit; text-decoration: underline; }
.hublogin .more:hover { color: var(--wa-color-text-normal); }
.hublogin .hint { margin: 2px 0 0; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
</style>
