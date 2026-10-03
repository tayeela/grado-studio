// Отдельный запуск шага T6: node driver.mjs <url> t6_reserve_solo.mjs  (снимки — в E2E_SHOTS)
import t6 from "./t6_reserve.mjs";
import t6b from "./t6_exampleb.mjs";
const check = (cond, msg) => { if (!cond) throw new Error("не выполнено: " + msg); console.log("ok -", msg); };
export default async p => {
  await p.ev(`$("bExample").click(); await new Promise(r=>setTimeout(r,2500)); const pn=RESULT.placeNode; pn.properties.run=true; pn._ck=null; recompute(true); await new Promise(r=>setTimeout(r,3500)); return 1`);
  await t6b(p, check, process.env.E2E_SHOTS);
  await t6(p, check, process.env.E2E_SHOTS);
};
