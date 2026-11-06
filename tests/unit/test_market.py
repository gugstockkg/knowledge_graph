import unittest
from knowledge_graph.market.prices import parse_chart,event_returns

class MarketTests(unittest.TestCase):
 def chart(self,rows):
  return ('<?xml version="1.0" encoding="EUC-KR"?><protocol><chartdata symbol="214330" name="금호에이치티">'+''.join('<item data="'+r+'"/>' for r in rows)+'</chartdata></protocol>').encode('euc-kr')
 def test_decode_and_ohlcv(self):
  meta,rows=parse_chart(self.chart(['20261019|100|120|90|110|500']),'214330','2026-09-01','2026-11-05')
  self.assertEqual(meta['name'],'금호에이치티');self.assertEqual(rows[0]['date'],'2026-10-19');self.assertEqual(rows[0]['close'],110)
 def test_wrong_symbol_duplicate_and_bad_prices_rejected(self):
  with self.assertRaises(ValueError):parse_chart(self.chart(['20261019|100|120|90|110|500']),'999999','2026-09-01','2026-11-05')
  for values in [['20261019|100|90|95|110|500'],['20261019|100|120|90|110|500']*2]:
   with self.assertRaises(ValueError):parse_chart(self.chart(values),'214330','2026-09-01','2026-11-05')
 def test_entry_strictly_after_receipt_and_incomplete_horizon(self):
  bars=[{'date':'2026-10-19','open':90,'close':100,'volume':100},{'date':'2026-10-20','open':100,'close':110,'volume':100},{'date':'2026-10-21','open':120,'close':126,'volume':100}]
  r=event_returns('2026-10-19',bars,[1,2,5]);self.assertEqual(r['entry_date'],'2026-10-20');self.assertAlmostEqual(r['horizons']['1']['return_pct'],10);self.assertAlmostEqual(r['horizons']['2']['return_pct'],26);self.assertEqual(r['horizons']['5']['status'],'insufficient_future_bars');self.assertIsNone(r['horizons']['5']['return_pct'])
 def test_halt_is_not_silently_skipped(self):
  bars=[{'date':'2026-10-20','open':0,'close':100,'volume':0},{'date':'2026-10-21','open':110,'close':120,'volume':100}]
  r=event_returns('2026-10-19',bars,[1]);self.assertEqual(r['status'],'nontradable_entry');self.assertIsNone(r['horizons']['1']['return_pct'])
 def test_graph_payload_identity_and_name_gate(self):
  from knowledge_graph.market.link import build_payload
  snapshot={'stock_code':'214330','corp_code':'00105606','company_id':'company:00105606','provider_name':'금호에이치티','mapping_status':'name_match','source_url':'https://example.invalid','retrieved_at':'2026-11-06T00:00:00+00:00','raw_sha256':'synthetic','bars':[{'date':'2026-10-19','open':100,'high':120,'low':90,'close':110,'volume':500,'is_tradable':True}]}
  m={'dataset_id':'synthetic-dataset','snapshots':[snapshot],'prices':1,'failures':[]}
  a,b=build_payload(m);self.assertEqual(len(a),1);self.assertEqual(len(b),1);self.assertEqual(a[0]['company_id'],'company:00105606');self.assertIn('synthetic-dataset',b[0]['entity_id'])
  snapshot['mapping_status']='name_mismatch_review'
  with self.assertRaises(ValueError):build_payload(m)
if __name__=='__main__':unittest.main()
