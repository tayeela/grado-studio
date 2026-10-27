// Вход по ключу доступа (переменная GRADO2_TOKEN на сервере) или через Telegram (ключи бота GRADO2_TG_*: тогда видна
// только кнопка Telegram). Ключ уходит только в теле POST, не в адрес. Ошибка входа через Telegram приходит как #tg=код.
const f = document.getElementById("f"), t = document.getElementById("t"), b = document.getElementById("b"), msg = document.getElementById("msg");
f.addEventListener("submit", async e => {
  e.preventDefault();
  b.disabled = true;
  msg.textContent = "";
  try {
    const r = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: t.value})});
    if (r.ok) { location.replace("/"); return; }
    msg.textContent = r.status === 429 ? "Слишком много попыток, подождите минуту" : r.status === 401 ? "Неверный ключ" : "Ошибка входа, код " + r.status;
  } catch (err) {
    msg.textContent = "Нет связи с сервером";
  }
  b.disabled = false;
  t.select();
});

const TG_MSG = {
  denied: "Вход в Telegram отменён", unknown: "Этому аккаунту Telegram вход не открыт", expired: "Вход занял больше 10 минут, начните заново",
  state: "Вход прервался, начните заново", token: "Telegram не подтвердил вход, попробуйте ещё раз", net: "Telegram не ответил, попробуйте ещё раз",
  off: "Вход через Telegram на сервере не настроен",
};
const code = (location.hash.match(/tg=([a-z]+)/) || [])[1];
if (code) { msg.textContent = TG_MSG[code] || "Вход не удался"; history.replaceState(null, "", location.pathname); }
fetch("/api/site").then(r => r.ok ? r.json() : null).then(j => {
  if (!j || !j.tg) return;
  if (j.user) { location.replace("/"); return; }
  document.getElementById("tgbox").hidden = false;
  document.getElementById("keybox").hidden = true;
  t.required = false;
}).catch(() => {});
