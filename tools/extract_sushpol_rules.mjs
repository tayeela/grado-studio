/* Извлекает правила ВРИ действующего альбома для серверного сборщика; проверка: node tools/extract_sushpol_rules.mjs --check. */
/* ГРАДО 2 · переносит действующие правила/цвета ВРИ в общий паспорт Python без браузера.
   Читает только доверенный albums.js, Babel разбирает декларации; --check проверяет свежесть.
   Контрольные примеры исполняют исходный landUseOf, Python проверяется теми же примерами. */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const source=fs.readFileSync(path.join(root,'apps/grado2/web/albums.js'),'utf8');
const require=createRequire(path.join(root,'apps/grado2/ui/package.json'));
const parser=require('@babel/parser');
const ast=parser.parse(source,{sourceType:'script'});
const declarations=new Map();
for(const stmt of ast.program.body) if(stmt.type==='VariableDeclaration') for(const d of stmt.declarations)
  if(d.init) declarations.set(d.id.name,source.slice(d.init.start,d.init.end));
const names=['VRI_T','VRI_WORDS','SPEC_ZONES','TRANSPORT_ZONES','OSM_USE','ZOUIT_LGR','C_TERR','C_TW'];
const context=vm.createContext({});
const code=names.map(n=>`const ${n}=${declarations.get(n)};`).join('\n');
vm.runInContext(code,context,{timeout:1000});
function clean(v){
 if(Object.prototype.toString.call(v)==='[object RegExp]') return {pattern:v.source,flags:v.flags};
 if(Array.isArray(v))return v.map(clean);
 if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,clean(x)]));
 return v;
}
const output={schemaVersion:1,source:'apps/grado2/web/albums.js',rules:{}};
for(const name of names) output.rules[name]=clean(vm.runInContext(name,context));
const more=['ZONE_OF','LAND_USE','VRI_CLS','CODE_CLS','AGRI_CLS','landUseOf'];
vm.runInContext('let tinao=false; const safe=f=>f(); const inNewMoscow=()=>tinao;\n'+more.map(n=>`const ${n}=${declarations.get(n)};`).join('\n'),context,{timeout:1000});
const inputs=[...new Set(Object.values(output.rules.VRI_T).flatMap(v=>[v[0],...v[2].map(c=>`Код (${c})`)])),'','Cадоводство','1.2.9 склад','Офис','Существующее производство','ИЖС','4.9.1.1'];
output.contractCases=[];
for(const tinao of [false,true]) for(const text of inputs){
 context.caseText=text;context.caseTinao=tinao;
 const value=vm.runInContext('tinao=caseTinao;landUseOf({"ВРИ":caseText})',context,{timeout:1000});
 output.contractCases.push({tinao,text,classId:value?.[3]??null});
}
output.sourceSHA256=crypto.createHash('sha256').update([...names,...more].map(n=>declarations.get(n)).join('\n')).digest('hex');
const result=JSON.stringify(output,null,2)+'\n';
const target=path.join(root,'docs/standards/albums/sushpol-rules-v1.json');
if(process.argv.includes('--check')){
 if(!fs.existsSync(target)||fs.readFileSync(target,'utf8')!==result){process.stderr.write('sushpol rules stale\n');process.exit(1);}
}else fs.writeFileSync(target,result);
process.stdout.write(`sushpol rules: ${output.contractCases.length} contract cases\n`);
