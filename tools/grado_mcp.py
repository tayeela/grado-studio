#!/usr/bin/env python3
"""MCP-доступ к ГРАДО 2: инструменты подготовки презентации через проверяемый HTTP API.

Официальный Python SDK, stdio; файлы сохраняются только в настроенную папку результатов.
Запуск и настройки: docs/guides/grado-mcp.md. Проверки: apps/grado2/tests/test_grado_mcp.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from mcp.server.fastmcp import FastMCP


class GradoClient:
    def __init__(self, url=None, token_file=None, outputs=None, uploads=None, cookie_file=None, transport=None):
        self.url = (url or os.environ.get("GRADO_MCP_URL") or "http://127.0.0.1:8667").rstrip("/")
        parsed = urlsplit(self.url)
        try:
            local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        except (ValueError, TypeError):
            local = False
        if (parsed.scheme not in ("http", "https") or parsed.scheme == "http" and not local or
                not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
            raise ValueError("Нужен адрес https сервера либо http loopback, без пути/секретов в URL")
        self.outputs = Path(outputs or os.environ.get("GRADO_MCP_OUTPUTS") or Path.home()/"Downloads"/"ГРАДО — результаты агента").expanduser().resolve()
        self.uploads = Path(uploads or os.environ.get("GRADO_MCP_UPLOADS") or self.outputs/"загрузка").expanduser().resolve()
        headers = {"X-Grado-Project-Capabilities":"sushpol-v1"}
        for key, p in (("X-Grado-Token",token_file or os.environ.get("GRADO_MCP_TOKEN_FILE")),
                       ("Cookie",cookie_file or os.environ.get("GRADO_MCP_COOKIE_FILE"))):
            if p:
                value = Path(p).expanduser().read_text().strip()
                if "\n" in value or "\r" in value:
                    raise ValueError("Файл доступа должен содержать одну строку")
                headers[key] = value
        self.http = httpx.AsyncClient(base_url=self.url, headers=headers, timeout=60, follow_redirects=False,
                                      transport=transport)

    async def request(self, method, route, payload=None, params=None):
        response = await self.http.request(method,route,json=payload,params=params)
        if response.status_code >= 400:
            try:
                error=response.json()
                message=error.get("error") or error.get("message") or "Запрос отклонён"
                code=error.get("reasonCode") or str(response.status_code)
            except (ValueError,AttributeError):
                message,code="Сервер не вернул проверяемый JSON",str(response.status_code)
            raise ValueError(f"ГРАДО {code}: {str(message)[:350]}")
        try:
            return response.json()
        except ValueError:
            raise ValueError("ГРАДО вернул неизвестный формат ответа") from None

    async def export(self, project_id, run_id, format, draft=False):
        UUID(run_id)
        if format not in ("pdf","pptx"):
            raise ValueError("Формат должен быть pdf или pptx")
        # Имя не берётся из проекта/Content-Disposition: путь не управляется порталом или моделью.
        name=hashlib.sha256(project_id.encode()).hexdigest()[:16]+"-"+run_id+"."+format
        self.outputs.mkdir(parents=True,exist_ok=True)
        path=self.outputs/name
        tmp=path.with_name("."+path.name+"."+uuid4().hex+".part")
        digest=hashlib.sha256();size=0;prefix=b""
        try:
            async with self.http.stream("GET","/api/preparation/export",params={"projectId":project_id,
                                       "runId":run_id,"format":format,"draft":"1" if draft else "0"},timeout=200) as response:
                if response.status_code!=200:
                    raise ValueError(f"ГРАДО не разрешил выгрузку: HTTP {response.status_code}")
                with tmp.open("wb") as f:
                    async for chunk in response.aiter_bytes():
                        if len(prefix)<8:prefix=(prefix+chunk)[:8]
                        size+=len(chunk)
                        if size>200*2**20:raise ValueError("Файл превышает предел скачивания 200 МиБ")
                        digest.update(chunk);f.write(chunk)
                    f.flush();os.fsync(f.fileno())
                if not (prefix.startswith(b"%PDF-") if format=="pdf" else prefix.startswith(b"PK\x03\x04")):
                    raise ValueError("Сервер вернул не файл выбранного формата")
                os.replace(tmp,path)
        finally:
            tmp.unlink(missing_ok=True)
        return {"file":str(path),"sha256":digest.hexdigest(),"bytes":size,"format":format,"draft":draft,
                "projectId":project_id,"runId":run_id}

    async def replace_photo(self, project_id, photo_id, upload_name, point, azimuth_deg, confirm_previous):
        import base64
        path=(self.uploads/upload_name).resolve()
        if not path.is_relative_to(self.uploads) or not path.is_file():
            raise ValueError("Изображение должно находиться внутри папки загрузки MCP")
        if path.stat().st_size>20*2**20:
            raise ValueError("Изображение больше 20 МиБ")
        return await self.request("POST","/api/preparation/photo",{"projectId":project_id,"photoId":photo_id,
            "image":base64.b64encode(path.read_bytes()).decode("ascii"),"name":path.name,"point":point,
            "azimuthDeg":azimuth_deg,"confirmPrevious":confirm_previous})


def create_mcp(client=None):
    # Отложенное создание HTTP-клиента: импорт/список функций не читают файлы доступа.
    current=[client]
    def api():
        if current[0] is None:current[0]=GradoClient()
        return current[0]
    mcp=FastMCP("grado",instructions="ГРАДО 2: сначала прочитайте статус проекта. Подготовка получает слои внутри программы. "
                "Сохраняйте command_id для повтора. После старта проверяйте статус с wait_seconds=10. "
                "Не называйте черновик готовым. Проблемы источников не подменяйте выдуманными значениями.")

    @mcp.tool()
    async def grado_health() -> dict:
        """Проверить соединение и возможности ГРАДО, без доступа к секретам."""
        return await api().request("GET","/api/agent/health")

    @mcp.tool()
    async def grado_list_projects() -> dict:
        """Доступные проекты: только краткий каталог без геометрии."""
        return await api().request("GET","/api/agent/projects")

    @mcp.tool()
    async def grado_create_project(name: str, territory: dict, coordinates: str="wgs84") -> dict:
        """Создать новый проект по Polygon/MultiPolygon, coordinates=wgs84 или msk. Исходные слои не нужны."""
        return await api().request("POST","/api/agent/project",{"name":name,"territory":territory,"coordinates":coordinates})

    @mcp.tool()
    async def grado_project_status(project_id: str) -> dict:
        """Посмотреть область, состав слоёв/листов и проблемы проекта без полной геометрии."""
        return await api().request("GET","/api/preparation/status",params={"projectId":project_id})

    @mcp.tool()
    async def grado_prepare_presentation(project_id: str, command_id: str, refresh: bool=True, photos: bool=True,
                                          resume_run_id: str|None=None) -> dict:
        """Начать сборку презентации по мытищинскому образцу. command_id — UUID, сохранять для безопасного повтора.
        После budget_exceeded или обрыва повторяйте с refresh=false: полученные источники берутся из квитанций,
        докачивается только недостающее; полученные слои заново не скачиваются."""
        UUID(command_id)
        return await api().request("POST","/api/preparation/start",{"projectId":project_id,
                  "commandId":command_id,"refresh":refresh,"photos":photos,"resumeRunId":resume_run_id})

    @mcp.tool()
    async def grado_preparation_status(project_id: str, run_id: str|None=None, command_id: str|None=None,
                                       wait_seconds: int=10) -> dict:
        """Дождаться обновления до 15 секунд: этапы, готовность и причины недостатков. command_id разрешает потерянный ответ start."""
        params={"projectId":project_id,"wait":min(15,max(0,wait_seconds))}
        if run_id:params["runId"]=run_id
        if command_id:params["commandId"]=command_id
        return await api().request("GET","/api/preparation/status",params=params)

    @mcp.tool()
    async def grado_preparation_issues(project_id: str, run_id: str, offset: int=0, limit: int=25) -> dict:
        """Прочитать конкретные недостатки с objectKey/field для уточнения. Без геометрии и изображений."""
        return await api().request("GET","/api/preparation/issues",params={"projectId":project_id,"runId":run_id,
                                   "offset":max(0,offset),"limit":min(100,max(1,limit))})

    @mcp.tool()
    async def grado_cancel_preparation(project_id: str, run_id: str) -> dict:
        """Остановить подготовку, сохранив принятые данные и прежний альбом."""
        return await api().request("POST","/api/preparation/cancel",{"projectId":project_id,"runId":run_id})

    @mcp.tool()
    async def grado_export_presentation(project_id: str, run_id: str, format: str, draft: bool=False) -> dict:
        """Скачать PDF/PPTX одной версии в папку результатов. Неполный комплект требует явного draft=true."""
        return await api().export(project_id,run_id,format,draft)

    @mcp.tool()
    async def grado_resolve_field(project_id: str, expected_project_revision: str, source_key: str,
                                   object_key: str, field: str, basis: str, action: str="value",
                                   value: str|float|None=None) -> dict:
        """Уточнить поле объекта либо принять отсутствие/неприменимость по явному основанию. Не выдумывать сведения. После изменения повторить подготовку refresh=false."""
        return await api().request("POST","/api/preparation/field",{"projectId":project_id,
            "expectedProjectRevision":expected_project_revision,"sourceKey":source_key,"objectKey":object_key,
            "field":field,"basis":basis,"action":action,"value":value})

    @mcp.tool()
    async def grado_replace_photo(project_id: str, photo_id: str, upload_name: str,
                                   point: list[float]|None=None, azimuth_deg: float|None=None,
                                   confirm_previous: bool=False) -> dict:
        """Заменить кадр своим изображением из папки загрузки MCP, сохранив id. Точку/направление задать или явно подтвердить прежние."""
        return await api().replace_photo(project_id,photo_id,upload_name,point,azimuth_deg,confirm_previous)

    return mcp


if __name__=="__main__":
    create_mcp().run(transport="stdio")
