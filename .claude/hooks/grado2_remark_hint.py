#!/usr/bin/env python3
"""UserPromptSubmit hook: владелец пишет про альбом или оформление — напомнить порядок работы (владелец 06.10.2026: «А»).

Слова про листы, подписи, цвета, линии, легенду, слои → в контекст добавляется короткая подсказка: свод правил
docs/wiki/album-rules.md, навык owner-remark (замечание → правило → исправление), навык album-verify (до / после).
Владелец повторял одни и те же замечания: подсказка не даёт начать правку, не сверившись со сводом.
"""
import json
import re
import sys

data = json.load(sys.stdin)
text = str(data.get("prompt") or "").lower()
WORDS = (r"лист|легенд|условн|подпис|цвет|лини|сзз|зоуит|лгр|альбом|презентац|слайд|титул|генплан|сущпол|снимок|"
         r"спутник|фотофикс|дорог|шрифт|кегл|участ|ври|выноск|стрелк|границ")
if re.search(WORDS, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
        "ГРАДО: похоже на замечание по альбому. До правки — docs/wiki/album-rules.md (свод правил владельца); "
        "порядок — навык owner-remark (дословно в OWNER.md → правило в album-rules и label-rules → причина в коде → "
        "навык album-verify «до / после» на копии → gate → коммит); на сайт — только по «выкладывай»."}}, ensure_ascii=False))
sys.exit(0)
