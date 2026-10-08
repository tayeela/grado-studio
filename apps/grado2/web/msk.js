// @ts-check
/* ГРАДО 2 · рабочая местная система Москвы МСК (как пользовательская СК «МСК» в QGIS владельца) в браузере.
   Перенос core/connectors/grado_connectors/crs.py (msk_to_wgs84 / wgs84_to_msk) один в один: обратный поперечный
   Меркатор на эллипсоиде Бесселя без сдвига начала (+x_0=0 +y_0=0), 7-параметрический Хельмерт (Position Vector),
   WGS84. X — на восток, Y — на север, метры: так же, как в DXF и на листах. Система ГИС ОГД — та же формула со сдвигом
   начала (16,098; 14,512) м, в браузере она не нужна. Сверено с PROJ в tests/test_msk.py (меньше 1 мм). */
(function (root) {
  const R = Math.PI / 180;
  const BA = 6377397.155, BF = 1 / 299.1528128, BE2 = BF * (2 - BF), BEP2 = BE2 / (1 - BE2);
  const LAT0 = 55.66666666667 * R, LON0 = 37.5 * R, K0 = 1.0, X0 = 0, Y0 = 0;     // МСК: начало без сдвига
  const TD = [316.151, 78.924, 589.650], TR = [-1.57273, 2.69209, 2.34693].map(v => v / 3600 * R), TS = 8.4507e-6;
  const WA = 6378137.0, WF = 1 / 298.257223563, WE2 = WF * (2 - WF);
  const arc = (phi, a, e2) => a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * phi)
    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * phi) - (35 * e2 ** 3 / 3072) * Math.sin(6 * phi));
  const M0 = arc(LAT0, BA, BE2);

  // [x восток, y север] МСК → [lon, lat] WGS84, градусы
  function toWgs([east, north]) {
    const a = BA, e2 = BE2, ep2 = BEP2;
    const m = M0 + (north - Y0) / K0, mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256));
    const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
    const p1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
      + (151 * e1 ** 3 / 96) * Math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
    const sp = Math.sin(p1), cp = Math.cos(p1), tp = Math.tan(p1), c1 = ep2 * cp ** 2, t1 = tp ** 2;
    const n1 = a / Math.sqrt(1 - e2 * sp ** 2), r1 = a * (1 - e2) / (1 - e2 * sp ** 2) ** 1.5, d = (east - X0) / (n1 * K0);
    const phi = p1 - (n1 * tp / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
      + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720);
    const lam = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / cp;
    const nn = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
    const x = nn * Math.cos(phi) * Math.cos(lam), y = nn * Math.cos(phi) * Math.sin(lam), z = nn * (1 - e2) * Math.sin(phi);
    const [rx, ry, rz] = TR, ms = 1 + TS;
    const xo = ms * (x - rz * y + ry * z) + TD[0], yo = ms * (rz * x + y - rx * z) + TD[1], zo = ms * (-ry * x + rx * y + z) + TD[2];
    const bw = WA * Math.sqrt(1 - WE2), ep2w = WE2 / (1 - WE2), p = Math.hypot(xo, yo), th = Math.atan2(zo * WA, p * bw);
    const lat = Math.atan2(zo + ep2w * bw * Math.sin(th) ** 3, p - WE2 * WA * Math.cos(th) ** 3), lon = Math.atan2(yo, xo);
    return [lon / R, lat / R];
  }
  // [lon, lat] → [x, y] МСК: обратная задача итерациями Ньютона по прямой цепочке, как в ядре
  function fromWgs([lon, lat]) {
    const kx = 111320.0 * Math.cos(lat * R);
    let e = (lon - LON0 / R) * kx + X0, n = (lat - LAT0 / R) * 110540.0 + Y0;
    for (let i = 0; i < 6; i++) {
      const [lo, la] = toWgs([e, n]); e -= (lo - lon) * kx; n -= (la - lat) * 110540.0;
      if (Math.abs(lo - lon) < 1e-11 && Math.abs(la - lat) < 1e-11) break;
    }
    return [e, n];
  }
  const api = { toWgs, fromWgs };
  if (typeof module === "object" && module.exports) module.exports = api; else root.MSK = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
