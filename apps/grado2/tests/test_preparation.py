"""Проверяет МСК-покрытие, ревизии и восстановление проекта между двумя заменами.

Запуск: python -m pytest apps/grado2/tests/test_preparation.py.
"""
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

import preparation as P
from shapely.geometry import box, mapping


def area(x0, y0, x1, y1):
    return mapping(P.to_wgs(box(x0, y0, x1, y1)))


class CoverageTest(unittest.TestCase):
    def test_holes_between_parts_do_not_become_full_bbox(self):
        parts = [{"sublayer": "a", "outcome": "empty", "area": area(0, 0, 400, 1000)},
                 {"sublayer": "a", "outcome": "received", "area": area(600, 0, 1000, 1000)}]
        c = P.coverage(area(0, 0, 1000, 1000), parts, ["a"])
        self.assertAlmostEqual(c["ratio"], .8, places=5)
        self.assertFalse(c["complete"])
        self.assertAlmostEqual(c["missingAreaM2"], 200000, delta=5)

    def test_each_required_sublayer_must_be_checked(self):
        a = area(0, 0, 1000, 1000)
        p = [{"sublayer": "a", "outcome": "empty", "area": a}]
        self.assertTrue(P.coverage(a, p, ["a"])["complete"])
        self.assertFalse(P.coverage(a, p, ["a", "b"])["complete"])
        self.assertFalse(P.coverage(a, p, [])["complete"])

    def test_overlapping_receipts_do_not_double_area(self):
        p = [{"sublayer": "a", "outcome": "received", "area": area(0, 0, 750, 1000)},
             {"sublayer": "a", "outcome": "empty", "area": area(250, 0, 1000, 1000)}]
        self.assertAlmostEqual(P.coverage(area(0, 0, 1000, 1000), p, ["a"])["ratio"], 1., places=6)

    def test_invalid_polygon_is_not_silently_repaired(self):
        with self.assertRaises(P.PreparationError):
            P.polygon({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]})


class RevisionTest(unittest.TestCase):
    def test_key_order_and_integer_roundtrip_are_stable(self):
        self.assertEqual(P.digest({"a": 1., "b": {"x": .25}}), P.digest({"b": {"x": .25}, "a": 1}))
        with self.assertRaises(P.PreparationError):
            P.digest({"x": float("nan")})

    def test_data_and_manual_changes_have_different_scopes(self):
        p = {"territory": {"type": "Feature", "geometry": area(0, 0, 100, 100)},
             "data": {"a": {"fc": {"features": []}}}, "album": {"meta": {}, "sheets": []}}
        a = P.revisions(p)
        p["data"]["a"]["fc"]["features"].append({"properties": {"right": "source"}})
        b = P.revisions(p)
        self.assertEqual(a["baseInputsRevision"], b["baseInputsRevision"])
        self.assertNotEqual(a["inputRevision"], b["inputRevision"])
        p["album"]["sheets"].append({"id": "1", "title": "Ручное название"})
        self.assertNotEqual(b["baseInputsRevision"], P.revisions(p)["baseInputsRevision"])

    def test_unknown_schema_and_profile_fail_closed(self):
        p = {"album": {"meta": {"sushpolPreparation": {"schemaVersion": 2}}}}
        with self.assertRaises(P.PreparationError) as e:
            P.revisions(p)
        self.assertEqual(e.exception.code, "unsupported_schema")
        p = {"data": {str(i): {} for i in range(101)}}
        with self.assertRaises(P.PreparationError) as e:
            P.check_profile(p)
        self.assertEqual(e.exception.code, "budget_exceeded")


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.project, self.meta = d / "p.grado2", d / "p.meta.json"
        self.before = P.dump({"name": "Прежний", "album": {"sheets": [1, 2]}})
        self.after = P.dump({"name": "Новый", "album": {"sheets": [3, 4]}})
        self.project.write_bytes(self.before)
        self.meta.write_bytes(P.dump({"rev": 1}))
        self.tx = P.Transaction(self.project, self.meta)

    def test_process_crash_at_each_publication_boundary_recovers_pair(self):
        for point in ("journal_published", "project_published", "metadata_published"):
            with self.subTest(point=point):
                self.project.write_bytes(self.before)
                self.meta.write_bytes(P.dump({"rev": 1}))
                cid = str(uuid.uuid4())
                def crash(stage):
                    if stage == point:
                        raise SystemExit("injected process exit")
                tx = P.Transaction(self.project, self.meta, failpoint=crash)
                with self.assertRaises(SystemExit):
                    tx.publish(self.after, {"rev": 2}, cid, P.body_hash(self.before))
                body, meta = self.tx.read()
                self.assertEqual(body, self.after)
                self.assertEqual(meta["rev"], 2)
                self.assertIn(cid, meta["preparationCommits"])
                result = self.tx.publish(self.after, {"rev": 3}, cid, P.body_hash(self.before))
                self.assertEqual(result["projectRevision"], P.body_hash(self.after))
                self.assertEqual(self.tx.read()[1]["rev"], 2)

    def test_stale_write_does_not_replace_manual_work(self):
        with self.assertRaises(P.PreparationError) as e:
            self.tx.publish(self.after, {}, str(uuid.uuid4()), "wrong")
        self.assertEqual(e.exception.code, "version_conflict")
        self.assertEqual(self.project.read_bytes(), self.before)

    def test_checkpoint_is_full_and_does_not_throttle(self):
        a = self.tx.checkpoint(P.body_hash(self.before))
        b = self.tx.checkpoint(P.body_hash(self.before))
        self.assertNotEqual(a["checkpointId"], b["checkpointId"])
        self.assertEqual((self.tx.root / "checkpoints" / (a["checkpointId"] + ".grado2")).read_bytes(), self.before)

    def test_other_client_cannot_renew_or_take_live_lease(self):
        r = self.tx.lease("acquire", "run", "owner", "command", expected_revision=P.body_hash(self.before), now=100)
        same = self.tx.lease("acquire", "run", "owner", "command", expected_revision="irrelevant", now=110)
        self.assertEqual(r, same)
        for action, owner in (("renew", "other"), ("release", "other")):
            with self.assertRaises(P.PreparationError):
                self.tx.lease(action, "run", owner, "c2", lease_id=r["leaseId"], now=110)
        with self.assertRaises(P.PreparationError):
            self.tx.lease("acquire", "run2", "other", "c3", expected_revision=P.body_hash(self.before), now=110)
        with self.assertRaises(P.PreparationError):
            self.tx.lease("renew", "run", "owner", "c4", lease_id=r["leaseId"], now=131)
        new = self.tx.lease("acquire", "run2", "other", "c5", expected_revision=P.body_hash(self.before), now=131)
        self.assertNotEqual(r["leaseId"], new["leaseId"])

    def test_corrupt_stage_is_not_published(self):
        def stop(stage):
            if stage == "journal_published":
                raise SystemExit()
        cid = str(uuid.uuid4())
        with self.assertRaises(SystemExit):
            P.Transaction(self.project, self.meta, stop).publish(self.after, {}, cid, P.body_hash(self.before))
        (self.tx.root / cid / "project.next").write_bytes(b"broken")
        with self.assertRaises(P.PreparationError) as e:
            self.tx.read()
        self.assertEqual(e.exception.code, "recovery_failed")
        self.assertEqual(self.project.read_bytes(), self.before)
