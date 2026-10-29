"""Настоящий stdio MCP-клиент → HTTP-сервер ГРАДО; секреты и геометрия не выходят в ответы статуса."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as S
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_preparation_api import TERRITORY

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from grado_mcp import GradoClient


class ClientBoundaries(unittest.TestCase):
    def test_rejects_remote_plaintext_and_url_secrets(self):
        for url in ['http://example.com','https://user:secret@example.com','https://example.com/key','https://example.com?secret=x']:
            with self.subTest(url=url),self.assertRaises(ValueError):GradoClient(url=url)


class MCPRoundtrip(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_and_real_http(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();token=root/'token';token.write_text('test-token-not-for-production');token.chmod(0o600)
            patches=[patch.object(S,'PROJECTS',root/'projects'),patch.object(S,'CACHE',root/'cache'),
                     patch.object(S,'TOKEN',token.read_text()),patch.object(S,'HUB',None),
                     patch.object(S,'esri_tile',lambda *args:None),
                     patch.object(S,'fetch',side_effect=lambda bbox,keys,*args:({},{k:'Нет ответа' for k in keys})),
                     patch('print_io.PRINT_OPS_CACHE',root/'ops'),patch('print_io.TILE_FAIL_DIR',root/'tile-fail')]
            for p in patches:p.start()
            instance=S.Server(('127.0.0.1',0));thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
            try:
                params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'tools'/'grado_mcp.py')],
                    env={**os.environ,'GRADO_MCP_URL':f'http://127.0.0.1:{instance.server_address[1]}',
                         'GRADO_MCP_TOKEN_FILE':str(token),'GRADO_MCP_OUTPUTS':str(root/'outputs')})
                async with stdio_client(params) as (reader,writer):
                    async with ClientSession(reader,writer) as session:
                        await session.initialize()
                        listed=await session.list_tools()
                        self.assertIn('grado_prepare_presentation',{t.name for t in listed.tools})
                        async def call(name,args=None):
                            result=await session.call_tool(name,args or {})
                            self.assertFalse(result.isError,result.content)
                            return result.structuredContent or json.loads(result.content[0].text)
                        health=await call('grado_health');self.assertEqual(health['protocolVersion'],1)
                        project=await call('grado_create_project',{'name':'MCP проверка','territory':TERRITORY})
                        self.assertNotIn('coordinates',json.dumps(project,ensure_ascii=False))
                        command=str(uuid4())
                        args={'project_id':'MCP проверка','command_id':command,'photos':False}
                        run=await call('grado_prepare_presentation',args)
                        again=await call('grado_prepare_presentation',args)
                        self.assertEqual(run['runId'],again['runId'])
                        for _ in range(20):
                            status=await call('grado_preparation_status',{'project_id':'MCP проверка','run_id':run['runId'],'wait_seconds':1})
                            if status['state']!='running':break
                        self.assertEqual(status['state'],'blocked',status)
                        self.assertIn('result',status,status)
                        self.assertEqual(status['result']['kinds'],14)
                        for fmt,magic in [('pdf',b'%PDF-'),('pptx',b'PK\x03\x04')]:
                            result=await call('grado_export_presentation',{'project_id':'MCP проверка','run_id':run['runId'],'format':fmt,'draft':True})
                            path=Path(result['file']);self.assertTrue(path.is_relative_to(root/'outputs'))
                            self.assertTrue(path.read_bytes().startswith(magic))
            finally:
                instance.shutdown();thread.join(timeout=10);instance.server_close()
                for p in reversed(patches):p.stop()


if __name__=='__main__':unittest.main()
