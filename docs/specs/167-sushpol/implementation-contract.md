# Контракты реализации набора #167

Нормативное дополнение к [ТЗ](../167-sushpol-mytishchi.md), редакция 2 от 29.10.2026.
Слова «нормативное» и «обязательно» относятся здесь к контракту программы, а не к юридической оценке территории.
Производственный код по этому контракту ещё не написан. Все значения ниже — проектные решения;
указанные пределы подлежат проверке, а не выдаются за измеренную производительность.

## 1. Идентичность и версии

recipeId = `sushpol-mytishchi`, recipeVersion = 1, schemaVersion = 1.
Ключи видов и их порядок заданы в [матрице листов](sheet-contracts.md).
UUID instanceId создаётся один раз при выборе нового набора. sheetId = instanceId + ":" + kind;
pageId = sheetId + ":" + номер продолжения с нуля. Строки, фотографии и документы имеют собственные
постоянные ключи; порядковые номера страниц и объектов не являются ключами.

Внешняя версия проекта остаётся 2. В album.meta добавляются sushpolPreparation и
requiredCapabilities = ["sushpol-v1"]. Они проходят существующее split/join раздела album;
геометрия и снимки остаются в нынешних слоях/листах. Неизвестная schemaVersion сохраняется побайтно
как JSON-значение и открывается новым клиентом только для просмотра, без автоматической нормализации.

### Канонические типы

Время — строка UTC ISO 8601, координаты обмена — GeoJSON WGS84 [lon,lat], расстояния/площади расчёта — МСК,
метры/м². Поля со значением null не заменяются нулём. Невалидная геометрия не исправляется молча.
Идентификаторы запуска/запроса/команды — UUID; все неизвестные поля известных схем сохраняются при round-trip.

```text
Preparation = {
 schemaVersion:1, recipeId:"sushpol-mytishchi", recipeVersion:1, instanceId:UUID,
 generation:int>=0, activeRun:Run|null, requests:Record<UUID,Acquisition>,
 sheets:Record<kind,SheetState>, decisions:Decision[], overrides:Override[],
 numbering:Record<objectKey,int>, lastExport:Export|null
}
Run = {
 runId:UUID, ownerClientId:UUID, state:RunState, baseInputsRevision:SHA256,
 inputRevision:SHA256, startedAt:UTC, updatedAt:UTC, reasonCodes:string[],
 checkpointId:string|null, committedRevision:string|null
}
Acquisition = {
 requestId:UUID, runId:UUID, sourceKey:string, requestedArea:Polygon|MultiPolygon,
 checkedParts:CheckedPart[], state:RequestState, checkedAt:UTC|null,
 dataDate:UTC|null, reasonCode:string|null, layerIds:string[], dataRevision:SHA256|null
}
CheckedPart = {
 partId:string, area:Polygon|MultiPolygon, sublayer:string, outcome:"received"|"empty",
 checkedAt:UTC, dataDate:UTC|null, provenance:"network"|"cache", originalRequestId:UUID
}
SheetState = {
 sheetId:string, kind:string, state:SheetStatus, dependencyRevisions:Record<string,SHA256>,
 inputRevision:SHA256|null, reasonCodes:string[], pageIds:string[], decisionIds:UUID[]
}
Decision = {
 id:UUID, scope:{sheetId:string,objectKey:string|null,field:string|null},
 code:"not_applicable"|"allow_missing"|"confirm_value"|"confirm_relation",
 basis:string, value:JSON|null, dependencyRevision:SHA256, confirmedAt:UTC
}
Override = {id:UUID, scope:{sheetId:string,objectKey:string|null,field:string},
 value:JSON, basis:string, dependencyRevision:SHA256, state:"accepted"|"conflict"}
Export = {exportId:UUID, generation:int, inputRevision:SHA256, pageIds:string[],
 format:"pdf"|"pptx", state:"built"|"download_requested"|"saved_confirmed"|"failed",
 isDraft:boolean, reasonCodes:string[], createdAt:UTC, fileSHA256:string|null}
```

Новый ответ источника не удаляет Override. При изменении соответствующего исходного поля override
становится conflict; владелец принимает новое значение либо повторно подтверждает своё. Decision теряет силу
при несовпадении dependencyRevision. Подтверждение отсутствия не меняет исходное значение на выдуманное.

### Ревизии и зависимости

Ревизии выпускает только сервер. POST /api/preparation/revision получает projectId и снимок входов
под обычным правом write, возвращает baseInputsRevision, inputRevision и dependencyRevisions.
JS хранит возвращённые значения, не реализует собственный сериализатор/хешер. Сервер нормализует
конечные числовые значения: целые в диапазоне точного JSON-числа ±(2^53−1) превращает в int,
остальные сохраняет float; неизвестные поля сохраняет. SHA256 считается от UTF-8
json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False).
Порядок массивов сохраняется, порядок ключей объектов не влияет. Формирование и проверка ревизий
в local/hub используют один preparation.py; JS/Python не обязаны независимо повторять формат чисел.
GET/POST не принимает чужую готовую ревизию как доказательство данных: commit пересчитывает её на сервере.

baseInputsRevision включает территорию, контекст координат, роли/назначения слоёв, настройки набора,
ручные уточнения, рамки/масштабы/подписи и фото. Операционные state/time/runId и положение курсора исключены.
Получение новых данных не меняет baseInputsRevision, но меняет inputRevision. dataRevision каждого слоя
включает fc, original, ручные изменения, происхождение и acquisition, исключая историю технических попыток.
inputRevision = хеш объекта {baseInputsRevision, dependencyRevisions}. Для каждого листа зависимости
определяются матрицей; изменение прав не инвалидирует ортофотоплан, изменение radius_m инвалидирует
только healthcare и его охват. Для экспорта добавляются порядок страниц и композиция. Поле dataRevision внутри Acquisition не входит
в собственный хеш слоя (разрыв самоссылки); acquisitionRefs заменяются содержимым подтверждений без runId,
requestId и технических времён. Проверенные области/исходная дата входят в хеш. Повтор того же результата
не меняет смысловую ревизию только из-за времени попытки.

### Состояния и переходы

| Объект | Перечисление | Разрешённые переходы |
|---|---|---|
| RunState | planned, running, paused, interrupted, blocked, ready, cancelled, conflict | planned→running; running→paused/interrupted/blocked/ready/cancelled/conflict; paused/interrupted/blocked→running новым runId; conflict→cancelled либо новый план после выбора; ready/cancelled терминальны |
| RequestState | planned, running, received, empty, partial, failed, interrupted, cancelled | planned→running/cancelled; running→received/empty/partial/failed/interrupted/cancelled; повтор — новый requestId со ссылкой на подтверждённые части |
| SheetStatus | waiting, building, needs_data, needs_decision, needs_check, ready, stale | waiting→building/needs_data; building→needs_data/needs_decision/needs_check/ready; needs_*→building; ready→stale при смене зависимости; stale→building |

Причины radius_not_defined и unknown_rule используются листом образования; radius_not_defined
сам по себе не блокирует штатное правило ЦАО.

При открытии проекта running превращается в interrupted, building — в needs_check. Состояние ready
не восстанавливается по одному прежнему флагу: проверяются хеши, подтверждения и ограничения вёрстки.
Полный результат ready требует всех 14 видов с ready, включая принятые допустимые исключения матрицы.
Ни одно исключение не скрывается из отчёта подготовки/экспорта. Нельзя принять отсутствие территории,
противоречивую связь объекта, недостающую страницу, испорченное изображение или переполненный блок.

Общие reasonCode: missing_source, partial_coverage, unknown_outcome, missing_field, unknown_rule,
invalid_geometry, stale_dependency, manual_conflict, version_conflict, unsupported_schema,
checkpoint_failed, budget_exceeded, layout_overflow, interrupted, cancelled. Фото добавляет коды из раздела 5.
Код сопровождается sheetId/objectKey/field/sourceKey и действием: получить ещё раз, дополнить поле,
проверить связь, выбрать правило, уменьшить охват, заменить фото, открыть новую версию или продолжить.
Текст для человека — отдельное поле; решения программы не извлекаются из текста.

## 2. Получение и сохранение подтверждений

POST /api/fetch сохраняет прежний ответ layers/errors и принимает необязательные projectId, runId,
requestId. На каждый sourceKey запроса возвращается один Acquisition; в группе sourceKey
подзапрос имеет собственный requestId, а родительский commandId связывает группу. Отсутствие источника
в acquisition — unknown_outcome, не empty. partial имеет только действительно проверенные checkedParts;
received/empty требуют покрытия всех запрошенных подслоёв и частей. Пример: запрос двух квадратов
по 1 км², проверено по 0,8 км² без перекрытия — покрытие 80 %, не габарит в 100 %.
Пустой ответ проверенного подслоя даёт empty только в проверенной области.

Каноническое место подтверждений — Preparation.requests, в том числе когда пустой ответ не создал слоя.
Каждый непустой DATA[layerId] имеет acquisitionRefs: UUID[]; это ссылки, не дубликаты геометрии подтверждений.
Сохраняются в web/project.js collectProject/applyProject и в DATA_F ui/src/collab.js.
UI data.js и фактический путь iframe web/app.js loadKeys принимают acquisition и возвращают планировщику
полный исход, а не только число слоёв. Смена PROJ_EPOCH отклоняет весь ответ до применения.
Старые EMPTYCOV/bbox используются прежними наборами, но не доказывают охват нового набора.

Данные и Acquisition одного requestId публикуются одной транзакцией изменения проекта. Сначала
проверяется схема, корреляция и ревизия; затем обновляется подготовленная копия разделов слоя+album;
только успешная проверка всех ссылок делает копию текущей. Отказ не оставляет ссылку без данных
или геометрию с подтверждением другой попытки. Удалённые/заменённые данные удаляют неиспользуемые ссылки;
проверенные пустые области сохраняются как текущие подтверждения. При экспорте файла, iframe split/join,
hub pull/push выполняется один и тот же контракт, включая unknown-поля схемы.

## 3. Мост интерфейса и конкурентная работа

Команды albumapi: plan, start, resume, stop, refresh, getReport. Envelope =
{protocolVersion:1, commandId:UUID, projectId:string, clientId:UUID, runId:UUID|null,
expectedProjectRevision:string, inputRevision:SHA256, leaseId:UUID|null, args:object}.
plan.args = {recipeId,instanceId|null}; start.args = {planId}; resume.args = {previousRunId};
stop.args = {}; refresh.args = {sheetIds:string[],sourceKeys:string[]}; getReport.args = {}.
Ответ = {commandId,projectId,runId,inputRevision,ack:boolean,reasonCode|null,result:object|null}.
plan не меняет проект; start фиксирует plan.dependencies/назначения ролей и только затем вычисляет
baseInputsRevision, создаёт runId, resume создаёт новый runId, сохраняет удачные подтверждения;
stop выставляет cancellation Event, не удаляет принятые данные. Повтор commandId возвращает прежний ответ,
повтор start с другим commandId при активном запуске даёт version_conflict. Ответы последних 64 команд
хранятся на время текущей сессии; после перезапуска start/resume проверяет записанный activeRun,
не пытается воскресить неполученный ответ в памяти.

Перед командой albumhost передаёт снимок в applyProject и требует ACK с projectId, inputRevision,
projectRevision и protocolVersion. Ошибка даёт NACK; album.ready остаётся false, очередь команд не исполняется.
Таймаут ACK — 10 секунд, один запрос, без автоматического повтора команды. При NACK пользователь получает
действие «Повторить передачу проекта». Просмотр старого листа при этом доступен.

Результат применяется как одна единица: изменённые данные, Preparation и листы конкретного instanceId.
Перед применением совпадают projectId, PROJ_EPOCH, runId, generation, baseInputsRevision и все прочитанные
ревизии зависимостей. Произвольный pull всего album в ходе нового запуска запрещён; прежние наборы
продолжают старый путь. Ручная правка затронутого поля делает результат конфликтным, не стирается.

Для local сохранение сравнивает SHA256 байтов сохранённого проекта. Для hub используется текущая rev.
Это projectRevision; она отличается от смыслового inputRevision. У одного проекта один активный
ownerClientId/runId. Hub хранит lease в metadata проекта; локальный сервер — в sidecar проекта.
Lease живёт 30 секунд, продление каждые 10 секунд. Истечение разрешает новый runId после чтения текущей
ревизии, а старый ответ отклоняется. Lease не является очередью фоновых заданий и не предоставляет доступ.
Два одновременных старта проверяются под той же блокировкой хранения, один получает conflict.

### Серверный lease: acquire, renew, release

POST /api/preparation/lease принимает {action:"acquire"|"renew"|"release", projectId, runId,
ownerClientId, commandId, leaseId:null|UUID, expectedProjectRevision:null|string}.
Для acquire обязательна текущая expectedProjectRevision, leaseId=null; для renew/release — выданный leaseId.
Ответ: {ack:boolean,projectId,runId,ownerClientId,leaseId,expiresAt:UTC|null,
projectRevision,reasonCode:null|string,released:boolean}. Отказы доступа — прежние 401/403;
занятость, несовпадение ревизии/владельца/leaseId — 409 version_conflict без смены lease.

acquire под lock проверяет write-доступ, capability, expectedProjectRevision и отсутствие живого lease.
Записывает {leaseId,runId,ownerClientId,authenticatedUser,expiresAt=now+30s} в local sidecar/hub metadata
атомарно, без повышения projectRevision: это операционные сведения, а не новая версия содержимого.
Повтор commandId возвращает прежний lease, не продлевает его; если он уже истёк — требуется новый acquire.
renew под тем же lock проверяет все идентификаторы и текущего пользователя, неистёкший lease;
продлевает на 30 секунд, не возобновляет уже истёкшее владение. Повтор commandId идемпотентен;
каждый heartbeat получает новый commandId. release удаляет только совпавший lease; уже отсутствующий
даёт ack=true,released=false, lease другого владельца не удаляется. Lease хранится с проектом,
после перезапуска истёкшие записи не воскресают. Время сервера является источником срока.

albumhost перед start/resume вызывает acquire, затем передаёт leaseId в envelope iframe. Running начинается
только после ACK applyProject и ACK start; при ошибке передачи albumhost вызывает release.
Он же посылает renew каждые 10 секунд и release при stop/pause/ready/cancelled/conflict/закрытии.
При первом отказе/таймауте heartbeat (5 секунд) клиент прекращает новые сетевые задания,
отменяет текущую работу, переводит run в interrupted и оставляет staged-кандидат неприменённым.
Автоматический acquire после отказа не делается. Продолжение — явный resume с новым runId после чтения
текущего проекта; при недоступном сервере ранее полученные данные остаются в памяти/последней сохранённой версии.
commit/checkpoint принимают также leaseId и под lock проверяют его срок/владельца;
stop сохраняет доступные данные только при действующем владении, иначе предлагает сохранить копию.

Конфликтные результаты не смешиваются. Пока вкладка открыта, её кандидат остаётся в памяти как отдельный
результат с собственным runId; исходный проект и результат другой вкладки остаются на сервере. Действия:
перечитать текущую версию и повторить план либо сохранить свой кандидат как новый проект штатной командой
«Сохранить копию». Копия получает новый projectId, instanceId и обнулённый activeRun; все sheetId/pageId и scope ссылок
одним проходом меняют префикс прежнего instanceId на новый, ключи объектов/номера сохраняются; данные/правки сохранены.
Закрытие вкладки не обещает сохранности неподтверждённого кандидата; принятые и сохранённые этапы сохраняются.

## 4. Контрольная версия, публикация и совместимость

Нужны два серверных маршрута: POST /api/preparation/checkpoint и POST /api/preparation/commit.
Доступ — существующий project write, viewer запрещён. В HUB они делегируют методы Hub под его lock,
не вызывают запрещённый POST /api/project. Локальный путь использует блокировку по каноническому пути;
один сервер владеет каталогом проектов. Два процесса, пишущие в один локальный каталог, не поддерживаются.

checkpoint body = {projectId,runId,leaseId,commandId,expectedProjectRevision}; клиент сначала сохраняет все
принятые данные/правки обычным путём с проверкой ревизии. Сервер под lock сравнивает ревизию, квоту и lease,
записывает полную контрольную версию, игнорируя обычные интервалы 600/3600 секунд, и возвращает
{checkpointId,projectRevision,contentSHA256}. UUID в имени исключает коллизию снимков одной минуты.
В local — .versions; в hub — его собственное хранилище снимков с force_snap=True и записью checkpointId.
Повтор commandId возвращает тот же идентификатор; ответ отправляется только после успешной атомарной записи.
Недостаток квоты — checkpoint_failed, без публикации нового альбома. Последний снимок операции закреплён
от обычной ротации до следующей успешной замены/явного подтверждения владельцем, учитывается в квоте.

commit body = {projectId,runId,leaseId,commandId,expectedProjectRevision,checkpointId,inputRevision,candidateProject}.
Допустимый размер — существующий MAX_PROJECT_BODY, не общий лимит небольшого JSON-запроса.
Кандидат строится в памяти без публикации частично готовых листов. Сервер проверяет владение запуском,
снимок, ревизию, схему, зависимости, ссылки и полноту набора. Затем одной атомарной записью сохраняет проект
и увеличивает rev/generation. Ответ содержит новую projectRevision, generation и contentSHA256.
Клиент заменяет текущие разделы только после ACK; неизвестный исход сетевой отправки проверяет
GET /api/preparation/commit-status?projectId=…&commandId=… под тем же доступом. Сетевой повтор не создаёт вторую замену.
Идемпотентность последних 64 commit хранится на сервере с project metadata, не только во вкладке.

### Долговечная публикация двух файлов

Один os.replace проекта и последующий os.replace metadata не считаются общей атомарной операцией.
Для защищённых проектов local и hub используют один механизм журнала упреждающей записи в preparation.py.
Исключение/остановка процесса между заменами покрываются восстановлением. Защита от физической
поломки диска/потери всего каталога этим механизмом не обещается; остаются обычные резервные копии.

Под проектной блокировкой сначала выполняется recovery, затем проверки CAS/снимка/lease.
Для commandId создаётся неизменяемый каталог .preparation-txn/<commandId>/ с project.next и meta.next.
meta.next содержит следующую ревизию/generation и сохранённый результат commandId из последних 64,
а также capability/сведения о снимке; в local sidecar хранит SHA256 новых байтов, в hub — следующую rev.
Файлы полностью записываются и fsync. Затем атомарно записывается и fsync журнал pending.json:
{commandId,baseRevision,nextRevision,checkpointId,projectSHA256,metaSHA256,transactionDirectory}.
Путь строит сервер, клиент его не задаёт. Журнал становится единственной точкой обязательства commit.
До этой записи отмена может отбросить stage; после неё операция завершается/восстанавливается,
а отмена не обещает откат уже принятой транзакции.

После журнала сервер копирует project.next во временный файл рядом с project.grado2, fsync и os.replace;
затем так же публикует meta.next как metadata. Не перемещать единственные stage-файлы: они нужны recovery.
После проверки обоих SHA256 журнал удаляется атомарным завершением; при возможности платформы fsync
родительского каталога, на Windows — закрытие/flush файлов перед replace. ACK только после этих шагов.
Упавший/отказавший запрос не освобождает проект для обслуживания частичного состояния: следующий
reader/writer под lock обязан выполнить recovery до возврата содержимого или ревизии.

Recovery читает pending.json, проверяет безопасный серверный путь и SHA256 обоих stage-файлов и
повторно публикует оба файла (roll forward), затем удаляет журнал. Это идемпотентно, в том числе если
оба новых файла уже опубликованы. При отсутствующем/повреждённом stage — checkpoint_failed;
проект не выдаётся как согласованный и не перезаписывается обычным сохранением. Восстановление
контрольной версии требует явного restore с сохранением повреждённого состояния для разбора.
Не связанный с pending каталог старше 24 часов можно удалить служебной очисткой только пространства txn;
он учитывается в квоте. Активный/журналируемый каталог не удаляется.

commit-status запускает recovery до ответа. Падение до pending означает not_committed (повтор commandId
разрешён с исходной ревизией); после pending — committed после успешного roll forward либо recovery_failed,
а не новый независимый commit. Падение после удаления pending разрешается по metadata с сохранённым
commandId. Обычные записи защищённого проекта, restore и изменения server metadata вызывают ту же
recovery перед работой; операции, меняющие одновременно проект/rev/idempotence, используют этот же журнал.
Hub._commit и все local/hub пути чтения подлежат этой интеграции, не только новый API.

Восстановление — POST /api/preparation/restore {projectId,checkpointId,expectedProjectRevision,commandId}.
Сначала checkpoint текущего состояния, затем CAS и атомарная запись выбранной полной версии;
новая монотонная rev, прошлый run прекращён, running/building становятся interrupted/needs_check.
Отказ квоты/записи оставляет текущий файл. Отмена до commit оставляет прежний альбом;
после подтверждённого commit отмена не откатывает автоматически — используется restore.
Падение после записи до ACK разрешается commit-status; падение при staged-сборке сохраняет прежний альбом.

### Поддерживаемые клиенты

До первой записи нового набора сервер атомарно ставит флаг requiredCapabilities в local sidecar/hub metadata
и создаёт контрольную версию прежнего проекта. Это часть checkpoint, а не доверенное поле тела старого клиента.
Все пути записи защищённого проекта, включая autosave, push, restore и импорт поверх, требуют
заголовок X-Grado-Project-Capabilities: sushpol-v1, известную schemaVersion и сохранность обязательных полей.
Обычный старый клиент не присылает заголовок: сервер отклоняет запись 409 unsupported_schema, без изменений.
Новый клиент при неизвестной схеме может скачать/копировать исходный файл, но не перезаписывать проект.
Чтение старым клиентом допускается как просмотр старых совместимых разделов; новый набор не считается им
правильно отображённым. Запись/пересборка новым клиентом старого проекта разрешена после проверки round-trip.

Защита действует на обновлённом сервере/установленной программе. Старый отдельный сервер, получивший копию
файла, технически способен её испортить; такой путь записи не поддерживается и не заявляется совместимым.
Исходный экспортированный файл и контрольная версия сохраняются отдельно, не перезаписываются миграцией.
Флаг в server metadata не снимается обычным импортом без метаданных подготовки.
Проверка совместимости: старые collectProject/join намеренно удаляют новые поля, старый POST/push
отклоняется сервером; текущий клиент сохраняет всё через файл, iframe, local и hub.

## 5. Точки панорам и скачивание кадра

Граница сначала проверяется в МСК. Используются только наружные кольца всех частей MultiPolygon;
отверстия не дают дополнительные цели. Части сортируются по убыванию площади, при равенстве — по
лексикографическому списку координат канонического кольца. Кольцо ориентируется против часовой стрелки,
начало — вершина с минимальным (x,y), при совпадении — следующий лексикографически меньший цикл.
Длины наружных колец складываются. Восемь целей — расстояния (i+0,5)×суммарная_длина/8, i=0..7,
по последовательности колец. Разрыв между частями не входит в длину. Это детерминированная начальная
раскладка, не доказательство репрезентативности всех частей; владелец может добавить позиции.

Для кандидатов OSM сохраняются highway, access, foot, tunnel, bridge, layer и исходный _key.
Нормализованный атрибут highway может читаться как «Тип дороги»; остальные теги остаются под исходными
именами. Старый кэш без версии osmSchema=2 не используется для выбора точек: получить дороги заново
в отдельном ключе кэша, не удалять общий кэш. Если исходник не содержит тегов, их отсутствие не означает
подтверждённую открытость участка. Это данные для выбора точки, не расчёт пешеходного маршрута.

Допустимые highway: residential, living_street, service, unclassified, tertiary, secondary, primary,
footway, pedestrian, path, steps, track. motorway, motorway_link, trunk, trunk_link, construction,
proposed исключены независимо от других тегов. tunnel!=no при непустом значении и layer<0 исключены;
bridge!=no при непустом значении и layer>0 исключены для начального наземного плана.
foot=no/private запрещает; foot=yes/designated/permissive разрешает access=no/private только при
явном foot-разрешении; без такого foot access=no/private запрещает. Иные значения допускают кандидата
с записанными исходными тегами, но не утверждают правовой режим доступа.

Для каждой цели проецировать её на каждый допустимый линейный сегмент в 250 м в МСК. Сортировка:
расстояние, _key дороги, номер части, номер сегмента, доля вдоль сегмента. Первые два различных кандидата,
расстояние между которыми >=10 м, — основной и запасной. При отсутствии второго повтор основной точки
не выполняется. На позиции не больше двух поисков, на комплект не больше 16, включая ошибки поиска;
транспортные повторы netutil входят в лимит трёх попыток одного поиска. Источник опрашивается последовательно.

Метаданные с расстоянием Point от кандидата >100 м отклоняются. Географический азимут берётся по WGS84
от фактического Point к цели; при расстоянии <1 м — undefined, нужен ручной азимут или запасной кандидат.
Одинаковый panoramaId и круговая разность азимутов <15° считаются дублем; младшая позиция остаётся,
старшая пробует запасного кандидата, затем needs_data. При разнице ровно 15° кадры различны.
HTTP 429 прекращает текущий автоматический план до cooldown; запасной кандидат не обходит паузу.

### API кадра и отмена

POST /api/panorama/frame body = {projectId,runId,requestId,photoId,inputRevision,
candidate:[lon,lat],target:[lon,lat],azimuthDeg:number|null}.
Все координаты конечные и в географических пределах. azimuthDeg нормализуется в [0,360), ручное значение
имеет приоритет над направлением на target; null означает расчёт. HFOV=80°, pitch=0°, output=1500×1000.
Повтор requestId с тем же телом возвращает кэш результата этой попытки; с другим телом — 409 conflict.
requestId не предоставляет доступ: каждый вызов проверяет обычный доступ к projectId.

Успех: {projectId,runId,requestId,photoId,inputRevision,image:{mime:"image/jpeg",data:base64,
width:1500,height:1000,sha256},panoramaId,imageId,point:[lon,lat],azimuthDeg,hfovDeg:80,
sourceUrl,downloadedAt,takenAt:null|UTC}. Ошибка: те же идентификаторы +
{reasonCode,retryAfterAt:null|UTC,completedTileKeys:string[]} без image.
Коды: no_panorama, metadata_unconfirmed, rate_limited, source_unavailable, unsupported_projection,
tile_missing, insufficient_resolution, timeout, cancelled, budget_exceeded, version_conflict.
Неожиданный HTML/капча — source_unavailable, неизвестная структура — metadata_unconfirmed.
Фактическая точка/направление всегда сохраняются, дата из имени imageId не считается датой съёмки.

POST /api/panorama/cancel {projectId,runId,requestId} идемпотентно ставит Event текущего запроса;
чужой projectId не может отменить работу. Abort клиента также вызывает cancel; сервер сам соблюдает deadline
при пропаже вкладки. Активные запросы — ограниченный реестр текущего процесса, не постоянные фоновые задания.
Повтор после перезапуска использует новый requestId и проверенные тайлы кэша.

Общий дедлайн — monotonic start+120 секунд от входа API, включает очередь портала, метаданные, повторы,
тайлы и проекцию. Один активный кадр на процесс; второй запрос получает занято/ожидание без второй сетевой очереди.
Ожидание GATE учитывает отмену и оставшийся срок. Сеть использует новый netutil.arequest через существующий
httpx.AsyncClient и tenacity.AsyncRetrying с теми же <=3 попытками, TLS и проверками тела. Отдельного
повторяющего цикла в коннекторе нет. Внешний asyncio.timeout ограничивает суммарный срок; каждый сетевой
этап получает оставшийся deadline и cancel. Async-задача закрывает response/client при отмене.
Проверки Pillow выполняются ограниченными блоками с проверкой Event/deadline между тайлами и каждыми
8 строками сетки. После истечения срока новые блоки не запускаются; незавершённый JPEG не публикуется.
Слот освобождается после завершения очистки, не открывает вторую работу поверх незавершённой.

В portalgate добавляется cooldown для yandex, общий с получением карт. При 429 netutil.arequest
немедленно возвращает управление с заголовками, без внутреннего ожидания/новой попытки. Gate хранит
retryAfterAt под lock и сохраняет время в отдельном служебном файле кэша (без токенов/тел ответов).
Заголовок Retry-After: число секунд либо HTTP-date в UTC; отрицательное/прошедшее — минимум 1 секунда,
отсутствующее/невалидное — 60 секунд. Будущее время не ограничивается 30 секундами: оно целиком запрещает
следующий запрос, но не удерживает текущий кадр 120 секунд — кадр завершается rate_limited.
Часы UTC переводятся в остаток для монотонного ожидания; после перезапуска время читается заново.
Все места взятия yandex Gate, включая прежние карты, соблюдают cooldown. Разные домены одного источника
не создают независимые разрешения. Для всех вызовов Яндекса сервер при запуске регистрирует в netutil обработчик portal policy
(before_attempt, on_response). yandex_vmap и sat_io передают portal="yandex"; будущий коннектор панорам — тоже.
Обработчик проверяет Gate.cooldown до каждой попытки, а первый 429/503 с Retry-After записывает паузу
и прерывает дальнейшие повторы. Core без зарегистрированного обработчика сохраняет прежнее поведение.
При поднятом cooldown новая попытка, включая внутренний цикл адаптера, завершается rate_limited до сети.
5xx/сетевые сбои без указанной паузы — обычные до трёх попыток с 1/2 секундами,
если они помещаются в оставшийся срок. Retry-After для 503 учитывается тем же правилом cooldown.

Сборка JPEG использует алгоритм главного ТЗ: только нужные тайлы, 64 тайла/16 млн пикселей,
прямолинейная проекция, Pillow MESH. Кэш только проверенных оригинальных JPEG, атомарная запись;
недокачанный кадр не готов. Не загружается страница плеера, интерфейс на кадр не накладывается.

## 6. Общий профиль и этапы

Профиль первого выпуска: до 100 слоёв, 50 000 объектов, 500 выбранных ЗУ, 2000 ОКС,
64 фото, 200 итоговых страниц, 160 МиБ JSON проекта на диске после сериализации.
Существующий предел 400 МиБ остаётся транспортным пределом, а не обещанием подготовки таких проектов.
Контрольные исторические копии: Безобразово около 56,1 МБ/57 слоёв/13 871 объекта;
Гольяново около 21,1 МБ/22 слоёв/1060 объектов. Это размер сохранённых копий, не замер скорости.

Подготовка выполняет один тяжёлый этап за раз, один кадр, один экспорт; одновременно PDF/PPTX не рендерятся.
Бюджет процесса — RSS не выше 1,5 ГиБ сверх чистого запущенного сервера; клиентский heap не выше 768 МиБ
сверх пустого проекта. Сборка без сети и экспорт каждого формата: 180 секунд; общий автоматический
сетевой план: 30 минут активного времени, без ожидания разрешённой паузы пользователя/источника.
На один кадр 120 секунд, на план фото не больше 16 поисков. Общий кэш панорам нового пространства:
512 МиБ с LRU только этого пространства; текущий JPEG проекта от кэша не зависит. Существующие
квоты проектов/источников сохраняются. Размеры/количества проверяются до старта, после получения и перед commit;
при превышении — budget_exceeded, исходный альбом сохранён, ни строки, ни фото не отбрасываются.

Замеры RSS/heap и времени выполняются на описанной в отчёте машине на граничном искусственном проекте
и двух копиях, а не считаются выполненными по факту наличия констант. Если граница не проходит,
функция не объявляется готовой: оптимизировать в этих пределах либо вынести изменение профиля владельцу.
Обычный план данных не превращает слой города в 50 000 случайных объектов: ограничение применяется
к сохраняемому результату после честного получения и обрезки объявленной областью, не к ложному полному охвату.

| Этап | Состав | Условие выхода |
|---|---|---|
| 1. Контракт и сохранение | preparation.py/js, acquisition, web/app/project, UI data/collab, источники, контрольные версии local/hub, защита клиентов | пустой/частичный исход; файл/iframe/hub round-trip; CAS, снимок и restore при отказах; старый клиент не перезаписывает |
| 2. Запуск и обмен | albumapi, albumhost, lease, ACK/NACK, staging/commit, UI подготовки | повтор команды, две вкладки, смена проекта, поздний ответ, отмена и открытие после сбоя |
| 3. Тематические материалы | mytishchi, таблицы/карточки/показатели, образование/медицина, каноническая вёрстка | все строки матрицы, общая нумерация, пропуски/исключения, переполнение и прежние наборы |
| 4. Фото | OSM schema2, netutil.arequest, cooldown Gate, panorama API/проекция/замена | синтетические направления/стык, тайм-аут/429/отмена, кэш и собственное фото; живая проверка отдельно |
| 5. Полный путь | AlbumPanel, единая спецификация PDF/PPTX, упаковка/проверки | полный gate с types/UI/E2E, установленная программа, два проекта, все страницы просмотрены и album_check |

До выхода этапа 5 новый набор скрыт production feature flag `sushpolMytishchi=false`; в изолированных
тестах его включают явно. Каждый этап собирается и проходит свои проверки; старые наборы доступны.
Частичная реализация не выдаётся пользователю за готовую автоматическую презентацию.

## 7. Дополнение перечня файлов и проверок

Это изменения сверх перечня главного ТЗ, а не новый движок.

| Путь | Дополнение |
|---|---|
| apps/grado2/web/app.js | loadKeys передаёт корреляцию, получает acquisition, возвращает исход, публикует данные+подтверждение атомарно |
| apps/grado2/web/project.js | acquisitionRefs в сериализации, неизвестные поля и requiredCapabilities |
| apps/grado2/ui/src/collab.js | acquisitionRefs в DATA_F и неизменяемая единица публикации нового набора |
| apps/grado2/preparation.py | общий recovery-журнал/проверка ревизий, безопасные серверные пути stage, повторная публикация пары файлов |
| apps/grado2/hub.py | lease acquire/renew/release и CAS, forced checkpoint, idempotent commit/status/restore, capability registry в metadata |
| apps/grado2/server.py | revision API и установка portal policy; local те же операции; hub делегирование; маршруты cancel/status; проверка всех путей записи |
| apps/grado2/portalgate.py | общий cooldown yandex, deadline/cancel ожидания, сохранение retryAfterAt |
| core/connectors/grado_connectors/netutil.py | arequest, общий deadline/cancel, AsyncRetrying, обработка Retry-After для нового API без изменения умолчаний старых вызовов |
| apps/grado2/sat_io.py и core/connectors/grado_connectors/yandex_vmap.py | передавать portal="yandex", соблюдать общую паузу до любой внутренней попытки |
| core/connectors/grado_connectors/osm.py | нужные теги, osmSchema=2 и отдельный ключ обновлённого кэша |
| apps/grado2/web/analysis.js | экспорт единого resolver SERVICES для нового набора, прежние NRadius/NWalk без смены метода |
| apps/grado2/tests/test_hub.py | два старта, capability downgrade, forced snapshot, commit/status, CAS/restore; остановка между каждым шагом журнала/двумя replace и recovery при первом чтении |
| apps/grado2/tests/test_server.py | local аналоги и crash recovery, квота/сбой записи, повтор commandId после потери ACK |
| apps/grado2/tests/collab_test.js | данные+acquisitionRefs+Preparation через split/join обоих интерфейсов |
| core/connectors/tests/test_netutil.py | общий deadline, отмена AsyncClient, 429/503 Retry-After число/дата/невалидный/отсутствует |
| apps/grado2/tests/test_portalgate.py | две вкладки/карты и панорама соблюдают один cooldown, перезапуск и отмена ожидания |

Файлы будущих чистых тестов JS общей части перечислены главным ТЗ. Дополнительно в них проверяются
повторяемость серверных ревизий после JS/Python round-trip, область инвалидирования, exact threshold 15°, MultiPolygon/holes,
фильтры дорог и сравнение граничных 100/250 м. Все проверки не используют рабочие проекты и порт 8650.
