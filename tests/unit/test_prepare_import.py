import unittest,tempfile,csv,json
from pathlib import Path
from knowledge_graph.storage.prepare_import import convert,encode_scalar

class ImportTests(unittest.TestCase):
 def test_zero_and_identifiers(self):
  self.assertEqual(encode_scalar(0),'0')
  self.assertEqual(encode_scalar(None),'')
  self.assertEqual(encode_scalar('096690'),'096690')
 def test_invalid_date_and_nonfinite_numbers(self):
  with self.assertRaises(ValueError):encode_scalar('2026-02-30','date')
  with self.assertRaises(ValueError):encode_scalar(float('nan'))
 def source(self,base,duplicate=False,orphan=False):
  attrs={'shares':0,'percentage':0,'as_of_date':'2026-10-14','stock_code':'096690','denominator':None}
  nodes=[{'entity_id':'holding:x','entity_type':'HoldingSnapshot','name':'sample','attributes_json':json.dumps(attrs)}]
  if duplicate:nodes.append(nodes[0].copy())
  with (base/'nodes.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(nodes[0]));w.writeheader();w.writerows(nodes)
  with (base/'relationships.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['relation_id','subject_id','predicate','object_id','attributes_json']);w.writeheader()
   if orphan:w.writerow({'relation_id':'r','subject_id':'holding:x','predicate':'HELD_BY','object_id':'missing','attributes_json':'{}'})
 def test_flatten_and_preserve_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   b=Path(tmp);src=b/'src';src.mkdir();self.source(src);before=(src/'nodes.csv').read_bytes();convert(src,b/'out')
   with (b/'out/nodes.csv').open(encoding='utf-8-sig',newline='') as f:r=next(csv.DictReader(f))
   self.assertEqual(r['shares'],'0');self.assertEqual(r['stock_code'],'096690');self.assertEqual(r['denominator'],'');self.assertEqual(before,(src/'nodes.csv').read_bytes())
 def test_duplicate_and_orphan_rejected(self):
  for duplicate,orphan in [(True,False),(False,True)]:
   with tempfile.TemporaryDirectory() as tmp:
    b=Path(tmp);src=b/'src';src.mkdir();self.source(src,duplicate,orphan)
    with self.assertRaises(ValueError):convert(src,b/'out')
 def test_scripts_scoped_to_output(self):
  with tempfile.TemporaryDirectory() as tmp:
   b=Path(tmp);src=b/'src';src.mkdir();self.source(src);convert(src,b/'out')
   self.assertTrue((b/'out/schema.cypher').exists());self.assertTrue((b/'out/load.cypher').exists())
 def test_bad_boolean_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   b=Path(tmp);src=b/'src';src.mkdir();self.source(src)
   path=src/'nodes.csv'
   with path.open(newline='') as f:rows=list(csv.DictReader(f))
   attrs=json.loads(rows[0]['attributes_json']);attrs['arithmetic_consistent']='yes';rows[0]['attributes_json']=json.dumps(attrs)
   with path.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   with self.assertRaises(ValueError):convert(src,b/'out')
 def test_verify_rejects_wrong_ids_and_endpoints(self):
  from knowledge_graph.storage.verify import assert_graph_matches_source
  with tempfile.TemporaryDirectory() as tmp:
   b=Path(tmp);self.source(b)
   correct={'node_ids':[{'id':'holding:x'}],'relationship_details':[]}
   assert_graph_matches_source(b,correct)
   with self.assertRaises(AssertionError):assert_graph_matches_source(b,{'node_ids':[{'id':'wrong'}],'relationship_details':[]})
   headers=['relation_id','subject_id','predicate','object_id','attributes_json']
   with (b/'relationships.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerow(dict(zip(headers,['r','holding:x','HELD_BY','holding:x','{}'])))
   wrong={'node_ids':[{'id':'holding:x'}],'relationship_details':[{'id':'r','subject':'holding:x','predicate':'HELD_BY','object':'wrong'}]}
   with self.assertRaises(AssertionError):assert_graph_matches_source(b,wrong)
if __name__=='__main__':unittest.main()
