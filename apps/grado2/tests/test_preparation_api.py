"""Подготовка через настоящий HTTP: повтор старта, защита старого клиента, черновой экспорт."""
import json
import sys
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as S
import preparation as P
from starlette.testclient import TestClient

TERRITORY={'type':'Polygon','coordinates':[[[37.16,55.34],[37.161,55.34],[37.161,55.341],[37.16,55.341],[37.16,55.34]]]}
HEADERS={'X-Grado-Project-Capabilities':'sushpol-v1'}


class PreparationAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.patches=[patch.object(S,'PROJECTS',self.root/'projects'),patch.object(S,'CACHE',self.root/'cache'),
                      patch('print_io.PRINT_OPS_CACHE',self.root/'ops'),patch('print_io.TILE_FAIL_DIR',self.root/'tile-fail'),patch.object(S,'HUB',None),patch.object(S,'TOKEN',''),patch.object(S,'esri_tile',lambda *args:None),
                      patch.object(S,'fetch',side_effect=lambda bbox,keys,*args: ({},{k:'Источник недоступен' for k in keys}))]
        for p in self.patches:p.start()
        self.client=TestClient(S.APP,base_url="http://127.0.0.1:8667")
        response=self.client.post('/api/agent/project',json={'name':'Проверка','territory':TERRITORY},headers=HEADERS)
        self.assertEqual(response.status_code,200,response.text)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_protected_save_rejects_dropped_schema_and_legacy_client(self):
        body=json.loads((S.PROJECTS/'Проверка.grado2').read_bytes())
        response=self.client.post('/api/project?name=Проверка',json=body)
        self.assertEqual(response.status_code,409,response.text)
        body['album']['meta'].pop('sushpolPreparation')
        response=self.client.post('/api/project?name=Проверка',json=body,headers=HEADERS)
        self.assertEqual(response.status_code,409,response.text)
        reopened=self.client.get('/api/project?name=Проверка').json()
        self.assertIn('sushpolPreparation',reopened['album']['meta'])

    def test_durable_start_idempotence_and_downloads(self):
        command=str(uuid4())
        args={'projectId':'Проверка','commandId':command,'refresh':True,'photos':False}
        first=self.client.post('/api/preparation/start',json=args,headers=HEADERS)
        self.assertEqual(first.status_code,200,first.text)
        rid=first.json()['runId']
        second=self.client.post('/api/preparation/start',json=args,headers=HEADERS)
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['runId'],rid)
        conflict=self.client.post('/api/preparation/start',json={**args,'photos':True},headers=HEADERS)
        self.assertEqual(conflict.status_code,409,conflict.text)
        import sushpol_jobs
        job=sushpol_jobs.service(S).jobs[rid]
        job['thread'].join(timeout=15)
        self.assertFalse(job['thread'].is_alive())
        status=self.client.get('/api/preparation/status',params={'projectId':'Проверка','commandId':command}).json()
        self.assertEqual(status['state'],'blocked',status)
        self.assertEqual(status['result']['kinds'],14,status)
        self.assertGreater(status['report']['total'],0)
        forbidden=self.client.get('/api/preparation/export',params={'projectId':'Проверка','runId':rid,'format':'pdf'})
        self.assertEqual(forbidden.status_code,409,forbidden.text)
        # Raster provider is intentionally offline; draft remains visibly incomplete.
        with patch.object(S,'esri_tile',lambda *args:None),patch('print_io.PRINT_OPS_CACHE',self.root/'ops'),patch('print_io.TILE_FAIL_DIR',self.root/'tile-fail'):
            for fmt,magic in [('pdf',b'%PDF-'),('pptx',b'PK\x03\x04')]:
                response=self.client.get('/api/preparation/export',params={'projectId':'Проверка','runId':rid,'format':fmt,'draft':'1'})
                self.assertEqual(response.status_code,200,response.text[:300] if response.status_code!=200 else '')
                self.assertTrue(response.content.startswith(magic))
        reopened=self.client.get('/api/preparation/status',params={'projectId':'Проверка'}).json()
        self.assertGreaterEqual(len(reopened['sheets']),14)
        # New service instance simulates process restart: command still resolves to same durable run.
        fresh=sushpol_jobs.Runs(S)
        class Context:
            headers=HEADERS
            @staticmethod
            def who():return None
        reused=fresh.start(Context(),args)
        self.assertEqual(reused['runId'],rid)
        self.assertTrue(reused['reused'])

    def test_cancelled_first_import_leaves_downloadable_partial_draft(self):
        entered=threading.Event();release=threading.Event()
        def wait(bbox,keys,*args):
            entered.set();release.wait(5)
            return {},{k:"Нет ответа" for k in keys}
        with patch.object(S,"fetch",wait):
            response=self.client.post('/api/preparation/start',json={'projectId':'Проверка','commandId':str(uuid4()),'photos':False},headers=HEADERS)
            self.assertEqual(response.status_code,200,response.text)
            rid=response.json()['runId'];self.assertTrue(entered.wait(5))
            cancelled=self.client.post('/api/preparation/cancel',json={'projectId':'Проверка','runId':rid},headers=HEADERS)
            self.assertEqual(cancelled.status_code,200)
            release.set()
            import sushpol_jobs
            sushpol_jobs.service(S).jobs[rid]['thread'].join(timeout=8)
            status=self.client.get('/api/preparation/status',params={'projectId':'Проверка','runId':rid}).json()
            self.assertEqual(status['state'],'cancelled',status)
            self.assertTrue(status['candidateSHA256'])
            self.assertTrue(status['result']['partial'])
            result=self.client.get('/api/preparation/export',params={'projectId':'Проверка','runId':rid,'format':'pdf','draft':'1'})
            self.assertEqual(result.status_code,200)
            self.assertTrue(result.content.startswith(b'%PDF-'))


if __name__=='__main__':unittest.main()
