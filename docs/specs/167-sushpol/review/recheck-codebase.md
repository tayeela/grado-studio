# Повтор стадии 9 — Codebase Details

Рецензент /root/recheck167_codebase, изолирован, только чтение. Один ограниченный повтор.
**Вердикт: 2 Major, Blocker не обнаружен.**

1. **Major — не задан серверный протокол lease.** implementation-contract.md:141–169:
   albumapi имеет start/resume/stop, но нет API выдачи/продления/освобождения серверного lease,
   тел/ответов и реакции на потерю heartbeat. Существующий albumhost.js:120–137 вызывает JavaScript iframe,
   не серверную команду старта. Нужно задать acquire/renew/release и корреляцию ownerClientId/runId.
2. **Major — не определено восстановление атомарного commit.** implementation-contract.md:194–208:
   проект, rev/generation и долговечная идемпотентность обещаны как единая запись, но hub.py:1204–1207
   отдельно заменяет project.grado2 и meta.json. Падение между ними оставляет новый проект со старой rev
   и без результата commandId. Один lock не устраняет это; нужен механизм восстановления пары файлов
   и проверка отказа между публикациями, включая commit-status/повтор commandId.

## Обязательные чтения и ограничения

Persona и implementation-readiness-standard полностью; детальный раздел и ранние контракты ТЗ;
все три контрактных Markdown-приложения, весь layout-v1.json, reference-passport, source-evidence,
panorama-download-check; структура reference-layout.json. Указанные в задании кодовые пути сопоставлены
с планом. Будущие изменения не оценивались как уже существующий механизм. Другие отчёты/память/разговор
не читались; правок, сборок и внешних сообщений не было.

## Применённые после отчёта исправления

Оба замечания — PROPOSE FIX, severity сохранена. В implementation-contract.md добавлены:

- «Серверный lease: acquire, renew, release»: POST /api/preparation/lease, полные запрос/ответ,
  leaseId, корреляция/пользователь, срок 30 секунд, heartbeat 10 секунд, отказ/таймаут 5 секунд,
  прекращение работы и явный resume, вызовы albumhost перед iframe и release после остановки.
- «Долговечная публикация двух файлов»: неизменяемый stage project.next/meta.next,
  журнал pending.json перед публикацией, SHA256/fsync, последовательные атомарные замены,
  roll forward перед любым чтением/записью, commit-status/idempotence, пределы защиты и аварийные тесты.

Это документированные исправления родительским агентом, не второй положительный вердикт Codebase.
Вторая независимая перепроверка этой роли не проводилась.
