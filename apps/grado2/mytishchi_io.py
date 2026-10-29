"""ГРАДО 2 · компоновки мытищинского набора на действующем печатном ядре.

Одна сцена для UI, PDF и PPTX. Размеры из паспорта; перенос по метрикам шрифта
с Unicode grapheme clusters без уменьшения кегля. Проверки: tests/test_mytishchi_io.py.
"""
from __future__ import annotations

import base64
import io
import json
import math
import sys
from pathlib import Path

import regex
from PIL import Image
from grado_layout.model import Frame
from grado_render import hex_to_rgb

from album_io import PT, _text, _tw, _header
from preparation import PreparationError

_ROOT = Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
LAYOUT = json.loads((_ROOT/"docs/standards/albums/mytishchi-layout-v1.json").read_text())
BLOCKS = {s["kind"]:{b["role"]:b for b in s["blocks"]} for s in LAYOUT["sheets"]}


def wrap(text, width, pt=8, family="sans"):
    """Сохраняет все символы; слишком длинный токен делится только между графемами."""
    if width<=0:
        raise PreparationError("layout_overflow","Нет ширины для текста")
    lines=[]
    for paragraph in str(text).replace("\r\n","\n").replace("\r","\n").split("\n"):
        current=""
        for word in regex.findall(r"\S+\s*|\s+",paragraph):
            if _tw(current+word,family,pt*PT)<=width:
                current+=word
                continue
            if current:
                lines.append(current.rstrip());current=""
            for cluster in regex.findall(r"\X",word):
                if _tw(cluster,family,pt*PT)>width:
                    raise PreparationError("layout_overflow","Одна графема не помещается в строку")
                if current and _tw(current+cluster,family,pt*PT)>width:
                    lines.append(current.rstrip());current=""
                current+=cluster
        lines.append(current.rstrip())
    return lines or [""]


def text_pages(texts, rect, pt=8):
    """Строки с постоянными ключами; длинная карточка также получает продолжения."""
    _,_,w,h=rect;lead=pt*PT*1.15
    capacity=math.floor((h-1.4)/lead)
    if capacity<1:raise PreparationError("layout_overflow","Нет места даже для одной строки")
    pages=[];current=[]
    for item in texts:
        key,text=item["key"],item["text"]
        for n,line in enumerate(wrap(text,w-2,pt)):
            if len(current)==capacity:
                pages.append(current);current=[]
            current.append({"key":key,"text":line,"first":n==0})
        if len(current)<capacity:current.append({"key":key,"text":"","first":False})
    if current:pages.append(current)
    return pages or [[]]


def table_pages(rows, headers, widths, rect, pt=11, padding=1):
    """Перенос по измеренной высоте в миллиметрах; длинные строки сохраняют ключи."""
    lead=pt*PT*1.15
    header=[wrap(v,w-2*padding,pt,"sans-bold") for v,w in zip(headers,widths)]
    head_height=max(map(len,header),default=1)*lead+1.4
    available=rect[3]-head_height
    if available<lead+1.4:raise PreparationError("layout_overflow","Заголовок таблицы не оставляет места строке")
    pages=[];current=[];remaining=available
    repeat_columns=[0]+[i for i,h in enumerate(headers) if "Кадастров" in h]
    for row in rows:
        cells=[wrap(v,w-2*padding,pt) for v,w in zip(row["values"],widths)]
        count=max(map(len,cells),default=1);offset=0
        while offset<count:
            if count*lead+1.4<=available and count*lead+1.4>remaining:
                pages.append(current);current=[];remaining=available
            marker_col=max(range(len(widths)),key=lambda i:widths[i])
            marker=wrap("(продолжение)",widths[marker_col]-2*padding,pt) if offset else []
            take=min(count-offset,math.floor((remaining-1.4+1e-9)/lead)-len(marker))
            continuation={}
            if offset:
                for col in repeat_columns:
                    text=str(row["values"][col])
                    continuation[col]=wrap(text,widths[col]-2*padding,pt)
            need=max([1,*[len(v) for v in continuation.values()]])
            if take<1 or need*lead+1.4>remaining:
                if not current:raise PreparationError("layout_overflow","Нет прогресса переноса таблицы")
                pages.append(current);current=[];remaining=available
                continue
            sliced=[v[offset:offset+take] for v in cells]
            for col,value in continuation.items():sliced[col]=value
            if marker:sliced[marker_col]=marker+sliced[marker_col]
            height=max(take+len(marker),need)*lead+1.4
            current.append({"key":row["key"],"offset":offset,"height":height,"cells":sliced})
            offset+=take;remaining-=height
    if current:pages.append(current)
    return {"headers":header,"widths":widths,"pt":pt,"padding":padding,"headHeight":head_height,"pages":pages or [[]]}


class TextBlock(Frame):
    def __init__(self,rect,lines,pt=8,bold=False):
        super().__init__(rect);self.lines=lines;self.pt=pt;self.bold=bold
    def ops(self,ctx):
        x,y,w,h=self.rect;out=[];lead=self.pt*PT*1.15
        for i,line in enumerate(self.lines):
            text=line.get("text","") if isinstance(line,dict) else str(line)
            out.append(_text(x+1,y+.7+self.pt*PT+i*lead,self.pt,text,family="sans-bold" if self.bold else "sans"))
        return out


class TableBlock(Frame):
    def __init__(self,rect,table,rows):
        super().__init__(rect);self.table=table;self.rows=rows
    def ops(self,ctx):
        x,y,w,h=self.rect;pt=self.table["pt"];lead=pt*PT*1.15;out=[]
        def line(a,b,c,d):
            return {"op":"path","rings":[[(a,b),(c,d)]],"closed":False,"fill":None,"stroke":(.2,.2,.2),"width":.15,"dash":None}
        entries=[{"cells":self.table["headers"],"height":self.table["headHeight"]},*self.rows]
        yy=y
        for n,row in enumerate(entries):
            cx=x
            for width,cell in zip(self.table["widths"],row["cells"]):
                for k,text in enumerate(cell):
                    out.append(_text(cx+self.table.get("padding",1),yy+.7+pt*PT+k*lead,pt,text,family="sans-bold" if n==0 else "sans"))
                out.append(line(cx,yy,cx,yy+row["height"]));cx+=width
            out.extend([line(cx,yy,cx,yy+row["height"]),line(x,yy,cx,yy),line(x,yy+row["height"],cx,yy+row["height"])])
            yy+=row["height"]
        return out


class Decoration(Frame):
    def __init__(self,page,sheet,meta):
        super().__init__((0,0,*page.size));self.sheet=sheet;self.meta=meta
    def ops(self,ctx):
        sh,m=self.sheet,self.meta;kind=sh["mytishchiKind"];blocks=BLOCKS[kind];out=[]
        if kind=="title":
            x,y,w,h=blocks["cover_title"]["rect"]
            lines=wrap(m.get("object") or m.get("name") or "Существующее положение",w,36,"sans-bold")
            if len(lines)*36*PT*1.15>h-20:raise PreparationError("layout_overflow","Титул не помещается в блок")
            place=wrap(m.get("place") or "",w,28)
            total=len(lines)*36*PT*1.15+(len(place)*28*PT*1.15+5 if m.get("place") else 0)
            if total>h:raise PreparationError("layout_overflow","Название и район не помещаются на титуле")
            top=y+h-total
            out+=TextBlock((x,top,w,h),lines,36,True).ops(ctx)
            if m.get("place"):
                out+=TextBlock((x,top+len(lines)*36*PT*1.15+5,w,h),place,28).ops(ctx)
            yr=blocks["year"]["rect"]
            out+=TextBlock(yr,[str(m.get("year") or "")],12).ops(ctx)
        else:
            header=_header()
            out.append({"op":"path","rings":[[(0,0),(page_width:=self.rect[2],0),(page_width,27.8),(0,27.8)]],
                        "closed":True,"fill":(.95,.95,.95),"stroke":None,"width":0,"dash":None})
            if header:out.append({"op":"image","data":header,"x":0,"y":0,"w":265.1,"h":27.8})
            short=m.get("short") or m.get("object") or ""
            header_lines=wrap(short,145,14,"sans-bold")
            if len(header_lines)>2:raise PreparationError("layout_overflow","Краткое название проекта не помещается в шапку")
            out+=TextBlock((268,5,145,20),header_lines,14,True).ops(ctx)
            box=blocks["title"]["rect"];lines=wrap(sh["title"],box[2]-2,18,"sans-bold")
            if len(lines)>2:raise PreparationError("layout_overflow","Заголовок длиннее двух строк")
            out+=TextBlock(box,lines,18,True).ops(ctx)
            r=blocks["page_number"]["rect"]
            out+=TextBlock(r,[str(sh.get("pageNo") or "")],12).ops(ctx)
        if sh.get("draft"):
            out.append(_text(24,15 if kind=="title" else 292,8,"Черновик",(.65,.2,.15),"sans"))
        return out


class PhotoBlock(Frame):
    def __init__(self,rect,photo,number):
        super().__init__(rect);self.photo=photo;self.number=number
    def ops(self,ctx):
        x,y,w,h=self.rect;p=self.photo
        if not p.get("data"):return []
        try:
            raw=base64.b64decode(p["data"],validate=True)
            with Image.open(io.BytesIO(raw)) as im:
                iw,ih=im.size;im.verify()
        except (ValueError,OSError):
            raise PreparationError("layout_overflow","Файл фотографии повреждён") from None
        ratio=min(w/iw,(h-6)/ih);dw,dh=iw*ratio,ih*ratio
        return [{"op":"image","x":x+(w-dw)/2,"y":y+(h-6-dh)/2,"w":dw,"h":dh,"data":raw},
                _text(x+1,y+h-1.5,8,str(self.number),family="sans")]


def build_frames(page,sh,meta,lib,lgr_dash,tiles,map_frame):
    kind=sh["mytishchiKind"];blocks=BLOCKS[kind];frames=[]
    for part in sh.get("maps") or []:
        rect=blocks[part["role"]]["rect"]
        frames.append(map_frame(tuple(rect),part["sheet"]))
    for role,lines in (sh.get("textBlocks") or {}).items():
        frames.append(TextBlock(blocks[role]["rect"],lines,8))
    for role,value in (sh.get("tables") or {}).items():
        frames.append(TableBlock(blocks[role]["rect"],value,value["rows"]))
    for i,p in enumerate(sh.get("photos") or []):
        frames.append(PhotoBlock(blocks[f"photo_{i+1}"]["rect"],p,p.get("number",i+1)))
    frames.append(Decoration(page,sh,meta))
    return frames
