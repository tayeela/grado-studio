<!-- ГРАДО 2 · окна совместной работы (общий сервер, hub.js), как окна рабочей страницы web/hub.js:
     «Совместные проекты» — те же карточки с превью, что окно «Проекты» папки (ProjectCard.vue): поиск, порядок, только с альбомом,
     избранное, открыть, переименовать, копия, скачать, удалить (с вопросом); создать пустой, сделать общей текущую работу, загрузить файл.
     «Доступ» (участники и роли, команда, ссылка), «Команды», «История» (версии и кто что делал), «Пользователи и приглашения» (администратор).
     Прочее необратимое — двумя нажатиями: первое взводит кнопку на 4 с. -->
<template>
  <!-- ======== совместные проекты ======== -->
  <wa-dialog class="hubwin wide" label="Совместные проекты" :open="hub.win === 'projects'" @wa-after-hide="close('projects')">
    <div class="bar">
      <input v-model="newName" class="grow" maxlength="60" placeholder="Название нового проекта" aria-label="Название нового проекта" @keydown.enter="create">
      <label class="dim">Где создать <select v-model="newTeam" aria-label="Где создать"><option value="">Личные</option><option v-for="t in hub.teams || []" :key="t.id" :value="t.id">{{ t.name }}</option></select></label>
      <wa-button size="s" variant="brand" @click="create">Создать пустой</wa-button>
      <wa-button size="s" appearance="outlined" title="Открытая сейчас работа станет общим проектом под этим названием" @click="share">Сделать общим текущую работу</wa-button>
      <wa-button size="s" appearance="outlined" @click="fileIn.click()">Загрузить файл .grado2…</wa-button>
      <input ref="fileIn" type="file" accept=".grado2,application/json" hidden @change="onFile">
    </div>
    <div class="bar">
      <input :value="hub.q" class="grow" type="search" placeholder="Поиск по названию или команде" aria-label="Поиск проекта" @input="e => setPref('q', e.target.value)">
      <select :value="hub.ord" aria-label="Порядок" @change="e => setPref('ord', e.target.value)"><option value="recent">Недавние</option><option value="name">По названию</option></select>
      <wa-button size="s" :appearance="hub.album ? 'filled' : 'outlined'" :variant="hub.album ? 'brand' : 'neutral'" title="Только проекты, где собран альбом" @click="setPref('album', !hub.album)">С альбомом</wa-button>
    </div>
    <p v-if="!hub.projects.length" class="empty">Совместных проектов пока нет. Введите название и нажмите «Создать пустой» или «Сделать общим текущую работу».</p>
    <p v-else-if="!groups.length" class="empty">Ничего не найдено</p>
    <template v-else>
      <section v-for="g in groups" :key="g.title" class="pgroup">
        <h4 class="sec">{{ g.title }}</h4>
        <div class="pgrid">
          <ProjectCard v-for="p in g.rows" :key="g.title + p.id" :name="p.name" :img="previewOf(p)" :star="!!p.star" :current="p.id === hub.pid"
                       :editing="ren === g.title + p.id" :renamable="isOwner(p.role)" empty-text="Пока без объектов"
                       @open="p.id !== hub.pid && openProject(p.id, p.name)" @star="starProject(p)" @edit="ren = g.title + p.id" @cancel="ren = null"
                       @rename="v => { ren = null; renameProject(p.id, v.slice(0, 60)); }" @act="a => act(a, p, g)">
            <template #sub>{{ ROLE[p.role] || p.role }} · {{ p.updated_by ? uname(p.updated_by) + ", " : "" }}{{ p.updated ? when(p.updated) : "" }}<template v-if="+p.album_n"> · альбом {{ p.album_n }} л.</template><template v-if="+p.online"> · <b class="on">в проекте {{ p.online }}</b></template></template>
            <template #menu>
              <wa-dropdown-item value="open" :disabled="p.id === hub.pid">{{ p.id === hub.pid ? "Открыт" : "Открыть" }}</wa-dropdown-item>
              <wa-dropdown-item v-if="isOwner(p.role)" value="ren">Переименовать</wa-dropdown-item>
              <wa-dropdown-item value="copy">Сделать копию…</wa-dropdown-item>
              <wa-dropdown-item value="down">Скачать файл .grado2</wa-dropdown-item>
              <template v-if="isOwner(p.role)"><wa-divider></wa-divider><wa-dropdown-item value="del" variant="danger">Удалить у всех…</wa-dropdown-item></template>
            </template>
          </ProjectCard>
        </div>
        <div v-if="g.rows.some(p => p.id === cp.id) && !g.fav" class="bar copy">
          <input v-model="cp.name" v-focus class="grow" maxlength="60" aria-label="Название копии" @keydown.enter="doCopy" @keydown.esc.stop="cp.id = null">
          <label class="dim">Где создать <select v-model="cp.team" aria-label="Где создать копию"><option value="">Личные</option><option v-for="t in hub.teams || []" :key="t.id" :value="t.id">{{ t.name }}</option></select></label>
          <wa-button size="s" variant="brand" @click="doCopy">Создать копию</wa-button><wa-button size="s" appearance="plain" @click="cp.id = null">Отмена</wa-button>
        </div>
      </section>
    </template>
    <wa-dialog label="Удалить проект у всех?" :open="!!delAsk" @wa-after-hide="delAsk = null">
      <p>Проект «{{ delAsk?.name }}», его комментарии и история версий будут удалены у всех участников. Вернуть его будет нельзя.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="delAsk = null">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="deleteProject(delAsk); delAsk = null">Удалить</wa-button>
    </wa-dialog>
  </wa-dialog>

  <!-- ======== доступ ======== -->
  <wa-dialog class="hubwin" label="Доступ к проекту" :open="hub.win === 'share'" @wa-after-hide="close('share')">
    <p v-if="!hub.pid" class="empty">Сначала откройте проект: окно «Совместные проекты».</p>
    <template v-else>
      <p class="note">Проект «{{ hub.name }}». {{ own ? "Вы владелец: можно добавлять и убирать участников и менять их роли." : "Менять доступ может только владелец проекта." }}</p>
      <table class="hubt"><tbody>
        <tr><td class="nm">Где лежит проект</td><td><select :value="pr.team || ''" :disabled="!own" aria-label="Где лежит проект"
          @change="e => setTeam(e.target.value || null, e.target.value && pr.team ? pr.team_access || 'edit' : 'edit', e.target.value ? 'Проект перенесён в команду' : 'Проект стал личным')">
          <option value="">Личные</option><option v-for="t in hub.teams || []" :key="t.id" :value="t.id">{{ t.name }}</option>
          <option v-if="pr.team && !myTeam(pr.team)" :value="pr.team">{{ pr.team_name || "Команда" }}</option></select></td></tr>
        <tr v-if="pr.team"><td class="nm">Вся команда «{{ pr.team_name || "" }}»</td><td><select :value="pr.team_access || 'edit'" :disabled="!own" aria-label="Доступ всей команды"
          @change="e => setTeam(pr.team, e.target.value, 'Доступ команды изменён')"><option v-for="(t, r) in TACC" :key="r" :value="r">{{ t }}</option></select></td></tr>
      </tbody></table>
      <div class="sec">Доступ по ссылке</div>
      <p v-if="!own" class="note">{{ pr.link_role && LINKR[pr.link_role] ? `Сейчас: ${LINKR[pr.link_role]}. ` : "" }}Включать и выключать ссылку может только владелец проекта.</p>
      <p v-else-if="!hub.link || hub.link.pid !== hub.pid" class="note">Загружаю…</p>
      <p v-else-if="hub.link.err" class="note">Не удалось получить настройки ссылки: закройте и снова откройте окно.</p>
      <template v-else>
        <table class="hubt"><tbody><tr><td class="nm">Кто может открыть по ссылке</td><td>
          <select :value="hub.link.link?.role || ''" aria-label="Доступ по ссылке" @change="e => setLink({ role: e.target.value || null }, e.target.value ? 'Доступ по ссылке включён' : 'Доступ по ссылке выключен')">
            <option v-for="(t, r) in LINKR" :key="r" :value="r">{{ t }}</option></select></td></tr></tbody></table>
        <div v-if="hub.link.link" class="bar">
          <input class="grow" readonly :value="linkUrl(hub.link.link.token)" aria-label="Ссылка на проект" @focus="e => e.target.select()">
          <wa-button size="s" appearance="outlined" @click="copyText(linkUrl(hub.link.link.token), 'Ссылка')"><Copy :size="14" /> Скопировать</wa-button>
          <wa-button size="s" :variant="armed('lrot') ? 'danger' : 'neutral'" :appearance="armed('lrot') ? 'filled' : 'outlined'" title="Выдать новую ссылку: старая перестанет работать, а вошедшие по ней потеряют доступ"
                     @click="twoStep('lrot') && setLink({ rotate: true, role: hub.link.link?.role || 'viewer' }, 'Выдана новая ссылка: старая больше не работает')">{{ armed("lrot") ? "Точно? Старая ссылка перестанет работать" : "Новая ссылка" }}</wa-button>
        </div>
        <p v-if="hub.link.users?.length" class="note">Вошли по ссылке: {{ hub.link.users.map(u => u.name || u.login).join(", ") }}</p>
        <p class="note">Ссылка работает только для тех, у кого есть учётная запись в ГРАДО 2.</p>
      </template>
      <table class="hubt">
        <thead><tr><th>Участник</th><th>Логин</th><th>Роль</th><th></th></tr></thead>
        <tbody><tr v-for="m in hub.members" :key="m.login">
          <td class="nm">{{ m.name || m.login }}<span v-if="m.login === hub.me?.login" class="pill">вы</span></td><td>{{ m.login }}</td>
          <td><select v-if="own" :value="m.role" aria-label="Роль участника" @change="e => setMember(m.login, e.target.value)"><option v-for="r in ['owner', 'editor', 'viewer']" :key="r" :value="r">{{ ROLE[r] }}</option></select><template v-else>{{ ROLE[m.role] || m.role }}</template></td>
          <td class="acts"><wa-button v-if="own" size="s" :appearance="armed('rm:' + m.login) ? 'filled' : 'plain'" :variant="armed('rm:' + m.login) ? 'danger' : 'neutral'"
              :title="armed('rm:' + m.login) ? 'Нажмите ещё раз, чтобы убрать участника' : 'Убрать из проекта'" @click="twoStep('rm:' + m.login) && setMember(m.login, null)"><X :size="14" />{{ armed("rm:" + m.login) ? " Точно?" : "" }}</wa-button></td>
        </tr></tbody>
      </table>
      <template v-if="own">
        <div class="bar"><input v-model="addLogin" class="grow" placeholder="Логин человека" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Логин человека" @keydown.enter="addMember">
          <select v-model="addRole" aria-label="Роль"><option value="editor">{{ ROLE.editor }}</option><option value="viewer">{{ ROLE.viewer }}</option></select>
          <wa-button size="s" variant="brand" @click="addMember"><UserPlus :size="14" /> Добавить</wa-button></div>
        <p class="note">Человек должен быть зарегистрирован в ГРАДО 2. Нет учётной записи — попросите администратора выдать приглашение.</p>
      </template>
      <p class="note"><b>Владелец</b> — управляет доступом, может удалить проект. <b>Правка</b> — рисует и меняет проект. <b>Просмотр</b> — смотрит проект и оставляет комментарии.</p>
    </template>
  </wa-dialog>

  <!-- ======== команды ======== -->
  <wa-dialog class="hubwin" label="Команды" :open="hub.win === 'teams'" @wa-after-hide="close('teams')">
    <div class="bar"><input v-model="teamNew" class="grow" maxlength="60" placeholder="Название новой команды" aria-label="Название новой команды" @keydown.enter="createTeam">
      <wa-button size="s" variant="brand" @click="createTeam">Создать команду</wa-button></div>
    <p v-if="!hub.teams" class="empty">Загружаю…</p>
    <p v-else-if="!hub.teams.length" class="empty">Вы пока не состоите ни в одной команде. Введите название и нажмите «Создать команду».</p>
    <template v-for="t in hub.teams || []" :key="t.id">
      <div class="sec">
        <input v-if="tren === t.id" v-focus class="ren" :value="t.name" maxlength="60" aria-label="Новое название команды"
               @keydown.enter="e => { const n = e.target.value.trim(); tren = null; if (n) teamAct(tp(t.id), { name: n }, 'Команда переименована', 'Не переименована'); }" @keydown.esc.stop="tren = null" @blur="tren = null">
        <template v-else>{{ t.name }}</template>
        <wa-button v-if="mgr(t) && tren !== t.id" size="s" appearance="plain" @click="tren = t.id">Переименовать</wa-button>
      </div>
      <p class="note">{{ +t.projects ? `Проектов в команде: ${t.projects}.` : "Проектов в команде пока нет." }}</p>
      <table class="hubt">
        <thead><tr><th>Участник</th><th>Логин</th><th>Роль</th><th></th></tr></thead>
        <tbody><tr v-for="m in t.members" :key="m.login">
          <td class="nm">{{ m.name || m.login }}<span v-if="m.login === hub.me?.login" class="pill">вы</span></td><td>{{ m.login }}</td>
          <td><select v-if="mgr(t)" :value="m.role" aria-label="Роль в команде" @change="e => teamAct(tp(t.id, '/members'), { login: m.login, role: e.target.value }, 'Роль в команде изменена', 'Роль не изменена')">
            <option v-for="r in ['owner', 'member']" :key="r" :value="r">{{ TROLE[r] }}</option></select><template v-else>{{ TROLE[m.role] || m.role }}</template></td>
          <td class="acts"><wa-button v-if="mgr(t)" size="s" :appearance="armed(`trm:${t.id}:${m.login}`) ? 'filled' : 'plain'" :variant="armed(`trm:${t.id}:${m.login}`) ? 'danger' : 'neutral'"
              @click="twoStep(`trm:${t.id}:${m.login}`) && teamAct(tp(t.id, '/members'), { login: m.login, role: null }, 'Человек убран из команды', 'Не убран')"><X :size="14" />{{ armed(`trm:${t.id}:${m.login}`) ? " Точно?" : "" }}</wa-button></td>
        </tr></tbody>
      </table>
      <div v-if="mgr(t)" class="bar"><input v-model="tadd[t.id]" class="grow" placeholder="Логин человека" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Логин человека"
        @keydown.enter="addToTeam(t)"><wa-button size="s" variant="brand" @click="addToTeam(t)"><UserPlus :size="14" /> Добавить по логину</wa-button></div>
      <div class="bar">
        <wa-button v-if="t.members.some(m => m.login === hub.me?.login)" size="s" :variant="armed('tleave:' + t.id) ? 'danger' : 'neutral'" :appearance="armed('tleave:' + t.id) ? 'filled' : 'outlined'"
                   @click="twoStep('tleave:' + t.id) && teamAct(tp(t.id, '/members'), { login: hub.me.login, role: null }, 'Вы вышли из команды', 'Не удалось выйти')">{{ armed("tleave:" + t.id) ? "Точно выйти?" : "Выйти из команды" }}</wa-button>
        <wa-button v-if="mgr(t)" size="s" :variant="armed('tdel:' + t.id) ? 'danger' : 'neutral'" :appearance="armed('tdel:' + t.id) ? 'filled' : 'outlined'" title="Удалить можно только команду без проектов"
                   @click="twoStep('tdel:' + t.id) && teamAct(tp(t.id, '/delete'), {}, 'Команда удалена', 'Команда не удалена')">{{ armed("tdel:" + t.id) ? "Точно удалить?" : "Удалить команду" }}</wa-button>
      </div>
    </template>
  </wa-dialog>

  <!-- ======== история ======== -->
  <wa-dialog class="hubwin wide" label="История проекта" :open="hub.win === 'history'" @wa-after-hide="close('history')">
    <div class="tabs" role="tablist">
      <button role="tab" :aria-selected="htab === 'ver'" @click="htab = 'ver'">Версии</button>
      <button role="tab" :aria-selected="htab === 'act'" @click="htab = 'act'">Кто что делал</button>
    </div>
    <p v-if="!hub.pid" class="empty">Сначала откройте проект.</p>
    <p v-else-if="!hub.hist" class="empty">Загружаю…</p>
    <template v-else-if="htab === 'ver'">
      <p class="note">Версия сохраняется не чаще раза в 10 минут и перед каждым возвратом. Возврат не стирает историю: текущая работа тоже остаётся в списке.{{ canEdit(myRole()) ? "" : " Вернуть версию могут владелец и редакторы." }}</p>
      <table v-if="vers.length" class="hubt"><thead><tr><th>№</th><th>Когда</th><th>Кто</th><th>Размер</th><th></th></tr></thead>
        <tbody><tr v-for="v in vers" :key="v.rev"><td class="num">{{ v.rev }}</td><td>{{ when(v.t) }}</td><td>{{ uname(v.login) }}</td><td class="num">{{ v.size ? size(v.size) : "—" }}</td>
          <td class="acts"><wa-button v-if="canEdit(myRole())" size="s" :variant="armed('rs:' + v.rev) ? 'danger' : 'neutral'" :appearance="armed('rs:' + v.rev) ? 'filled' : 'outlined'"
            @click="twoStep('rs:' + v.rev) && restore(v.rev)">{{ armed("rs:" + v.rev) ? "Точно вернуть?" : "Вернуть эту версию" }}</wa-button></td></tr></tbody></table>
      <p v-else class="empty">Сохранённых версий пока нет: первая появится через несколько минут работы.</p>
    </template>
    <template v-else>
      <table v-if="acts.length" class="hubt"><thead><tr><th>Когда</th><th>Кто</th><th>Что сделал</th></tr></thead>
        <tbody><tr v-for="(a, i) in acts" :key="i"><td>{{ when(a.t) }}</td><td>{{ uname(a.login) }}</td><td class="nm" :title="a.detail">{{ ACT[a.action] || a.action }}<span v-if="a.detail" class="sub">{{ a.detail }}</span></td></tr></tbody></table>
      <p v-else class="empty">Записей пока нет.</p>
    </template>
  </wa-dialog>

  <!-- ======== пользователи и приглашения ======== -->
  <wa-dialog class="hubwin wide" label="Пользователи и приглашения" :open="hub.win === 'admin'" @wa-after-hide="close('admin')">
    <p v-if="!hub.adm" class="empty">Загружаю…</p>
    <template v-else>
      <div class="bar"><wa-button size="s" variant="brand" @click="newInvite"><UserPlus :size="14" /> Создать приглашение</wa-button></div>
      <template v-if="hub.newCode">
        <div class="bar"><code class="code">{{ hub.newCode }}</code><wa-button size="s" appearance="outlined" @click="copyText(hub.newCode, 'Код')"><Copy :size="14" /> Скопировать</wa-button></div>
        <p class="note">Передайте код человеку: он вводит его на странице входа, вкладка «Регистрация по приглашению». Код одноразовый.</p>
      </template>
      <div class="sec">Приглашения</div>
      <table v-if="hub.adm.inv.length" class="hubt"><thead><tr><th>Код</th><th>Создано</th><th>Кем</th><th>Использовано</th></tr></thead>
        <tbody><tr v-for="i in invs" :key="i.code"><td><code>{{ i.code }}</code></td><td>{{ when(i.created) }}</td><td>{{ uname(i.by) }}</td>
          <td>{{ i.used_by ? uname(i.used_by) : "ещё нет" }}<span v-if="i.used_by" class="sub">{{ when(i.used_at) }}</span></td></tr></tbody></table>
      <p v-else class="note">Приглашений пока нет.</p>
      <div class="sec">Пользователи</div>
      <table class="hubt"><thead><tr><th>Имя</th><th>Логин</th><th>Статус</th><th></th></tr></thead>
        <tbody><tr v-for="u in hub.adm.users" :key="u.login"><td class="nm">{{ u.name || u.login }}<span v-if="u.admin" class="pill">админ</span></td><td>{{ u.login }}</td>
          <td :class="{ bad: u.disabled }">{{ u.disabled ? "отключён" : "работает" }}</td>
          <td class="acts"><wa-button v-if="u.login !== hub.me?.login" size="s" appearance="outlined" @click="toggleUser(u)">{{ u.disabled ? "Включить" : "Отключить" }}</wa-button></td></tr></tbody></table>
    </template>
  </wa-dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { Copy, UserPlus, X } from "@lucide/vue";
import ProjectCard from "./ProjectCard.vue";
import {
  ACT, LINKR, ROLE, TACC, TROLE, canEdit, copyProject, createProject, deleteProject, downloadShared, hub, isOwner, linkUrl, myRole, myTeam, newInvite, openProject,
  plural, projGroups, renameProject, restore, setLink, setMember, setPref, setTeam, shareLocal, size, starProject, teamAct, toMs, toggleUser, tp, uname, when,
} from "../hub.js";
import { notice } from "../project.js";

const vFocus = { mounted: el => { el.focus(); el.select?.(); } };
const close = w => { if (hub.win === w) hub.win = ""; };

/* двухшаговое подтверждение: первое нажатие взводит кнопку на 4 с, второе выполняет */
const arm = ref(null);
const armed = k => arm.value?.k === k && Date.now() - arm.value.t < 4000;
function twoStep(k) { if (armed(k)) { arm.value = null; return true; } arm.value = { k, t: Date.now() }; setTimeout(() => { if (arm.value?.k === k) arm.value = null; }, 4000); return false; }
async function copyText(t, what) {
  let ok = false; try { await navigator.clipboard.writeText(t); ok = true; } catch { /* нет доступа к буферу */ }
  notice.value = ok ? `${what} скопирован${what === "Ссылка" ? "а" : ""}` : `${what}: выделите и скопируйте (Ctrl+C)`;
}

/* ---- проекты ---- */
const groups = computed(() => projGroups());
const newName = ref(""), newTeam = ref(""), ren = ref(null), fileIn = ref(null), cp = reactive({ id: null, name: "", team: "" });
async function create() {
  const name = newName.value.trim(); if (!name) { notice.value = "Введите название проекта"; return; }
  if (await createProject({ name, ...(newTeam.value ? { team: newTeam.value } : {}) })) newName.value = "";
}
async function share() {
  const name = newName.value.trim(); if (!name) { notice.value = "Введите название: под ним текущая работа станет общим проектом"; return; }
  if (await shareLocal(name, newTeam.value)) newName.value = "";
}
async function onFile(e) {
  const f = e.target.files[0]; e.target.value = ""; if (!f) return;
  try {
    const p = JSON.parse(await f.text()); if (p.format && p.format !== "grado2") throw new Error("это не проект ГРАДО 2");
    const name = (newName.value.trim() || p.name || f.name.replace(/\.(grado2|json)$/i, "")).slice(0, 60);
    if (await createProject({ name, project: p, ...(newTeam.value ? { team: newTeam.value } : {}) }, `Файл «${f.name}» загружен как общий проект`)) newName.value = "";
  } catch (err) { notice.value = "Файл не загружен: " + err.message; }
}
const delAsk = ref(null);
/* превью общего проекта (server.py hub_get «preview»): адрес меняется с ревизией — картинка перерисовывается после правок */
const previewOf = p => `/api/hub/project/${encodeURIComponent(p.id)}/preview?rev=${p.rev}`;
function act(a, p, g) {
  if (a === "open") openProject(p.id, p.name);
  else if (a === "ren") ren.value = g.title + p.id;
  else if (a === "copy") startCopy(p);
  else if (a === "down") downloadShared(p);
  else if (a === "del") delAsk.value = p;
}
function startCopy(p) { Object.assign(cp, { id: p.id, name: `${p.name} — копия`.slice(0, 60), team: myTeam(p.team) ? p.team : "" }); }
async function doCopy() { const name = cp.name.trim().slice(0, 60); if (!name) return; if (await copyProject(cp.id, name, cp.team)) cp.id = null; }

/* ---- доступ ---- */
const own = computed(() => isOwner(myRole()));
const pr = computed(() => hub.projects.find(x => x.id === hub.pid) || {});
const addLogin = ref(""), addRole = ref("editor");
async function addMember() { const l = addLogin.value.trim().toLowerCase(); if (!l) return; await setMember(l, addRole.value); addLogin.value = ""; }

/* ---- команды ---- */
const teamNew = ref(""), tren = ref(null), tadd = reactive({});
const mgr = t => t.role === "owner" || t.role === "admin";
function createTeam() { const name = teamNew.value.trim(); if (!name) { notice.value = "Введите название команды"; return; } teamNew.value = ""; teamAct("teams", { name }, `Создана команда «${name}»`, "Команда не создана"); }
function addToTeam(t) { const l = (tadd[t.id] || "").trim().toLowerCase(); if (!l) return; tadd[t.id] = ""; teamAct(tp(t.id, "/members"), { login: l, role: "member" }, `Человек «${l}» добавлен в команду`, "Не добавлен"); }

/* ---- история и администрирование ---- */
const htab = ref("ver");
const vers = computed(() => [...(hub.hist?.ver || [])].sort((a, b) => b.rev - a.rev));
const acts = computed(() => [...(hub.hist?.act || [])].sort((a, b) => toMs(b.t) - toMs(a.t)));
const invs = computed(() => [...(hub.adm?.inv || [])].sort((x, y) => toMs(y.created) - toMs(x.created)));
</script>

<style>
.hubwin::part(dialog) { width: min(640px, 94vw); }
.hubwin.wide::part(dialog) { width: min(1120px, 96vw); }
.hubwin .pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.hubwin .pgroup + .pgroup { margin-top: 10px; }
.hubwin h4.sec { color: var(--g-muted); font-size: var(--wa-font-size-xs); text-transform: uppercase; letter-spacing: .04em; font-weight: 600; margin: 10px 0 8px; }
.hubwin .bar.copy { margin-top: 10px; }
.hubwin .pcard b.on { color: var(--wa-color-success-on-quiet, #2f9e44); font-weight: 600; }
.hubwin { font-size: var(--wa-font-size-s); }
.hubwin .bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 4px 0 8px; }
.hubwin .bar .grow { flex: 1 1 200px; }
.hubwin input, .hubwin select { font: inherit; padding: 4px 7px; border: 1px solid var(--g-line); border-radius: 5px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
.hubwin .dim { color: var(--g-muted); display: inline-flex; gap: 5px; align-items: center; }
.hubwin .empty, .hubwin .note { color: var(--g-muted); margin: 6px 0; }
.hubwin .sec { font-weight: 600; margin: 12px 0 4px; display: flex; gap: 8px; align-items: center; }
.hubwin td.sec { color: var(--g-muted); font-size: var(--wa-font-size-xs); text-transform: uppercase; letter-spacing: .04em; padding-top: 10px; }
.hubt { width: 100%; border-collapse: collapse; margin: 4px 0; }
.hubt th { text-align: left; font-weight: 600; color: var(--g-muted); font-size: var(--wa-font-size-xs); border-bottom: 1px solid var(--g-line); padding: 3px 6px; }
.hubt td { padding: 3px 6px; border-bottom: 1px solid var(--g-line); vertical-align: middle; }
.hubt tr.cur td { background: color-mix(in srgb, var(--wa-color-brand-fill-loud) 8%, transparent); }
.hubt .nm { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hubt .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.hubt .acts { text-align: right; white-space: nowrap; }
.hubt .sub { display: block; color: var(--g-muted); font-size: var(--wa-font-size-2xs); }
.hubt .bad { color: var(--wa-color-danger-on-quiet); }
.hubwin .pill { font-size: var(--wa-font-size-2xs); padding: 0 6px; margin-left: 6px; border-radius: 8px; background: var(--wa-color-neutral-fill-quiet); color: var(--g-muted); }
.hubwin .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--g-line); margin-bottom: 6px; }
.hubwin .tabs button { border: 0; background: none; padding: 5px 2px; font: inherit; color: var(--g-muted); cursor: pointer; border-bottom: 2px solid transparent; }
.hubwin .tabs button[aria-selected=true] { color: var(--wa-color-text-normal); border-bottom-color: var(--wa-color-brand-fill-loud); }
.hubwin .code { font-size: 15px; padding: 3px 8px; background: var(--wa-color-neutral-fill-quiet); border-radius: 4px; }
.hubwin wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
</style>
