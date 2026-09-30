// Вход по ключу доступа (включается переменной GRADO2_TOKEN на сервере). Ключ уходит только в теле POST, не в адрес.
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
