<!-- ГРАДО 2 · вкладка «Листы и альбом» нового интерфейса. Сверху — листы проекта, те же, что в «Макете листа» (project.layouts):
     «Новый лист» — пустой лист, как там (без заготовок по формату), щелчок по листу открывает его в «Макете листа»
     (store.js sheetNav), «PDF» — все эти листы одним файлом (sheetmaps.js printAll). Карта листа — рамка вида на карте.
     Ниже, в раскрывающемся разделе, — альбом ППТ КРТ (шаг 2 плана, #94) без отдельного окна браузера.
     В нём строка альбома и действия («Собрать», PDF, PPTX), ход сборки и выгрузки («PDF: лист 3 из 9 · 12 с», «Остановить»),
     вопросы «заменить или добавить» и «не всё готово»; ниже штамп, список листов и свойства выбранного листа с просмотром.
     Сборку и печать делает прежний движок альбома, скрытый в странице (albumhost.js call, web/albumapi.js), поэтому PDF и
     PPTX выходят лист в лист прежние. Простые правки (название, формат, масштаб, легенда, ТЭП, порядок, удаление, штамп)
     пишутся прямо в раздел album проекта. Пока вкладка на виду, рамки листов видны на карте вместе с рамками видов (viewframesmap.js): щелчок выбирает
     лист здесь, рамку тянут и меняют угол там же. «Слои листа» — роли выбранного листа с глазом (sheetlayers.js rows).
     Перетаскивание роли или слоя проекта на лист, очередь источников, фото, спутник, импорт из файла, содержание листа,
     масштаб схем и формат слайдов — здесь же (прежнего окна «Подробно» больше нет). -->
<template>
  <div class="pane alb">
    <!-- листы проекта — те же, что в «Макете листа»: одна логика везде (владелец 12.10.2026) -->
    <div class="ahead">
      <p class="stat">{{ ownHead }}</p>
      <div class="acts">
        <wa-button size="s" variant="brand" :disabled="viewer" data-act="new" title="Пустой лист, как в «Макете листа»: на нём ставите рамку карты и выбираете ей вид — рамку, нарисованную на карте в окне «Виды»" @click="addOwn"><FilePlus2 :size="14" /> Новый лист</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="!own.length || ownBusy" :loading="ownBusy" title="Все листы проекта по порядку одним PDF" @click="ownPdf"><FileDown :size="14" /> PDF</wa-button>
      </div>
    </div>
    <p v-if="!own.length" class="empty">Листов пока нет. «Новый лист» — пустой лист, как в «Макете листа»: на нём рисуют рамку карты и выбирают ей вид. Вид — это слои и рамка на карте, её рисуют в окне «Виды» и тянут на нужную территорию.</p>
    <ol v-else class="list" aria-label="Листы проекта">
      <li v-for="(s, i) in own" :key="s.id" :title="'Открыть в «Макете листа»: ' + (s.title || 'без названия')" tabindex="0" @click="openOwn(s.id)" @keydown.enter="openOwn(s.id)">
        <span class="n">{{ i + 1 }}</span>
        <span class="t">{{ s.title || "без названия" }}</span>
        <span class="f">{{ s.format || "A3" }}{{ s.orient === "P" ? " стоя" : "" }}<template v-if="mapsOn(s)"> · {{ mapsOn(s) }}</template></span>
        <span></span>
      </li>
    </ol>

    <!-- альбом ППТ КРТ: состав листов задан правилами ППТ КРТ (docs/wiki/album-rules.md), собирается и печатается прежним движком -->
    <wa-details class="stamp albsec" :open="albOpen" @wa-show.self="albOpen = true" @wa-hide.self="albOpen = false">
    <span slot="summary"><b>Альбом ППТ КРТ</b> <span class="sum" :title="st?.stat">{{ head }}</span></span>
    <div class="ahead">
      <div class="acts">
        <wa-dropdown @wa-select="e => build(e.detail.item.value)">
          <wa-button slot="trigger" size="s" appearance="outlined" with-caret :disabled="busy || viewer"><LayoutTemplate :size="14" /> Собрать</wa-button>
          <wa-dropdown-item value="pptkrt">Альбом ППТ КРТ<span slot="details">А3, красная шапка</span></wa-dropdown-item>
          <wa-dropdown-item value="sit">Ситуационный план A4<span slot="details">один лист</span></wa-dropdown-item>
          <wa-dropdown-item value="sec1">Раздел 1: существующее положение<span slot="details">слайды</span></wa-dropdown-item>
          <wa-divider></wa-divider>
          <wa-dropdown-item value="refresh" :disabled="!sheets.length">Обновить листы<span slot="details">по шаблону</span></wa-dropdown-item>
          <wa-dropdown-item value="file">Из файла…<span slot="details">проект .grado2 или готовая вёрстка</span></wa-dropdown-item>
        </wa-dropdown>
        <input ref="impFile" type="file" accept=".grado2,.json,application/json" hidden @change="importFile" />
        <wa-button size="s" variant="brand" :disabled="busy || !sheets.length" title="Все листы одним PDF: рамка, штамп, масштаб, легенда" @click="file('pdf')"><FileDown :size="14" /> PDF</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="busy || !sheets.length" title="Все листы редактируемой презентацией PowerPoint: подписи — текстом, карты — фигурами по слоям" @click="file('pptx')"><Presentation :size="14" /> PPTX</wa-button>
      </div>
    </div>

    <!-- ход сборки или выгрузки: что идёт и сколько секунд; «Остановить» — после текущего листа -->
    <div v-if="st?.bp" class="job" role="status" aria-live="polite">
      <wa-spinner></wa-spinner><span class="jt">{{ st.bp.text }}</span><span class="t">{{ st.bp.secs }} с</span>
      <wa-button v-if="st.bp.canStop" size="s" appearance="outlined" :disabled="st.bp.stop" title="Уже собранные листы останутся" @click="act(a => a.stop())">{{ st.bp.stop ? "Остановлю после листа…" : "Остановить" }}</wa-button>
    </div>
    <div v-else-if="!engineReady" class="job quiet" role="status"><wa-spinner></wa-spinner><span class="jt">Готовлю сборку альбома…</span></div>

    <!-- вопрос движка: набор собирается поверх других листов -->
    <div v-if="st?.ask" class="ask" role="alertdialog" aria-label="Заменить или добавить листы">
      <p>«{{ st.ask.name }}»: {{ st.ask.n }} л. В альбоме уже есть другие листы ({{ st.ask.have }}).</p>
      <div class="row">
        <wa-button size="s" variant="brand" @click="act(a => a.answer('replace'))">Заменить листы альбома</wa-button>
        <wa-button size="s" appearance="outlined" @click="act(a => a.answer('add'))">Добавить после текущих</wa-button>
        <wa-button size="s" appearance="plain" @click="act(a => a.answer('cancel'))">Отмена</wa-button>
      </div>
    </div>
    <!-- листы из файла: заменить или добавить; большой файл — сначала «всё равно взять?» -->
    <div v-if="st?.imp" class="ask" role="alertdialog" aria-label="Листы из файла">
      <template v-if="st.imp.big">
        <p>Файл «{{ st.imp.name }}» — {{ st.imp.mb }} МБ: проект станет большим, сохранение и совместная работа — медленнее.</p>
        <div class="row">
          <wa-button size="s" variant="brand" @click="act(a => a.importAnswer('go'))">Всё равно взять листы</wa-button>
          <wa-button size="s" appearance="plain" @click="act(a => a.importAnswer('cancel'))">Отмена</wa-button>
        </div>
      </template>
      <template v-else>
        <p>«{{ st.imp.name }}»: {{ st.imp.n }} л. В альбоме уже есть листы ({{ st.imp.have }}).</p>
        <div class="row">
          <wa-button size="s" variant="brand" @click="act(a => a.importAnswer('replace'))">Заменить листы альбома</wa-button>
          <wa-button size="s" appearance="outlined" @click="act(a => a.importAnswer('add'))">Добавить после текущих</wa-button>
          <wa-button size="s" appearance="plain" @click="act(a => a.importAnswer('cancel'))">Отмена</wa-button>
        </div>
      </template>
    </div>
    <div v-if="legacy" class="ask" role="alertdialog" aria-label="Обновить старые листы">
      <p>Обновить {{ legacy }} {{ word(legacy, "старый лист", "старых листа", "старых листов") }} по шаблону? Ваши названия, рамки и фото сохранятся, набор слоёв и легенда станут как в шаблоне.</p>
      <div class="row">
        <wa-button size="s" variant="brand" @click="refresh(true)">Обновить и старые</wa-button>
        <wa-button size="s" appearance="outlined" @click="refresh(false)">Только листы по шаблону</wa-button>
        <wa-button size="s" appearance="plain" @click="legacy = 0">Отмена</wa-button>
      </div>
    </div>
    <!-- перед выгрузкой: что не готово; щелчок по строке выбирает лист или открывает штамп -->
    <div v-if="issues" class="ask warn" role="alertdialog" aria-label="Не всё готово к выгрузке">
      <p><b>{{ issues.kind === "pdf" ? "PDF" : "PPTX" }}{{ issues.i != null ? " листа" : "" }}: не всё готово</b></p>
      <ul><li v-for="(l, k) in issues.lines.slice(0, 8)" :key="k"><button class="lnk" type="button" @click="jump(l)">{{ l.text }}</button></li>
        <li v-if="issues.lines.length > 8">и ещё {{ issues.lines.length - 8 }}</li></ul>
      <div class="row">
        <wa-button size="s" variant="brand" @click="go">Выгрузить всё равно</wa-button>
        <wa-button size="s" appearance="plain" @click="issues = null">Отмена</wa-button>
      </div>
    </div>

    <wa-details class="stamp" :open="stampOpen" @wa-show.self="stampOpen = true" @wa-hide.self="stampOpen = false">
      <span slot="summary"><b>Штамп</b> <span class="sum">{{ stampSum }}</span></span>
      <div class="fields">
        <wa-input v-for="f in META" :key="f[0]" size="s" :label="f[1]" :value="meta[f[0]] || ''" :readonly="viewer" :data-meta="f[0]"
                  @change="e => setMeta(f[0], e.target.value)"></wa-input>
      </div>
      <wa-button size="s" appearance="outlined" :disabled="viewer || busy" title="Заполнить пустые поля «№ КРТ», «Округ, район» и «Адрес» по загруженным слоям; введённое вами не меняется" @click="fill"><WandSparkles :size="14" /> Заполнить по слоям</wa-button>
    </wa-details>

    <!-- настройки альбома (#89): цвет воды на белых схемах и шрифт подписей карт; пусто — как печаталось до настройки -->
    <wa-details class="stamp look" :open="lookOpen" @wa-show.self="lookOpen = true" @wa-hide.self="lookOpen = false">
      <span slot="summary"><b>Оформление карт</b> <span class="sum">{{ lookSum }}</span></span>
      <div class="lookrow">
        <wa-color-picker size="s" aria-label="Цвет воды на белых схемах" :value="meta.waterColor || WATER" :disabled="viewer" data-look="water"
                         @change="e => setLook('waterColor', e.target.value)"></wa-color-picker>
        <span class="lbl">Вода на белых схемах<small>сущпол и Генплан — своим цветом</small></span>
        <wa-button v-if="meta.waterColor && meta.waterColor !== WATER" size="s" appearance="plain" :disabled="viewer" title="Голубой #bfe0f5, как по умолчанию" @click="setLook('waterColor', '')">Как было</wa-button>
      </div>
      <FontPicker label="Шрифт подписей карт" :value="meta.labelFont || 'base'" :name="meta.labelFontName" :presets="FONTS" :disabled="viewer" data-look="font"
                  @change="setFont"></FontPicker>
      <p class="hint">Заголовки и надписи листа — всегда Montserrat. Новые цвет и шрифт попадут в просмотр, PDF и PPTX.</p>
      <div class="g2">
        <wa-select size="s" label="Масштаб схем 5–9" :value="String(st?.scheme ?? 0)" :disabled="viewer" data-look="scheme"
                   title="Один масштаб для схем альбома ППТ КРТ — листов 5–9. «Авто» — по размеру территории; «по границам выгрузки» — рамка не меньше области загрузки данных и сит. плана. Масштаб, выбранный в свойствах листа, главнее"
                   @change="e => setScheme(e.target.value)">
          <wa-option value="0">авто по территории</wa-option>
          <wa-option value="cover">по границам выгрузки</wa-option>
          <wa-option v-for="v in st?.schemeScales || []" :key="v" :value="String(v)">1:{{ v.toLocaleString("ru-RU") }}</wa-option>
        </wa-select>
        <wa-select size="s" label="Формат слайдов раздела" :value="st?.slide || 'P'" :disabled="viewer" data-look="slide" title="Формат слайдов раздела 1: меняет и уже собранные слайды"
                   @change="e => act(a => a.setSlide(e.target.value))">
          <wa-option v-for="sl in st?.slides || []" :key="sl[0]" :value="sl[0]">{{ sl[1] }}</wa-option>
        </wa-select>
      </div>
    </wa-details>

    <p v-if="!sheets.length" class="empty">В альбоме листов нет. «Собрать» → «Альбом ППТ КРТ» соберёт листы по правилам ППТ КРТ: титул, месторасположение, ортофотоплан, сущпол, документация, ПЗЗ, Генплан.</p>
    <ol v-else class="list" role="listbox" aria-label="Листы альбома" @keydown="keys">
      <li v-for="(s, i) in sheets" :key="s.id" role="option" :aria-selected="i === cur" :tabindex="i === cur ? 0 : -1"
          :class="{ on: i === cur, bad: !!why(s), ['drop-' + (dnd.at === i ? dnd.tone || 'wait' : '')]: dnd.at === i }"
          :title="(s.title || 'без названия') + (why(s) ? ' — не готов: ' + why(s) : '')" @click="pick(i)"
          @dragover="e => dragOver(e, i)" @dragleave="e => dragLeave(e, i)" @drop="e => dropOn(e, i)">
        <span class="n">{{ i + 1 }}</span>
        <span class="t">{{ s.title || "без названия" }}</span>
        <span class="f">{{ row(s).size }}<template v-if="row(s).scale"> · {{ row(s).scale }}</template></span>
        <CircleAlert v-if="why(s)" :size="14" class="nr" aria-label="не готов" />
        <span v-if="dnd.at === i && dnd.text" class="dcap" :class="dnd.tone">{{ dnd.text }}</span>
      </li>
    </ol>
    <p v-if="dnd.what" class="hint dfoot" aria-live="polite"><b>Перетаскивание:</b> {{ dnd.what.type === "role" ? `роль «${dnd.what.title}» — на другой лист: перенос, с Alt — копия` : `слой «${dnd.what.title}» — на лист или строку роли: включить там` }}</p>

    <section v-if="sel" class="det" :aria-label="'Лист ' + (cur + 1)">
      <wa-input size="s" label="Название" :value="sel.title || ''" :readonly="viewer" @change="e => setSheet('title', e.target.value)"></wa-input>
      <div class="g2">
        <wa-select size="s" label="Формат" :value="sel.size" :disabled="viewer || row(sel).frozen" @change="e => setSheet('size', e.target.value)">
          <wa-option v-for="(t, k) in sizes" :key="k" :value="k">{{ t }}</wa-option>
        </wa-select>
        <wa-select size="s" label="Масштаб" :value="String(sel.scale || 0)" :disabled="viewer || row(sel).noScale" @change="e => setSheet('scale', +e.target.value)">
          <wa-option value="0">авто{{ row(sel).auto && row(sel).scale ? " (" + row(sel).scale + ")" : "" }}</wa-option>
          <wa-option v-if="sel.scale && !scales.includes(sel.scale)" :value="String(sel.scale)">1:{{ sel.scale.toLocaleString("ru-RU") }} (рамка на карте)</wa-option>
          <wa-option v-for="v in scales" :key="v" :value="String(v)">1:{{ v.toLocaleString("ru-RU") }}</wa-option>
        </wa-select>
      </div>
      <!-- содержание своего листа: текущая карта, сохранённый вид или таблица ТЭП (у листов по шаблону — слои шаблона) -->
      <wa-select v-if="ownMap" size="s" label="Содержание" :value="sel.kind === 'tep' ? '__tep' : sel.view || ''" :disabled="viewer" data-sheet="view"
                 @change="e => act(a => a.setView(cur, e.target.value))">
        <wa-option value="">текущая карта</wa-option>
        <wa-option v-for="v in st?.views || []" :key="v.id" :value="v.id">вид «{{ v.name }}»</wa-option>
        <wa-option value="__tep">таблица ТЭП (все показатели)</wa-option>
      </wa-select>
      <div class="flags">
        <wa-checkbox size="s" :checked="!!sel.legend" :disabled="viewer || sel.kind === 'tep' || row(sel).frozen" @change="e => setSheet('legend', e.target.checked)">Легенда</wa-checkbox>
        <wa-checkbox size="s" :checked="!!sel.tep" :disabled="viewer || sel.kind === 'tep' || row(sel).frozen" @change="e => setSheet('tep', e.target.checked)">Таблица ТЭП</wa-checkbox>
      </div>
      <p v-if="why(sel)" class="nrw"><b>Не готов:</b> {{ why(sel) }}</p>
      <p v-if="row(sel).frozen" class="hint">Готовая вёрстка из файла: слои и оформление записаны в самом листе.</p>
      <p v-else-if="row(sel).tpl" class="hint">Лист по шаблону: слои и оформление — из шаблона; рамку на карте можно сдвинуть, за угол — сменить масштаб.</p>
      <div class="row">
        <wa-button size="s" appearance="outlined" :disabled="busy" @click="preview"><Eye :size="14" /> Просмотр</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="busy" title="PDF только этого листа" @click="file('pdf', cur)"><FileDown :size="14" /> PDF листа</wa-button>
        <wa-button v-if="sel.kind !== 'tep'" size="s" appearance="outlined" data-act="lay" title="Двигать, выравнивать и править надписи листа — окно «Макет надписей»" @click="openLay"><Type :size="14" /> Надписи</wa-button>
        <wa-button v-if="sel.center && sel.kind !== 'tep'" size="s" appearance="outlined" :disabled="viewer" title="Лист сдвинут: вернуть его в центр территории" @click="act(a => a.resetCenter(cur))"><LocateFixed :size="14" /> В центр</wa-button>
        <wa-button v-if="canSat" size="s" appearance="outlined" data-act="sat" :disabled="busy || sat.busy" :loading="sat.busy"
                   title="Спутник Яндекса по рамке листа — архив для AutoCAD в МСК (DXF и снимок), только для работы" @click="askSat"><Satellite :size="14" /> Спутник</wa-button>
        <wa-button size="s" appearance="plain" :disabled="viewer || cur === 0" title="Выше" aria-label="Выше" @click="up"><ArrowUp :size="14" /></wa-button>
        <wa-button size="s" appearance="plain" :disabled="viewer" title="Удалить лист" aria-label="Удалить лист" @click="askDrop = true"><Trash2 :size="14" /></wa-button>
      </div>
      <p v-if="sat.text" class="hint" aria-live="polite">{{ sat.text }}</p>
      <!-- фотофиксация: снимки листа «Материалы фотофиксации» — до 12, точка съёмки на карте из GPS снимка -->
      <wa-details v-if="sel.kind === 'photos'" class="stamp lay photos" open>
        <span slot="summary"><b>Снимки</b> <span class="sum">{{ photos.length }} из 12{{ noGps ? ` · без GPS ${noGps}` : "" }}</span></span>
        <ul v-if="photos.length" class="shots" aria-label="Снимки листа">
          <li v-for="ph in photos" :key="ph.k" :title="ph.name + (ph.at ? '' : ' — без GPS: точки съёмки на карте нет')">
            <img :src="ph.src" :alt="ph.name" loading="lazy">
            <span class="nm">{{ ph.k + 1 }}<template v-if="!ph.at"> · без GPS</template></span>
            <button v-if="!viewer" type="button" class="x" :aria-label="'Убрать снимок ' + (ph.k + 1)" title="Убрать снимок" @click="dropPhoto(ph.k)"><X :size="12" /></button>
          </li>
        </ul>
        <p v-else class="hint">Снимков нет. Добавьте фотографии с телефона: точка съёмки встанет на карту листа сама, если в снимке есть GPS.</p>
        <input ref="photoFile" type="file" accept="image/*" multiple hidden @change="addPhotos" />
        <div class="row">
          <wa-button size="s" appearance="outlined" data-act="photo" :disabled="viewer || busy || photos.length >= 12" @click="photoFile.click()"><Camera :size="14" /> Добавить снимки…</wa-button>
          <wa-button v-if="photos.length" size="s" appearance="plain" :disabled="viewer" @click="askClear = true">Убрать все</wa-button>
        </div>
      </wa-details>
      <!-- слои листа (роли сверху вниз): глаз — только на этом листе; роль тянут на лист в списке, ниже — «Слои проекта» -->
      <wa-details v-if="roles && roles.kind === 'layout'" class="stamp lay" :open="layOpen" @wa-show.self="layOpen = true" @wa-hide.self="layOpen = false">
        <span slot="summary"><b>Слои листа</b> <span class="sum">{{ laySum }}</span></span>
        <ul class="roles" aria-label="Слои листа, сверху вниз">
          <li v-for="r in roles.rows" :key="r.id" :class="{ off: !r.on, ['drop-' + (dnd.row === r.role ? dnd.tone || 'wait' : '')]: dnd.row === r.role }"
              :title="'Слои: ' + r.layers.join('; ') + (roles.editable ? '. Перетащите на лист в списке выше: перенос, с Alt — копия' : '')"
              :draggable="roles.editable" @dragstart="e => dragStart(e, { type: 'role', from: cur, role: r.role, title: r.title })" @dragend="dragEnd"
              @dragover="e => dragOver(e, cur, r.role)" @dragleave="e => dragLeave(e, cur, r.role)" @drop="e => dropOn(e, cur, r.role)">
            <wa-button size="s" appearance="plain" :disabled="!roles.editable" :aria-label="(r.on ? 'Скрыть' : 'Показать') + ' «' + r.title + '» на этом листе'"
                       :title="roles.editable ? (r.on ? 'Скрыть на этом листе' : 'Показать на этом листе') : roles.why" @click="roleEye(r)">
              <Eye v-if="r.on" :size="14" /><EyeOff v-else :size="14" /></wa-button>
            <span class="rt">{{ r.title }} <small>{{ r.count }}</small>
              <button v-if="r.queue && r.queue.length > 1" type="button" class="src lnk" :aria-expanded="qOpen === r.id" title="Откуда брать: очередь источников" @click="qOpen = qOpen === r.id ? null : r.id">{{ r.source }} ▾</button>
              <small v-else class="src">{{ r.source }}</small></span>
            <span class="cov" :class="{ w: r.cover != null && r.cover < .9 }">{{ r.cover == null ? "—" : Math.round(r.cover * 100) + " %" }}</span>
            <span class="chips">
              <button v-if="r.hand" class="chip hand" type="button" :disabled="!roles.editable" :title="r.hand + (roles.editable ? '. Щелчок — вернуть как по образцу' : '')" @click="roleReset(r)">вручную</button>
              <span v-if="r.badge" class="chip" :class="r.badge.tone">{{ r.badge.text }}</span>
            </span>
            <wa-dropdown v-if="roles.editable && sheets.length > 1" class="mv" @wa-select="e => moveRole(r, e.detail.item.value)">
              <wa-button slot="trigger" size="s" appearance="plain" :aria-label="'Перенести «' + r.title + '» на другой лист'" title="Перенести или копировать на другой лист"><MoveRight :size="14" /></wa-button>
              <h3 class="mvh">Перенести на лист</h3>
              <wa-dropdown-item v-for="(s, k) in sheets" v-show="k !== cur" :key="'m' + s.id" :value="'m' + k">{{ k + 1 }}. {{ s.title || "без названия" }}</wa-dropdown-item>
              <wa-divider></wa-divider>
              <h3 class="mvh">Копия на лист</h3>
              <wa-dropdown-item v-for="(s, k) in sheets" v-show="k !== cur" :key="'c' + s.id" :value="'c' + k">{{ k + 1 }}. {{ s.title || "без названия" }}</wa-dropdown-item>
            </wa-dropdown>
            <span v-else></span>
            <!-- очередь источников роли: первый — главный, ниже — запасные; перетаскивание или стрелки -->
            <ol v-if="qOpen === r.id && r.queue" class="queue" :aria-label="'Источники «' + r.title + '», первый — главный'">
              <li v-for="(q, k) in r.queue" :key="q.key" :class="{ used: q.used, ['drop-' + (qd.over === k ? 'ok' : '')]: qd.over === k }" :draggable="roles.editable"
                  @dragstart.stop="e => qStart(e, r, k)" @dragover.stop.prevent="qd.r === r.id && (qd.over = k)" @dragleave.stop="qd.over === k && (qd.over = -1)" @drop.stop.prevent="qDrop(r, k)" @dragend.stop="qd.r = null; qd.over = -1">
                <span class="qn">{{ k + 1 }}</span>
                <span class="qt">{{ q.title }}<small v-if="q.used"> · используется</small></span>
                <span class="cov">{{ q.cover == null ? "—" : Math.round(q.cover * 100) + " %" }}</span>
                <span class="qb">
                  <wa-button size="s" appearance="plain" :disabled="!roles.editable || k === 0" :aria-label="'«' + q.title + '» выше'" title="Выше в очереди" @click="reorder(r, k, k - 1)"><ArrowUp :size="12" /></wa-button>
                  <wa-button size="s" appearance="plain" :disabled="!roles.editable || k === r.queue.length - 1" :aria-label="'«' + q.title + '» ниже'" title="Ниже в очереди" @click="reorder(r, k, k + 1)"><ArrowDown :size="12" /></wa-button>
                </span>
              </li>
            </ol>
          </li>
        </ul>
        <p v-if="!roles.editable && roles.why" class="hint">{{ roles.why }}</p>
        <p class="hint">Роль можно перетащить на лист в списке выше (с Alt — копия). У дорог щелчок по источнику открывает очередь: первый — главный.</p>
        <!-- слои проекта: перетащить на лист или строку роли — слой включится там; «+» — на этом листе -->
        <wa-details class="bank" :open="bankOpen" @wa-show.self="bankOpen = true; loadBank()" @wa-hide.self="bankOpen = false">
          <span slot="summary">Слои проекта <span class="sum">где включены</span></span>
          <template v-for="g in bank" :key="g.title">
            <p class="bkh">{{ g.title }} <small>{{ g.items.length }}</small></p>
            <ul class="bk">
              <li v-for="it in g.items" :key="it.key" :draggable="roles.editable" @dragstart="e => dragStart(e, { type: 'layer', key: it.key, title: it.title })" @dragend="dragEnd"
                  :title="roles.editable ? 'Перетащите на лист или на строку роли — слой включится там' : ''">
                <span class="bt">{{ it.title }}</span>
                <span class="bs">{{ it.sheets.length ? (it.sheets.length > 1 ? "листы " : "лист ") + it.sheets.join(", ") : "нигде" }}</span>
                <wa-button v-if="roles.editable && !it.sheets.includes(cur + 1)" size="s" appearance="plain" :aria-label="'Включить «' + it.title + '» на этом листе'" title="Включить на этом листе" @click="dropWhat(cur, { type: 'layer', key: it.key, title: it.title }, false)"><Plus :size="12" /></wa-button>
              </li>
            </ul>
          </template>
          <p v-if="!bank.length" class="hint">В проекте пока нет слоёв.</p>
        </wa-details>
      </wa-details>
      <p v-else-if="roles && roles.kind === 'map'" class="hint">Лист показывает текущую карту: состава слоёв у него нет.</p>
      <div v-if="img.url && img.id === sel.id" class="prev"><img :src="img.url" :alt="'Лист ' + (cur + 1) + ': ' + (sel.title || '')"></div>
      <p v-else-if="img.busy" class="hint">Собираю картинку листа…</p>
    </section>

    <wa-dialog label="Убрать снимки" :open="askClear" @wa-after-hide="askClear = false">
      <p>Убрать все {{ photos.length }} снимков с листа «{{ sel?.title || "без названия" }}»?</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askClear = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="askClear = false; dropPhoto(null)">Убрать</wa-button>
    </wa-dialog>
    <!-- спутник: AutoCAD видит снимок из DXF, только если путь к нему полный — папку загрузок спрашиваем один раз -->
    <wa-dialog label="Спутник Яндекса по рамке листа" :open="sat.ask" class="satdlg" @wa-after-hide="sat.ask = false">
      <p>Программа скачает снимки по рамке листа и соберёт архив для AutoCAD в МСК: DXF и снимок. Распакуйте архив двойным щелчком в папке загрузок и откройте sputnik_yandex.dxf — снимок уже на месте. Только для работы, в сдаваемые материалы не включать.</p>
      <wa-input size="s" label="Папка загрузок браузера — полный путь" :value="sat.dir" placeholder="/Users/имя/Downloads" @input="sat.dir = $event.target.value"></wa-input>
      <wa-button slot="footer" size="s" appearance="plain" @click="sat.ask = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" :disabled="!sat.dir.trim()" @click="runSat">Скачать</wa-button>
    </wa-dialog>
    <wa-dialog label="Удалить лист" :open="askDrop" @wa-after-hide="askDrop = false">
      <p>Удалить лист «{{ sel?.title || "без названия" }}» из альбома? Остальные листы останутся.</p>
      <wa-button slot="footer" size="s" appearance="plain" @click="askDrop = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="danger" @click="drop">Удалить</wa-button>
    </wa-dialog>
    </wa-details>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ArrowDown, ArrowUp, Camera, CircleAlert, Eye, EyeOff, FileDown, FilePlus2, LayoutTemplate, LocateFixed, MoveRight, Plus, Presentation, Satellite, Trash2, Type, WandSparkles, X } from "@lucide/vue";
import { album, call, engineState, startEngine, sync } from "../albumhost.js";
import { C } from "../collab.js";
import { markDirty, notice } from "../project.js";
import { project, sheetNav, winApi } from "../store.js";
import { newId, newSheet } from "../sheet/model.js";
import { printAll } from "./sheetmaps.js";
import FontPicker from "./FontPicker.vue";

const WATER = "#bfe0f5";   // вода белых схем по умолчанию (albums.js C_WATER_VIS, print_io.WATER_VIS)
/* шрифт подписей карт: base — как печаталось до настройки (подписи альбома ППТ КРТ Montserrat жирным, у прочих листов PT Sans) */
const FONTS = [["base", "Как сейчас"], ["pt-sans", "PT Sans"], ["pt-serif", "PT Serif"], ["montserrat", "Montserrat"]];   // готовые; любой другой — «Другой шрифт…» (FontPicker)
const META = [["object", "Объект"], ["code", "Шифр"], ["stage", "Стадия: ПП, П, Р"], ["org", "Организация"], ["short", "№ КРТ"], ["place", "Округ, район"], ["address", "Адрес"]];
const props = defineProps({ params: Object });
/* выбранный лист — общий с рамками на карте (viewframesmap.js) */
const cur = computed({ get: () => album.cur, set: v => { album.cur = v; } });
const st = ref(null), stampOpen = ref(false), lookOpen = ref(false), askDrop = ref(false), legacy = ref(0), issues = ref(null), ver = ref(0);
const img = reactive({ id: null, url: "", busy: false });
const roles = ref(null), layOpen = ref(true);
const viewer = computed(() => C.role === "viewer");
const engineReady = computed(() => album.ready);

/* Альбом — в project.raw (без слежения Vue): ver заставляет перечитать его после правок здесь и приёма правок движка. */
const alb = computed(() => { ver.value; album.rev; return project.raw?.album || null; });
const sheets = computed(() => alb.value?.sheets || []);
const meta = computed(() => alb.value?.meta || {});
const sel = computed(() => sheets.value[cur.value] || null);
const sizes = computed(() => st.value?.sizes || {});
const scales = computed(() => st.value?.scales || []);
const busy = computed(() => !!st.value?.busy);
const row = s => st.value?.rows?.[s.id] || { size: s.size || "", scale: "" };
const why = s => st.value?.why?.[s.id] || "";
const word = (n, a, b, c) => n % 10 === 1 && n % 100 !== 11 ? a : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? b : c;
const stampSum = computed(() => { ver.value; album.rev; const p = [meta.value.object, meta.value.code, meta.value.stage].filter(Boolean); return p.length ? p.join(" · ") : "не заполнен"; });
const lookSum = computed(() => {
  ver.value; album.rev;   // meta — тот же объект project.raw, правится на месте: перечитать после каждой правки
  const w = meta.value.waterColor && meta.value.waterColor !== WATER ? "вода " + meta.value.waterColor : "";
  const f = FONTS.find(x => x[0] === meta.value.labelFont)?.[1] || (String(meta.value.labelFont || "").startsWith("f:") ? meta.value.labelFontName || "свой шрифт" : "");
  return [w, f].filter(Boolean).join(" · ") || "как сейчас";
});
const head = computed(() => st.value?.stat || (sheets.value.length ? `Альбом: ${sheets.value.length} ${word(sheets.value.length, "лист", "листа", "листов")}` : "Альбом: листов нет"));

/* состояние движка (ход сборки, «не готов», строки листов) — раз в полсекунды, пока вкладка открыта */
let poll = 0;
let lastFrames = "";
function readState() {
  const s = engineState(); st.value = s ? JSON.parse(JSON.stringify(s)) : null;
  const f = JSON.stringify(st.value?.frames || []);
  if (f !== lastFrames) { lastFrames = f; album.frames = st.value?.frames || []; }   // рамки на карте — только когда изменились
}
/* рамки листов на карте — пока вкладка на виду */
let offVis = null;
onMounted(() => {
  startEngine(); readState(); poll = setInterval(readState, 500);
  const api = props.params?.api;
  album.tab = api ? api.isVisible : true;
  offVis = api?.onDidVisibilityChange?.(e => { album.tab = e.isVisible; });
});
onBeforeUnmount(() => { clearInterval(poll); offVis?.dispose?.(); album.tab = false; });
watch(() => sheets.value.length, n => { if (cur.value >= n) cur.value = Math.max(0, n - 1); });

/* действие движка: ошибки — в строку состояния */
async function act(fn) {
  try { return await call(fn); } catch (e) { notice.value = "Альбом: " + (e.message || e); } finally { readState(); }
}

/* правка альбома здесь: как touch() движка — время правки, проект изменён; движок получит проект перед следующим действием */
function edited() {
  const a = project.raw.album; if (a) { a.meta ||= {}; a.meta.editedAt = new Date().toISOString(); }
  markDirty(); ver.value++; sync();
}
function ensure() { project.raw.album ||= { meta: { object: "", code: "", stage: "ПП", org: "" }, sheets: [] }; return project.raw.album; }
function setMeta(k, v) { const a = ensure(); a.meta[k] = v; if (a.meta.auto) delete a.meta.auto[k]; edited(); }
/* настройка оформления: значение по умолчанию не хранится — альбом печатается как до настройки */
function setLook(k, v) {
  const a = ensure();
  if (!v || v === "base" || (k === "waterColor" && v.toLowerCase() === WATER)) delete a.meta[k]; else a.meta[k] = k === "waterColor" ? v.toLowerCase() : v;
  img.id = null; edited();
}
/* шрифт подписей карт: готовый или любой «f:<id>»; имя любого хранится рядом (labelFontName) — показать его и там, где шрифта нет */
function setFont(v, name) {
  const a = ensure();
  if (String(v).startsWith("f:") && name) a.meta.labelFontName = name; else delete a.meta.labelFontName;
  setLook("labelFont", v);
}
/* «Надписи» — окно «Макет надписей» (AlbumLayout.vue) для выбранного листа */
function openLay() { album.lay = cur.value; album.layTick++; winApi.open("albumlay"); }

/* «Слои листа»: роли выбранного листа от движка (окно «Слои и листы»); перечитываются при смене листа и после правок */
let rolesFor = null;
async function loadRoles() {
  const i = cur.value, id = sel.value?.id; if (!id) { roles.value = null; return; }
  if (!album.ready) return;
  try {
    const r = await call(a => a.roles(i));
    if (sel.value?.id === id) { roles.value = r ? JSON.parse(JSON.stringify(r)) : null; rolesFor = id; }
  } catch { roles.value = null; }
}
const laySum = computed(() => {
  const r = roles.value?.rows || [], off = r.filter(x => !x.on).length, bad = r.filter(x => x.badge && x.badge.tone !== "none").length;
  return [`${r.length} ${word(r.length, "роль", "роли", "ролей")}`, off ? `скрыто ${off}` : "", bad ? `${bad} с замечанием` : ""].filter(Boolean).join(" · ");
});
async function roleEye(r) { await act(a => a.role(cur.value, r.id)); setTimeout(loadRoles, 400); img.id = null; }
async function roleReset(r) { await act(a => a.resetRole(cur.value, r.id)); setTimeout(loadRoles, 400); img.id = null; }
watch(() => [sel.value?.id, album.rev, album.ready], ([id], [was] = []) => { if (id !== was) roles.value = rolesFor === id ? roles.value : null; loadRoles(); }, { immediate: true });
/* перетаскивание (как окно «Слои и листы» движка): роль — на лист списка (перенос, Alt — копия), слой проекта — на лист или строку
   роли. Правила и слова подсветки — движка (SheetLayers.check), действие с отменой Cmd+Z — его же (SheetLayers.drop). */
const dnd = reactive({ what: null, at: -1, row: null, copy: false, tone: "", text: "" }), qOpen = ref(null), bank = ref([]), bankOpen = ref(false);
let checkSeq = 0;
function dragStart(e, what) {
  if (!roles.value?.editable) { e.preventDefault(); return; }
  dnd.what = what; e.dataTransfer.effectAllowed = "copyMove"; e.dataTransfer.setData("text/plain", what.title);
}
function dragEnd() { Object.assign(dnd, { what: null, at: -1, row: null, tone: "", text: "" }); }
function dragOver(e, i, row = null) {
  const w = dnd.what; if (!w) return;
  if (row && w.type !== "layer") return;           // роль бросают на лист, строка роли принимает только слой
  e.preventDefault(); if (row) e.stopPropagation();
  const copy = w.type === "role" && e.altKey; e.dataTransfer.dropEffect = copy || w.type === "layer" ? "copy" : "move";
  if (dnd.at === i && dnd.row === row && dnd.copy === copy) return;
  Object.assign(dnd, { at: i, row, copy, tone: "", text: "" });
  const seq = ++checkSeq;
  call(a => a.dropCheck(i, { ...w, row: row || undefined }, copy)).then(r => { if (seq === checkSeq && r) { dnd.tone = r.ok ? (r.workingCopy ? "frozen" : "ok") : r.tone === "none" ? "none" : "bad"; dnd.text = r.text; } }).catch(() => { });
}
function dragLeave(e, i, row = null) { if (dnd.at === i && dnd.row === row && !e.currentTarget.contains(e.relatedTarget)) Object.assign(dnd, { at: -1, row: null, tone: "", text: "" }); }
async function dropOn(e, i, row = null) {
  const w = dnd.what; if (!w || (row && w.type !== "layer")) return;
  e.preventDefault(); if (row) e.stopPropagation();
  const copy = w.type === "role" && e.altKey; dragEnd();
  await dropWhat(i, { ...w, row: row || undefined }, copy);
}
async function dropWhat(i, w, copy) {
  const ok = await act(a => a.drop(i, w, copy));
  if (ok) { img.id = null; setTimeout(() => { loadRoles(); if (bankOpen.value) loadBank(); }, 500); }
}
/* меню роли «Перенести на лист» и «Копия на лист» — то же без мыши */
function moveRole(r, v) { dropWhat(+v.slice(1), { type: "role", from: cur.value, role: r.role, title: r.title }, v[0] === "c"); }
async function loadBank() { try { bank.value = JSON.parse(JSON.stringify(await call(a => a.bank()) || [])); } catch { bank.value = []; } }
watch(() => [album.rev, cur.value], () => { if (bankOpen.value) loadBank(); });
/* очередь источников: перетаскивание внутри списка или стрелки */
const qd = reactive({ r: null, from: -1, over: -1 });
function qStart(e, r, k) { if (!roles.value?.editable) { e.preventDefault(); return; } qd.r = r.id; qd.from = k; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", r.queue[k].title); }
function qDrop(r, k) { const from = qd.from, ok = qd.r === r.id; qd.r = null; qd.over = -1; if (ok && from !== k) reorder(r, from, k); }
async function reorder(r, from, to) {
  if (await act(a => a.reorderSrc(cur.value, r.id, from, to))) { img.id = null; setTimeout(loadRoles, 400); }
}
function setSheet(k, v) { if (!sel.value) return; sel.value[k] = v; edited(); }
function up() { const i = cur.value, l = sheets.value; if (i < 1) return; [l[i - 1], l[i]] = [l[i], l[i - 1]]; cur.value = i - 1; edited(); }
function drop() { askDrop.value = false; const l = sheets.value; if (!l.length) return; l.splice(cur.value, 1); cur.value = Math.min(cur.value, l.length - 1); edited(); }
function pick(i) { cur.value = i; album.fit++; }   // карта приближается к рамке листа
function keys(e) {
  const n = sheets.value.length; if (!n) return;
  const k = { ArrowDown: cur.value + 1, ArrowUp: cur.value - 1, Home: 0, End: n - 1 }[e.key];
  if (k == null) return;
  e.preventDefault(); cur.value = Math.min(Math.max(k, 0), n - 1);
  e.currentTarget.querySelector(`li:nth-child(${cur.value + 1})`)?.focus();
}

/* листы проекта — те же, что в «Макете листа» (SheetPanel.vue): новый — пустой А3, как там; открываются там же */
const own = computed(() => project.layouts || []);
const ownBusy = ref(false);
const ownHead = computed(() => own.value.length ? `Листы: ${own.value.length}` : "Листов нет");
const mapsOn = s => { const n = (s.blocks || []).filter(b => b.kind === "map").length; return n ? `${n} ${word(n, "карта", "карты", "карт")}` : ""; };
function openOwn(id) { sheetNav.id = id; sheetNav.tick++; winApi.open("sheet"); }
function addOwn() {
  const s = { id: newId("sheet"), ...newSheet({ format: "A3", title: `Лист ${own.value.length + 1}`, blank: true }) };
  project.layouts = [...JSON.parse(JSON.stringify(own.value)), s];
  openOwn(s.id);
}
async function ownPdf() {
  ownBusy.value = true;
  try { await printAll(JSON.parse(JSON.stringify(own.value)), meta.value, project.name || "листы"); } catch (e) { notice.value = "PDF листов: " + (e.message || e); } finally { ownBusy.value = false; }
}
/* раздел альбома раскрыт, если в альбоме есть листы; вопрос, ход сборки или «не всё готово» раскрывают его сами */
const albOpen = ref(!!project.raw?.album?.sheets?.length);
watch(() => !!(issues.value || legacy.value || st.value?.ask || st.value?.imp || st.value?.bp), v => { if (v) albOpen.value = true; });
watch(() => project.raw, r => { albOpen.value = !!r?.album?.sheets?.length; });
async function build(kind) {
  if (kind === "refresh") return refresh(null);
  if (kind === "file") { if (viewer.value) return; impFile.value?.click(); return; }
  if (!project.territory) { notice.value = "Сначала задайте границу территории — окно «Данные»: листы альбома строятся вокруг неё"; return; }
  await act(a => a.build(kind));
}
async function refresh(old) {
  legacy.value = 0;
  const r = await act(a => a.refresh(old));
  if (r?.old) legacy.value = r.old;
}
async function fill() {
  const d = await act(a => a.fillMeta());
  const names = { short: "№ КРТ", place: "округ, район", address: "адрес" };
  notice.value = d?.length ? "Заполнено: " + d.map(k => names[k] || k).join(", ") : "Нечего заполнять: поля уже заполнены или нужных слоёв нет";
}
/* PDF и PPTX: сначала «не всё готово» (если есть) — в этом окне; i — один лист */
async function file(kind, i) {
  issues.value = null;
  const lines = await act(a => a.issues(kind, i));
  if (lines?.length) { issues.value = { kind, i, lines: JSON.parse(JSON.stringify(lines)) }; return; }
  act(a => a.file(kind, i));
}
function go() { const q = issues.value; issues.value = null; if (q) act(a => a.file(q.kind, q.i)); }
function jump(l) {
  if (l.sheet != null) { cur.value = l.sheet; return; }
  if (l.stamp) stampOpen.value = true;
}
async function preview() {
  const s = sel.value; if (!s) return;
  img.busy = true; img.id = null;
  try { const url = await act(a => a.preview(cur.value)); if (url) { img.url = url; img.id = s.id; } } finally { img.busy = false; }
}
/* «Из файла…»: листы из проекта .grado2 или готовой вёрстки (readAlbumFile движка); вопрос «заменить или добавить» — st.imp */
const impFile = ref(null);
async function importFile(e) { const f = e.target.files?.[0]; e.target.value = ""; if (f) await act(a => a.importFile(f)); }
/* свой лист (не по шаблону, не готовая вёрстка): выбирается, что на нём — текущая карта, вид или ТЭП */
const ownMap = computed(() => sel.value && !sel.value.keys && !sel.value.panels && !sel.value.frozen && !["photos", "title", "situation"].includes(sel.value.kind));
async function setScheme(v) { const t = await act(a => a.setScheme(v)); if (t) notice.value = t; img.id = null; }

/* фотофиксация: снимки листа от движка (albumapi photos), добавить — тот же addPhotoFiles (1600 px, GPS из EXIF) */
const photos = ref([]), photoFile = ref(null), askClear = ref(false);
const noGps = computed(() => photos.value.filter(p => !p.at).length);
async function loadPhotos() {
  if (sel.value?.kind !== "photos" || !album.ready) { photos.value = []; return; }
  const i = cur.value; try { const r = await call(a => a.photos(i)); if (cur.value === i) photos.value = r ? r.map(p => ({ ...p })) : []; } catch { photos.value = []; }
}
watch(() => [sel.value?.id, album.rev, album.ready], loadPhotos, { immediate: true });
async function addPhotos(e) {
  const files = [...(e.target.files || [])]; e.target.value = ""; if (!files.length) return;
  await act(a => a.addPhotos(cur.value, files)); img.id = null; setTimeout(loadPhotos, 600);
}
async function dropPhoto(k) { await act(a => a.dropPhoto(cur.value, k)); img.id = null; setTimeout(loadPhotos, 600); }

/* спутник Яндекса по рамке листа (albumapi sat → /api/export/sat): папку загрузок спрашивает это окно; ход — из /api/progress */
const canSat = computed(() => sel.value && !["tep", "title"].includes(sel.value.kind) && !sel.value.panels);
const sat = reactive({ ask: false, dir: "", busy: false, text: "" });
async function askSat() { sat.dir = (await act(a => a.dlDir())) || sat.dir || ""; sat.ask = true; }
async function runSat() {
  const dir = sat.dir.trim().replace(/[\\/]+$/, ""); if (!dir) return;
  sat.ask = false; sat.busy = true; sat.text = "Спутник Яндекса: скачиваются снимки рамки листа.";
  const t = setInterval(async () => {
    try { const p = (await (await fetch("/api/progress")).json()).sat; if (p) sat.text = `Спутник Яндекса: снимки ${p.got} из ${p.total}. Первая выгрузка идёт минуты, повтор берётся с диска.`; } catch { }
  }, 1000);
  try { await act(a => a.sat(cur.value, dir)); } finally { clearInterval(t); sat.busy = false; sat.text = ""; }
}

/* меню «Выгрузка» → PDF или PPTX альбома: вкладка открылась (или уже открыта), выгрузка идёт отсюда */
watch(() => album.want, k => { if (k) { album.want = null; file(k); } }, { immediate: true });
</script>

<style>
.alb .ahead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; margin-bottom: 8px; }
.alb .stat { flex: 1 1 200px; margin: 0; min-width: 0; font-size: var(--wa-font-size-s); color: var(--g-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alb .acts { display: flex; flex-wrap: wrap; gap: 6px; }
.alb wa-button::part(label) { display: inline-flex; gap: 4px; align-items: center; }
.alb .job { display: flex; align-items: center; gap: 8px; padding: 6px 10px; margin-bottom: 8px; border-radius: 10px; font-size: var(--wa-font-size-s);
  background: var(--wa-color-brand-fill-quiet); border: 1px solid var(--wa-color-brand-border-quiet); }
.alb .job.quiet { background: var(--wa-color-surface-lowered); border-color: var(--g-line); color: var(--g-muted); }
.alb .job wa-spinner { font-size: 14px; --track-width: 2px; flex: none; }
.alb .job .jt { flex: 1; min-width: 0; }
.alb .job .t { white-space: nowrap; color: var(--g-muted); font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); }
.alb .ask { padding: 8px 10px; margin-bottom: 8px; border-radius: 10px; border: 1px solid var(--wa-color-brand-border-quiet); background: var(--wa-color-surface-raised); font-size: var(--wa-font-size-s); }
.alb .ask.warn { border-color: var(--wa-color-warning-border-normal); }
.alb .ask p { margin: 0 0 6px; line-height: 1.4; }
.alb .ask ul { margin: 0 0 6px; padding-left: 18px; }
.alb .ask .lnk { all: unset; display: block; cursor: pointer; text-decoration: underline dotted; line-height: 1.4; }
.alb .ask .lnk:focus-visible { outline: 2px solid var(--wa-color-focus); }
.alb .row { display: flex; flex-wrap: wrap; gap: 6px; }
.alb .stamp { margin-bottom: 8px; }
.alb .stamp::part(header) { font-size: var(--wa-font-size-s); }
.alb .stamp .sum { color: var(--g-muted); font-weight: 400; margin-left: 6px; }
.alb .stamp .fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; margin-bottom: 8px; }
.alb .lay .roles { list-style: none; margin: 0 0 6px; padding: 0; }
.alb .lay .roles li { display: grid; grid-template-columns: 28px minmax(0, 1fr) 40px auto 28px; align-items: center; gap: 6px; padding: 2px 0;
  font-size: var(--wa-font-size-s); border-top: 1px solid var(--g-line); }
.alb .lay .roles li:first-child { border-top: 0; }
.alb .lay .roles li.off .rt { opacity: .55; }
.alb .lay .rt { min-width: 0; overflow-wrap: anywhere; line-height: 1.3; }
.alb .lay .rt small { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin-left: 2px; }
.alb .lay .rt .src { display: block; margin-left: 0; }
.alb .lay .cov { text-align: right; font-variant-numeric: tabular-nums; font-size: var(--wa-font-size-xs); color: var(--g-muted); }
.alb .lay .cov.w { color: var(--wa-color-warning-on-quiet); }
.alb .lay .chips { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; align-items: center; max-width: 132px; }
.alb .lay .roles li[draggable=true] { cursor: grab; }
.alb .lay .roles li.drop-ok, .alb .list li.drop-ok { box-shadow: inset 0 0 0 2px var(--wa-color-success-border-loud, #2f9e44); }
.alb .lay .roles li.drop-bad, .alb .list li.drop-bad, .alb .list li.drop-none { box-shadow: inset 0 0 0 2px var(--wa-color-danger-border-loud, #c92a2a); }
.alb .lay .roles li.drop-frozen, .alb .list li.drop-frozen { box-shadow: inset 0 0 0 2px var(--wa-color-warning-border-loud, #e8590c); }
.alb .list li.drop-wait, .alb .lay .roles li.drop-wait { box-shadow: inset 0 0 0 2px var(--g-line); }
.alb .list .dcap { grid-column: 2 / -1; font-size: var(--wa-font-size-xs); line-height: 1.3; }
.alb .list .dcap.ok { color: var(--wa-color-success-on-quiet); } .alb .list .dcap.bad, .alb .list .dcap.none { color: var(--wa-color-danger-on-quiet); } .alb .list .dcap.frozen { color: var(--wa-color-warning-on-quiet); }
.alb .dfoot { margin-top: -4px; }
.alb .lay .lnk { all: unset; display: block; color: var(--wa-color-brand-on-quiet); font-size: var(--wa-font-size-xs); cursor: pointer; }
.alb .lay .lnk:focus-visible { outline: 2px solid var(--wa-color-focus); }
.alb .lay .mvh { margin: 4px 12px; font-size: var(--wa-font-size-xs); font-weight: 600; color: var(--g-muted); }
.alb .lay .queue { grid-column: 1 / -1; list-style: none; margin: 2px 0 6px 34px; padding: 0; border-left: 2px solid var(--g-line); }
.alb .lay .queue li { display: grid; grid-template-columns: 18px minmax(0, 1fr) 40px auto; gap: 6px; align-items: center; padding: 1px 0 1px 6px; font-size: var(--wa-font-size-s); }
.alb .lay .queue li[draggable=true] { cursor: grab; }
.alb .lay .queue li.used .qt { font-weight: 600; }
.alb .lay .queue .qn { color: var(--g-muted); text-align: right; font-variant-numeric: tabular-nums; }
.alb .lay .queue .qt small { color: var(--g-muted); font-weight: 400; }
.alb .lay .queue li.drop-ok { box-shadow: inset 0 2px 0 var(--wa-color-brand-border-loud, #1a5fb4); }
.alb .lay .bank { margin-top: 6px; }
.alb .lay .bkh { margin: 6px 0 2px; font-size: var(--wa-font-size-xs); font-weight: 600; color: var(--g-muted); }
.alb .lay .bkh small { font-weight: 400; }
.alb .lay .bk { list-style: none; margin: 0; padding: 0; }
.alb .lay .bk li { display: grid; grid-template-columns: minmax(0, 1fr) auto 28px; gap: 6px; align-items: center; padding: 1px 0; font-size: var(--wa-font-size-s); }
.alb .lay .bk li[draggable=true] { cursor: grab; }
.alb .lay .bk .bt { min-width: 0; overflow-wrap: anywhere; }
.alb .lay .bk .bs { color: var(--g-muted); font-size: var(--wa-font-size-xs); font-variant-numeric: tabular-nums; white-space: nowrap; }
.alb .photos .shots { list-style: none; margin: 0 0 8px; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 6px; }
.alb .photos .shots li { position: relative; border: 1px solid var(--g-line); border-radius: 6px; overflow: hidden; background: var(--wa-color-neutral-fill-quiet); }
.alb .photos .shots img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; }
.alb .photos .nm { display: block; padding: 2px 4px; font-size: var(--wa-font-size-xs); color: var(--g-muted); font-variant-numeric: tabular-nums; }
.alb .photos .x { position: absolute; top: 3px; right: 3px; width: 20px; height: 20px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 50%;
  background: rgba(0, 0, 0, .55); color: #fff; cursor: pointer; }
.alb .photos .x:focus-visible { outline: 2px solid var(--wa-color-focus); }
.satdlg { --width: 460px; }
.satdlg p { margin: 0 0 10px; line-height: 1.45; }
.alb .lay .chip { all: unset; font-size: var(--wa-font-size-xs); padding: 1px 6px; border-radius: 999px; background: var(--wa-color-neutral-fill-quiet); white-space: nowrap; }
.alb .lay .chip.warn { background: var(--wa-color-warning-fill-quiet); color: var(--wa-color-warning-on-quiet); }
.alb .lay .chip.bad { background: var(--wa-color-danger-fill-quiet); color: var(--wa-color-danger-on-quiet); }
.alb .lay .chip.hand { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); cursor: pointer; }
.alb .lay .chip.hand:focus-visible { outline: 2px solid var(--wa-color-focus); }
.alb .look .lookrow { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.alb .look .lbl { flex: 1; display: grid; font-size: var(--wa-font-size-s); line-height: 1.3; }
.alb .look .lbl small { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.alb .look wa-select { margin-bottom: 6px; }
.alb .look .hint { margin: 0; }
.alb .albsec { margin-top: 4px; }
.alb .albsec > .ahead { margin-top: 2px; }
.alb .empty { color: var(--g-muted); font-size: var(--wa-font-size-s); line-height: 1.4; }
.alb .list { list-style: none; margin: 0 0 8px; padding: 0; border: 1px solid var(--g-line); border-radius: 8px; }
.alb .list li { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto 16px; align-items: baseline; line-height: 16px; gap: 6px; padding: 6px 8px;
  font-size: var(--wa-font-size-s); cursor: pointer; border-top: 1px solid var(--g-line); }
.alb .list li:first-child { border-top: 0; }
.alb .list li:hover { background: var(--wa-color-neutral-fill-quiet); }
.alb .list li.on { background: var(--wa-color-brand-fill-quiet); }
.alb .list li:focus-visible { outline: 2px solid var(--wa-color-focus); outline-offset: -2px; }
.alb .list .n { color: var(--g-muted); font-variant-numeric: tabular-nums; text-align: right; }
.alb .list .t { overflow-wrap: anywhere; }   /* название целиком, длинное — в две строки (владелец 09.10.2026) */
.alb .list .f { color: var(--g-muted); font-size: var(--wa-font-size-xs); white-space: nowrap; font-variant-numeric: tabular-nums; }
.alb .list .nr { color: var(--wa-color-warning-on-quiet); align-self: start; margin-top: 1px; }   /* номер, формат и значок — на линии первой строки названия */
.alb .det { display: grid; gap: 8px; padding-top: 8px; border-top: 1px solid var(--g-line); }
.alb .det .g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.alb .det .flags { display: flex; gap: 16px; }
.alb .det .nrw { margin: 0; font-size: var(--wa-font-size-s); color: var(--wa-color-warning-on-quiet); }
.alb .det .hint { margin: 0; }
.alb .det .prev { border: 1px solid var(--g-line); border-radius: 8px; background: #fff; }
.alb .det .prev img { display: block; width: 100%; height: auto; }
</style>
