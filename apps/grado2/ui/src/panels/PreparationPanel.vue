<!-- ГРАДО 2 · серверная сборка существующего положения: импорт, статус, отчёт и выгрузка одной версии. -->
<template>
  <section class="preparation" aria-label="Существующее положение по мытищинскому образцу">
    <b>Существующее положение · мытищинский образец</b>
    <p>14 видов листов. ГИСОГД, НСПД, ОСМ и Яндекс загружаются внутри программы.</p>
    <div class="actions">
      <wa-button size="s" :disabled="running || readonly" :loading="starting" @click="start">Собрать презентацию</wa-button>
      <wa-button v-if="running" size="s" appearance="outlined" :disabled="readonly" @click="cancel">Остановить</wa-button>
    </div>
    <p role="status" aria-live="polite">{{ message }}</p>
    <template v-if="run">
      <p>{{ phases[run.phase] || run.phase }} · {{ run.progress?.got || 0 }} / {{ run.progress?.total || 14 }}<span v-if="run.report?.total"> · Требуют внимания: {{ run.report.total }}</span></p>
      <ul v-if="issues.length"><li v-for="(item,i) in issues" :key="i">{{ item.message }}<span v-if="item.fieldTitle"> · {{ item.fieldTitle }}</span><span v-if="item.sourceTitle"> · {{ item.sourceTitle }}</span><span v-if="item.objectKey && item.objectKey !== 'project.metrics'"> · {{ item.objectKey }}</span></li></ul>
      <label v-if="!running && !run.ready"><input type="checkbox" v-model="draft"> Выгрузить неполный комплект как черновик</label>
      <div v-if="!running && run.candidateSHA256" class="actions">
        <wa-button size="s" appearance="outlined" :disabled="downloading || (!run.ready && !draft)" @click="download('pdf')">PDF</wa-button>
        <wa-button size="s" appearance="outlined" :disabled="downloading || (!run.ready && !draft)" @click="download('pptx')">PPTX</wa-button>
      </div>
    </template>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { project } from "../store.js";
import { C, flush, open as openShared } from "../collab.js";
import { editTick, openProject, saveProject } from "../project.js";
const run=ref(null),issues=ref([]),message=ref(""),starting=ref(false),downloading=ref(false),draft=ref(false);
const pid=computed(()=>C.pid || project.file),readonly=computed(()=>C.pid && C.role==='viewer');
const running=computed(()=>run.value?.state==='running' || starting.value);
const phases={planned:'Подготовка',sources:'Получение слоёв',photos:'Фотофиксация',composition:'Комплектование',checking:'Проверка листов',finished:'Сборка завершена',stopped:'Сборка остановлена'};
let disposed=false,serial=0;
async function api(path,body,query={}) {
  const response=await fetch('/api/preparation/'+path+'?'+new URLSearchParams({projectId:pid.value,...query}),body===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Grado-Project-Capabilities':'sushpol-v1'},body:JSON.stringify({projectId:pid.value,...body})});
  const result=await response.json();if(!response.ok)throw new Error(result.error || 'Ошибка сервера');return result;
}
async function follow(id,token,tick,projectId) {
  while(!disposed && token===serial && pid.value===projectId) {
    run.value=await api('status',undefined,{runId:id,wait:10});
    if(run.value.state!=='running') {
      const report=await api('issues',undefined,{runId:id,limit:20});issues.value=report.issues;
      message.value=run.value.ready ? 'Комплект готов.' : 'Комплект требует уточнений. Причины указаны ниже.';
      if(tick!==null && editTick()===tick) {
        if(C.pid)await openShared(projectId);else await openProject(projectId);
      } else if(tick!==null)message.value+=' В окне есть новые правки; сохранённый результат не подставлен поверх них.';
      return;
    }
    await new Promise(resolve=>setTimeout(resolve,300));
  }
}
async function start() {
  starting.value=true;message.value='Сохраняю исходный проект…';issues.value=[];draft.value=false;
  try {
    if(C.pid) { if(!await flush())throw new Error('Сначала разрешите конфликт сохранения проекта'); }
    else if(!await saveProject(project.file || project.name))throw new Error('Перед сборкой сохраните проект под именем');
    const projectId=pid.value,tick=editTick(),token=++serial;
    const result=await api('start',{commandId:crypto.randomUUID(),refresh:true,photos:true});
    run.value=result;message.value='Получаю исходные слои…';
    starting.value=false;await follow(result.runId,token,tick,projectId);
  } catch(error){message.value=error.message;}finally{starting.value=false;}
}
async function cancel(){try{await api('cancel',{runId:run.value.runId});message.value='Остановка запрошена.';}catch(error){message.value=error.message;}}
async function download(format) {
  downloading.value=true;
  try {
    const response=await fetch('/api/preparation/export?'+new URLSearchParams({projectId:pid.value,runId:run.value.runId,format,draft:draft.value?'1':'0'}));
    if(!response.ok)throw new Error((await response.json()).error || 'Выгрузка не удалась');
    const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='Существующее положение'+(draft.value?' — черновик':'')+'.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  } catch(error){message.value=error.message;}finally{downloading.value=false;}
}
watch(pid,async value=>{
  const token=++serial;run.value=null;issues.value=[];message.value='';
  if(!value)return;
  try{const status=await api('status');const active=status.preparation?.activeRun;if(active && token===serial)await follow(active.runId,token,null,value);}catch(error){if(token===serial)message.value=error.message;}
},{immediate:true});
onBeforeUnmount(()=>{disposed=true;serial++;});
</script>
<style scoped>
.preparation{padding:12px;border:1px solid var(--line,#ddd);border-radius:6px;margin-block:12px}.preparation p{margin:8px 0;line-height:1.45}.actions{display:flex;gap:8px;flex-wrap:wrap}.preparation label{display:flex;align-items:center;gap:8px;margin:10px 0}.preparation li{margin-block:6px;overflow-wrap:anywhere}
</style>
