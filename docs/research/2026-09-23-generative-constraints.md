# Generative design under spatial constraints — research notes (23.09.2026)

Research run by a Sonnet agent for ГРАДО 2. Paywalled sources were read from abstracts only and are
marked; verify before citing in documents.

## Approaches
1. **Geometric envelopes** (ground truth): buildable area/volume as a Boolean of setbacks, height
   limits, ЗОУИТ and light rules. Knowles solar envelope: extrude "no-shade boundaries" along the
   reverse sun vector for the cutoff hours, intersect over all sampled hours.
2. **Growth until a constraint** (PIK Digital): split the site into cells, raise each by one floor,
   re-test insolation of existing neighbours, freeze the cell on violation.
3. **Multi-objective search** (NSGA-II / Wallacei / Forma / Delve) only inside the feasible region.
4. **ML (GAN, diffusion, RL)**: inspiration only — no Moscow training data, not verifiable for norms.

Consensus: hard geometry first, optimization inside it.

## Key sources
- PIK Digital, «Инсоляционный массинг, или как выращивать здания», Habr —
  https://habr.com/ru/companies/pik_digital/articles/871714/ — the most directly reusable algorithm;
  "insolation front" of hypothetical windows along neighbours' perimeters when layouts are unknown;
  known flaws: order-dependent greedy growth, the new building's own insolation is not checked.
- ГОСТ Р 57795-2017, methods of insolation calculation — http://docs.cntd.ru/document/1200157352
- СанПиН 1.2.3685-21, table 5.58 — central zone 2 h continuous, 22.04–22.08; intermittent: one
  interval ≥ 1 h, total +0.5 h — http://docs.cntd.ru/document/573500115
- МГСН 2.05-99 — http://docs.cntd.ru/document/1200003451
- Шмаров, Земцов, Коркина, «Инсоляция: практика нормирования и расчёта», Жилищное строительство,
  2016 — https://cyberleninka.ru/article/n/insolyatsiya-praktika-normirovaniya-i-rascheta
- МАрхИ, Поповский, пособие по расчёту инсоляции (hand-worked cases for validation) —
  https://marhi.ru/fpkp/doc/20-21/Raschet_Insolyatsii_Posobie_MArkhI_Popovskiy.pdf
- СП 42.13330.2016 п. 7.1 — 15/20 m between long sides, 10 m long side to end with windows; can be
  reduced when insolation, daylight, fire and privacy are proven by calculation —
  https://docs.cntd.ru/document/456054209/titles/1GSMAJQ
- Ladybug Solar Envelope (MIT, readable Python to port) —
  https://github.com/ladybug-tools/ladybug-grasshopper/blob/master/ladybug_grasshopper/src/LB%20Solar%20Envelope.py
- Sepúlveda & De Luca, solar envelope from solar ordinances, Building Simulation 2019 (abstract only) —
  https://link.springer.com/article/10.1007/s12273-019-0561-1
- «From Envelope to Layout…», CAADRIA ~2017 (authorship unverified) —
  https://www.researchgate.net/publication/319165660
- NSGA-II in operative generative design, Automation in Construction 2023 —
  https://www.sciencedirect.com/science/article/pii/S0926580523002868
- Urban block form MOO, Nanjing, Buildings (MDPI, open access) 2022 — https://www.mdpi.com/2075-5309/12/10/1710
- Zheng et al., DRL spatial planning of communities, Nature Computational Science 2023 —
  https://doi.org/10.1038/s43588-023-00503-5 (code: github.com/tsinghua-fib-lab/DRL-urban-planning)
- Deep Umbra (sunlight access by GAN), arXiv 2402.17169 — preview heatmaps only.
- Giraffe (browser GIS + generative) — https://www.giraffe.build/architects/ — closest product to study.
- CityEngine CGA zoning rules (parcel → setback → extrude → subdivide) —
  https://doc.arcgis.com/en/cityengine/latest/tutorials/tutorial-16-urban-planning.htm

## Gaps and risks
- No research treats ЗОУИТ as a generative problem: it is plain data exclusion (parcel − ⋃ ЗОУИТ).
- Expertise expects ГОСТ Р 57795-2017 results from established tools (СИТИС:Солярис); a statutory
  certification requirement for the software was not found. ГРАДО gives a design-stage estimate and
  must say so; validate against the МАрхИ worked cases.
