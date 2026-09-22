/** Вызовы ядра. Текст ошибки для человека короткий, журнал сервера остаётся ASCII. */

async function fail(response) {
  let message = "Команда не выполнена";
  try {
    const data = JSON.parse(await response.text());
    const known = {
      "extent too large": "Область слишком большая, приблизьте вид",
      "project preflight failed": "Предпроверка не пройдена",
      "login required": "Нужен вход",
      "only http and https urls are allowed": "Допустимы только ссылки http и https",
      "downloaded file is too large": "Скачиваемый файл слишком большой",
      "url download failed": "Не удалось скачать файл",
      "bad uin": "Неверный УИН",
    };
    if (data.error && known[data.error]) message = known[data.error];
    const title = data.report && data.report.errors && data.report.errors[0]
      && data.report.errors[0].title;
    if (title) message = title;
  } catch {
    /* тело не JSON */
  }
  const error = new Error(message);
  error.status = response.status;
  throw error;
}

export async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await fail(response);
  return response.json();
}

export async function postBlob(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) await fail(response);
  const blob = await response.blob();
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "");
  return { blob, filename: match ? match[1] : "grado.bin" };
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(url);
  }, 1500);
}
