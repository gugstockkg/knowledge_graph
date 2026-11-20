import datetime as dt
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from knowledge_graph.ingestion import batch
from knowledge_graph.ingestion.client import DartApiError

def zip_bytes():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:z.writestr('filing.xml','<DOCUMENT/>')
    return out.getvalue()

def filing(receipt='20251231000001',day='20260102'):
    return dict(rcept_no=receipt,rcept_dt=day,corp_code='00000001',report_nm='test')

class API:
    def __init__(self):self.rows={'20260102':[filing()]};self.lists=[];self.docs=[];self.failure=None
    def get_json(self,endpoint,p):
        self.lists.append(p.copy());rows=self.rows.get(p['bgn_de'],[]);page=p['page_no']
        return dict(status='000' if rows else '013',total_count=len(rows),total_page=max(1,(len(rows)+99)//100),list=rows[(page-1)*100:page*100])
    def download_document(self,receipt):
        self.docs.append(receipt)
        if self.failure:raise self.failure
        return zip_bytes()

class Sink:
    def __init__(self):self.keys=[];self.fail=False
    def put(self,path,key):
        if self.fail:raise RuntimeError('upload failed')
        self.keys.append(key)

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.api=API();self.sink=Sink()
        self.clock=lambda:dt.datetime(2026,1,5,12,tzinfo=batch.KST)
    def worker(self,**kw):return batch.Collector(self.root,self.api,self.sink,now=self.clock,**kw)
    def day(self,w=None,**kw):return (w or self.worker()).collect_day(dt.date(2026,1,2),**kw)
    def test_partition_uses_receipt_date(self):
        self.assertTrue(self.day());p='documents/partition_day=2026-01-02/20251231000001.zip'
        self.assertTrue((self.root/p).exists());self.assertIn(p,self.sink.keys)
    def test_resume_no_extra_api_calls(self):
        self.day();self.day();self.assertEqual(len(self.api.lists),1);self.assertEqual(len(self.api.docs),1)
    def test_refresh_finds_late_filing(self):
        self.day();self.api.rows['20260102'].append(filing('20260102000002'));self.day(refresh=True)
        self.assertEqual(len(self.api.docs),2)
    def test_pagination_and_count_validation(self):
        self.api.rows['20260102']=[filing(f'20260102{i:06d}') for i in range(101)]
        self.day();self.assertEqual([p['page_no'] for p in self.api.lists],[1,2])
        original=self.api.get_json
        def bad(*a):
            data=original(*a);data['total_count']+=1;return data
        self.api.get_json=bad
        with self.assertRaises(batch.BatchError):self.day(refresh=True)
    def test_upload_retry_reuses_zip(self):
        self.sink.fail=True
        with self.assertRaises(batch.BatchError):self.day()
        self.sink.fail=False;self.assertTrue(self.day());self.assertEqual(len(self.api.docs),1)
    def test_corrupt_file_is_redownloaded(self):
        self.day();next(self.root.glob('documents/**/*.zip')).write_bytes(b'bad');self.day(refresh=True)
        self.assertEqual(len(self.api.docs),2)
    def test_quota_pauses_across_restarts_until_next_kst_day(self):
        self.api.failure=DartApiError('quota',status='020')
        with self.assertRaises(batch.Paused):self.day()
        self.api.failure=None
        with self.assertRaises(batch.Paused):self.day()
        self.assertEqual(len(self.api.docs),1)
        self.clock=lambda:dt.datetime(2026,1,6,1,tzinfo=batch.KST);self.assertTrue(self.day())
    def test_daily_budget_persists(self):
        with self.assertRaises(batch.Paused):self.day(self.worker(daily_limit=1))
        with self.assertRaises(batch.Paused):self.day(self.worker(daily_limit=1))
        self.assertEqual(len(self.api.lists),1);self.assertEqual(len(self.api.docs),0)
    def test_run_budget_is_resumable(self):
        with self.assertRaises(batch.Paused):self.day(self.worker(run_limit=1))
        self.assertTrue(self.day());self.assertEqual(len(self.api.docs),1)
    def test_unavailable_retried_after_ttl(self):
        self.api.failure=DartApiError('no data',status='014');self.day();self.day(refresh=True)
        self.assertEqual(len(self.api.docs),1)
        self.clock=lambda:dt.datetime(2026,1,14,1,tzinfo=batch.KST);self.api.failure=None
        self.assertTrue(self.day(refresh=True));self.assertEqual(len(self.api.docs),2)
    def test_transient_error_does_not_complete_day(self):
        self.api.failure=DartApiError('offline')
        with self.assertRaises(batch.BatchError):self.day()
        self.api.failure=None;self.assertTrue(self.day())
    def test_invalid_identity_or_date_rejected(self):
        for bad in [dict(filing(),rcept_no='../bad'),dict(filing(),rcept_dt='20260103')]:
            self.api.rows['20260102']=[bad]
            with self.assertRaises(batch.BatchError):self.day(refresh=True)
        self.assertEqual(self.api.docs,[])
    def test_daily_gap_and_lookback(self):
        self.assertEqual(batch.daily_start(dt.date(2026,1,10),None),dt.date(2026,1,7))
        self.assertEqual(batch.daily_start(dt.date(2026,1,10),'2026-01-02'),dt.date(2026,1,3))
    def test_lock_excludes_second_worker(self):
        with batch.collection_lock(self.root):
            with self.assertRaises(batch.Paused):
                with batch.collection_lock(self.root):self.fail('second lock')

if __name__=='__main__':unittest.main()
