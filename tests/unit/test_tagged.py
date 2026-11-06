from pathlib import Path
import unittest
from knowledge_graph.extraction.tagged import FieldParser

class TaggedTests(unittest.TestCase):
 def test_synthetic_values_and_source_location(self):
  path=Path(__file__).resolve().parents[1]/'fixtures/synthetic/disclosure.xml'
  parser=FieldParser();parser.feed(path.read_text())
  fields={f['key']:f for f in parser.fields}
  self.assertEqual(fields['IFR_NM']['text'],'합성 테스트 보고자')
  self.assertEqual(fields['AFR_RPT_DT']['unit_value'],'20261014')
  self.assertEqual(fields['AFR_UN_CNT']['text'],'1,000')
  self.assertEqual(fields['AFR_UN_CNT']['line'],6)
  self.assertIsNotNone(fields['AFR_UN_CNT']['table'])
if __name__=='__main__':unittest.main()
