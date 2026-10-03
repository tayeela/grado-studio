# T58 report (v0.99.0 snapshot, ports 8700 / 8701, both stopped by PID)

## 1. PPTX of frozen sheets — PASS with defects
- Import _spec-final.grado2 into example project: 9 sheets, 17 MB. PPTX 8.2 MB in 11.6 s; PDF 7.2 MB (9 pages A3) in 10.6 s.
- Package valid: zipfile testzip OK, all XML/rels well-formed, 9 slides, 1 slide-size 15120000x10692000.
- Each slide carries the sheet title as text (slide 1 is the title page: decree text, not the word "Титульный лист"). Maps = vector shapes (up to 9.6k per slide) plus 1-65 JPEG tiles, 55 KB-ish each.
- LibreOffice render (18 s): 9 pages. Slide 2 vs owner's PDF page 2: same content and layout (both maps, labels, callout, number). Only difference: font Montserrat is not installed here, so LO shows a serif (fonts are not embedded; PowerPoint without Montserrat will do the same).
- Slides 3-9 compared with owner's PDF: same content. Defect: slide 9 (satellite) — photo tiles are not clipped to the map frame; they run past the frame under legend/title (also at normal-album slide 9, so general PPTX defect, not frozen-specific).
## Regression, normal album («Альбом ППТ КРТ» on example)
- Build takes 93 s; it ADDS 9 sheets next to imported ones (18 total) — imp_ sheets are not replaced (by design of prefix, but "заменит листы" may surprise). After removing imp_: PPTX 9 slides, 18 MB, 37 s, valid XML. Toast: sheets 5, 6, 9 "не готовы" (example data).
- Slide 2 of the normal album: 244,222 shapes, 159 MB of XML — LibreOffice did not finish in 9 min (killed). Not checked in PowerPoint.
## 2. Hub, 17 MB album — PASS
- A import: 9 sheets in 0.12 s; push of album section 17,865 KB (17.4 MB), 0.33 s; settle 2.9 s.
- Meta-only edits: example territory 6 KB, ТЭП parameter change 6 KB (album not resent).
- B opens: GET project 19,006 KB in 0.23 s; sheets visible 0.6 s; 9 sheets.
- B renames sheet 3, A adds a sheet simultaneously: server returned one 409, then both changes survived on both sides (10 sheets). Settle 3-6 s. Reload both (0.4-0.5 s): identical albums.
- Console errors: A 0, B 0 (409 filtered by harness as expected).
## Not checked
PowerPoint itself; true parallel edits of the same sheet (conflict choice).
Files: /tmp/grado-team/2026-10-03/t58/ (frozen-album.pptx/.pdf, normal-album.pptx, slide2-pptx-render.png, slide2-owner-pdf.png, slide9-pptx.png, normal-album-contact.png, collab*.log, collab-shots/). Scripts: s1.mjs, s3.mjs, collab58.mjs.
