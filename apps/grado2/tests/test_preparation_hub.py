"""Проверяет права настоящего хаба при запуске и отзыве доступа во время импорта.

Запуск: python -m pytest apps/grado2/tests/test_preparation_hub.py.
"""
import copy
import json
import threading
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from test_hub import Base,sample_project
from test_preparation_api import TERRITORY,HEADERS
import server as S
import preparation as P
import preparation_api as A
import sushpol_jobs as J


class HubPreparation(Base):
    def test_viewer_cannot_start_and_revoked_editor_cannot_write_result(self):
        project=sample_project();project['territory']['geometry']=TERRITORY
        pid=self.new_project(project)
        entered=threading.Event();release=threading.Event()
        def fetch(bbox,keys,*args):
            entered.set();release.wait(5)
            return {},{k:'Нет ответа' for k in keys}
        class Context:
            headers=HEADERS
            def __init__(self,user):self.user=user
            def who(self):return self.user
        with patch.object(S,'HUB',self.hub),patch.object(S,'CACHE',Path(self._tmp.name)/'cache'),patch.object(S,'fetch',fetch):
            runs=J.Runs(S)
            args={'projectId':pid,'commandId':str(uuid4()),'photos':False}
            with self.assertRaises(S.hubmod.HubError) as denied:runs.start(Context(self.viewer),args)
            self.assertEqual(denied.exception.status,403)
            result=runs.start(Context(self.editor),args)
            rid=result['runId'];self.assertTrue(entered.wait(5))
            self.hub.set_member(self.owner,pid,'editor',None)
            before=(self.hub._pdir(pid)/'project.grado2').read_bytes()
            release.set();runs.jobs[rid]['thread'].join(timeout=8)
            self.assertFalse(runs.jobs[rid]['thread'].is_alive())
            self.assertEqual((self.hub._pdir(pid)/'project.grado2').read_bytes(),before)
            self.assertFalse((runs.jobs[rid]['path']/'candidate.grado2').exists())
            self.assertEqual(runs.jobs[rid]['report']['byCode'],{'forbidden':1})

    def test_protected_hub_sections_reject_loss_of_preparation(self):
        project=sample_project();project['album']['meta']['sushpolPreparation']=P.new_state()
        pid=self.new_project(project)
        root=self.hub._pdir(pid);meta=self.hub._meta(pid)
        meta['requiredCapabilities']=[P.CAPABILITY];self.hub._save_meta(pid,meta)
        with self.assertRaises(P.PreparationError):
            self.hub.push(self.owner,pid,meta['rev'],{'album':{'meta':{},'sheets':[]}},'client',capabilities=HEADERS)
        with self.assertRaises(P.PreparationError):
            self.hub.push(self.owner,pid,meta['rev'],{'meta':{'name':'changed'}},'legacy')
        self.assertIn('sushpolPreparation',json.loads((root/'project.grado2').read_bytes())['album']['meta'])
