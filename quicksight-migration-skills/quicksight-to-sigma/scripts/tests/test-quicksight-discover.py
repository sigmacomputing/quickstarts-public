#!/usr/bin/env python3
"""Unit tests + mocked/recorded-response harness for the fast-discovery layer
of quicksight-discover.py (boto3-in-process transport, aws-CLI fallback,
estate-level dataset/datasource cache, batch mode).

Live AWS is not required (and is currently IAM-blocked): the boto3 path is
proven with an injected fake boto3 module replaying RECORDED describe-shaped
responses (sourced from the skill's fixtures), and the CLI path with a stubbed
subprocess.run. What still awaits live AWS validation is listed in SKILL.md.

Run:  python3 scripts/tests/test-quicksight-discover.py
"""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "quicksight-discover.py")
FIXTURES = os.path.join(HERE, "..", "..", "fixtures")

spec = importlib.util.spec_from_file_location("qsdisc", SCRIPT)
qsdisc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qsdisc)

ACCT, REGION = "123456789012", "us-east-1"


def recorded():
    """Recorded describe-shaped responses, anchored on the skill's real fixtures."""
    analysis = json.load(open(os.path.join(FIXTURES, "orders-overview-analysis.json")))
    dataset = json.load(open(os.path.join(FIXTURES, "dataset-orders-enriched.json")))
    ds_id = dataset["DataSet"]["DataSetId"]
    arn = dataset["DataSet"].get("Arn") or f"arn:aws:quicksight:{REGION}:{ACCT}:dataset/{ds_id}"
    dataset["DataSet"]["Arn"] = arn
    # pin the LastUpdatedTime so the recorded estate listing agrees with the
    # describe response (the cache key is DataSetArn + LastUpdatedTime)
    dataset["DataSet"]["LastUpdatedTime"] = "2026-06-01T00:00:00"
    # ensure the dataset points at a datasource so the lazy datasource path runs
    src_arn = f"arn:aws:quicksight:{REGION}:{ACCT}:datasource/snowflake-src"
    ptm = dataset["DataSet"].setdefault("PhysicalTableMap", {})
    if not any(v.get("DataSourceArn") for t in ptm.values() for v in t.values() if isinstance(v, dict)):
        ptm["pt1"] = {"RelationalTable": {"DataSourceArn": src_arn, "Name": "ORDERS",
                                          "InputColumns": []}}
    datasource = {"DataSource": {"DataSourceId": "snowflake-src", "Arn": src_arn,
                                 "Name": "Snowflake", "Type": "SNOWFLAKE"}}
    return analysis, dataset, datasource


class FakeQSClient:
    """Replays recorded responses; counts every call (the harness assertions)."""

    def __init__(self, analysis, dataset, datasource, listing_lut="2026-06-01T00:00:00"):
        self.analysis, self.dataset, self.datasource = analysis, dataset, datasource
        self.listing_lut = listing_lut
        self.calls = []

    def describe_analysis_definition(self, AwsAccountId=None, AnalysisId=None):
        self.calls.append(("describe-analysis-definition", AnalysisId))
        out = dict(self.analysis)
        out["AnalysisId"] = AnalysisId
        # boto3 returns datetimes — prove the normalization path
        out["ResponseMetadata"] = {"RequestId": "x"}
        out["LastUpdatedTime"] = datetime.datetime(2026, 6, 1, 12, 0, 0)
        return out

    def describe_data_set(self, AwsAccountId=None, DataSetId=None):
        self.calls.append(("describe-data-set", DataSetId))
        return json.loads(json.dumps(self.dataset))

    def describe_data_source(self, AwsAccountId=None, DataSourceId=None):
        self.calls.append(("describe-data-source", DataSourceId))
        return json.loads(json.dumps(self.datasource))

    def list_data_sets(self, AwsAccountId=None, **kw):
        self.calls.append(("list-data-sets", None))
        return {"DataSetSummaries": [{"Arn": self.dataset["DataSet"]["Arn"],
                                      "LastUpdatedTime": self.listing_lut}]}

    def count(self, op):
        return sum(1 for o, _ in self.calls if o == op)


def fake_boto3(client):
    mod = types.ModuleType("boto3")
    class Session:  # noqa: D401
        def __init__(self, profile_name=None, region_name=None):
            pass
        def client(self, name):
            assert name == "quicksight"
            return client
    mod.Session = Session
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qsdisc-test-")
        self._cache_root = qsdisc.CACHE_ROOT
        qsdisc.CACHE_ROOT = os.path.join(self.tmp, "estate-cache")
        self._boto3 = sys.modules.pop("boto3", None)
        self._run = subprocess.run

    def tearDown(self):
        qsdisc.CACHE_ROOT = self._cache_root
        subprocess.run = self._run
        if self._boto3 is not None:
            sys.modules["boto3"] = self._boto3
        else:
            sys.modules.pop("boto3", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def api_with(self, client):
        sys.modules["boto3"] = fake_boto3(client)
        api = qsdisc.QSApi(ACCT, REGION, force_cli=False)
        self.assertEqual(api.transport, "boto3")
        return api

    def quiet(self, *_a, **_k):
        pass


class TestTransport(Base):
    def test_boto3_in_process_no_subprocess(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        def boom(*a, **k):
            raise AssertionError("subprocess used despite boto3 transport")
        subprocess.run = boom
        api = self.api_with(client)
        out = api.call("describe-data-set", DataSetId=dataset["DataSet"]["DataSetId"])
        self.assertEqual(out["DataSet"]["Name"], dataset["DataSet"]["Name"])
        self.assertEqual(client.count("describe-data-set"), 1)

    def test_cli_fallback_when_boto3_absent(self):
        sys.modules.pop("boto3", None)
        sys.modules["boto3"] = None  # import boto3 -> ImportError (None module)
        captured = {}
        def fake_run(cmd, capture_output=None, text=None):
            captured["cmd"] = cmd
            return types.SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True}), stderr="")
        subprocess.run = fake_run
        api = qsdisc.QSApi(ACCT, REGION, profile="pivot", force_cli=False)
        self.assertEqual(api.transport, "aws-cli")
        out = api.call("describe-data-set", DataSetId="abc")
        self.assertTrue(out["ok"])
        cmd = captured["cmd"]
        self.assertEqual(cmd[:3], ["aws", "quicksight", "describe-data-set"])
        self.assertIn("--data-set-id", cmd)       # PascalCase -> kebab
        self.assertIn("--aws-account-id", cmd)
        self.assertIn("--profile", cmd)

    def test_force_cli_env_wins_over_boto3(self):
        analysis, dataset, datasource = recorded()
        sys.modules["boto3"] = fake_boto3(FakeQSClient(analysis, dataset, datasource))
        api = qsdisc.QSApi(ACCT, REGION, force_cli=True)
        self.assertEqual(api.transport, "aws-cli")

    def test_datetime_normalization_strips_response_metadata(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        out = api.call("describe-analysis-definition", AnalysisId="a1")
        self.assertNotIn("ResponseMetadata", out)
        self.assertEqual(out["LastUpdatedTime"], "2026-06-01T12:00:00")
        json.dumps(out)  # fully serializable


class TestEstateCache(Base):
    def discover(self, cache, aid, client):
        out = os.path.join(self.tmp, aid)
        return qsdisc.discover_one(out, cache, analysis_id=aid, log=self.quiet)

    def test_shared_dataset_described_once_per_estate(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        cache = qsdisc.EstateCache(api)
        self.discover(cache, "a1", client)   # describes the dataset
        self.discover(cache, "a2", client)   # same dataset -> memo, no describe
        self.assertEqual(client.count("describe-data-set"), 1)
        # a NEW process (new cache instance) with an unchanged estate -> disk
        # cache hit validated against ONE list-data-sets, still no re-describe
        cache2 = qsdisc.EstateCache(api)
        self.discover(cache2, "a3", client)
        self.assertEqual(client.count("describe-data-set"), 1)
        self.assertEqual(client.count("list-data-sets"), 1)

    def test_cache_invalidated_on_lastupdatedtime_change(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        self.discover(qsdisc.EstateCache(api), "a1", client)
        self.assertEqual(client.count("describe-data-set"), 1)
        # unchanged estate -> disk hit (proves the hit BEFORE proving the miss)
        self.discover(qsdisc.EstateCache(api), "a2", client)
        self.assertEqual(client.count("describe-data-set"), 1)
        client.listing_lut = "2026-06-09T09:00:00"  # dataset changed upstream
        self.discover(qsdisc.EstateCache(api), "a3", client)
        self.assertEqual(client.count("describe-data-set"), 2)

    def test_datasource_described_once_lazily(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        cache = qsdisc.EstateCache(api)
        self.discover(cache, "a1", client)
        self.discover(cache, "a2", client)
        self.assertEqual(client.count("describe-data-source"), 1)
        # new process: datasource comes from disk cache, no probe call at all
        self.discover(qsdisc.EstateCache(api), "a3", client)
        self.assertEqual(client.count("describe-data-source"), 1)

    def test_no_cache_flag_bypasses(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        self.discover(qsdisc.EstateCache(api, enabled=False), "a1", client)
        self.discover(qsdisc.EstateCache(api, enabled=False), "a2", client)
        self.assertEqual(client.count("describe-data-set"), 2)

    def test_signals_shape_matches_offline_run(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        api = self.api_with(client)
        sig = self.discover(qsdisc.EstateCache(api), "a1", client)
        self.assertEqual(sig["source"]["kind"], "analysis")
        self.assertEqual(len(sig["datasets"]), 1)
        self.assertEqual(sig["dataSources"][0]["type"], "SNOWFLAKE")
        self.assertTrue(all("visuals" in s for s in sig["sheets"]))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "a1", "signals.json")))


class TestBatchMode(Base):
    def test_batch_parallel_discovery(self):
        analysis, dataset, datasource = recorded()
        client = FakeQSClient(analysis, dataset, datasource)
        sys.modules["boto3"] = fake_boto3(client)
        out = os.path.join(self.tmp, "estate")
        with self.assertRaises(SystemExit) as cm:
            qsdisc.main(["--account-id", ACCT, "--region", REGION,
                         "--analysis-ids", "a1,a2,a3", "--pool", "4",
                         "--out-dir", out])
        self.assertEqual(cm.exception.code, 0)
        for aid in ("a1", "a2", "a3"):
            self.assertTrue(os.path.exists(os.path.join(out, aid, "signals.json")), aid)
        # the shared estate cache held: 3 analyses, ONE dataset describe
        self.assertEqual(client.count("describe-data-set"), 1)
        self.assertEqual(client.count("describe-analysis-definition"), 3)
        t = json.load(open(os.path.join(out, "timings.json")))
        self.assertEqual(t["mode"], "batch")
        self.assertEqual(t["analyses"], 3)
        self.assertTrue(any(x["task"].startswith("analysis:") for x in t["tasks"]))


class TestFixturePath(Base):
    def test_offline_fixture_run_stays_green(self):
        out = os.path.join(self.tmp, "fixture-run")
        qsdisc.main(["--from-fixtures", FIXTURES, "--out-dir", out])
        sig = json.load(open(os.path.join(out, "signals.json")))
        self.assertEqual(sig["source"]["name"], "Orders Overview")
        self.assertEqual(len(sig["sheets"][0]["visuals"]), 5)
        self.assertEqual(sig["dataSources"][0]["type"], "OFFLINE-FIXTURE")
        self.assertTrue(os.path.exists(os.path.join(out, "timings.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
