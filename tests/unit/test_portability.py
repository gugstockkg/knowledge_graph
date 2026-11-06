import unittest,tempfile,os,ssl
from pathlib import Path
from unittest.mock import patch
from knowledge_graph.config import get_paths,require_api_key
from knowledge_graph.ingestion.client import DartClient,DartApiError

class PortabilityTests(unittest.TestCase):
 def test_paths_independent_of_working_directory(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'KG_DATA_DIR':tmp}):
   p=get_paths();self.assertEqual(p.data,Path(tmp).resolve());self.assertEqual(p.collection,p.data/'raw/opendart/collections/20261001_20261105');self.assertEqual(p.ontology.name,'v0.1')
 def test_key_missing_safe_and_no_history(self):
  with patch.dict(os.environ,{'OPENDART_API_KEY':''}):
   with self.assertRaisesRegex(ValueError,'OPENDART_API_KEY'):require_api_key()
 def test_unavailable_document_is_not_a_zip(self):
  c=DartClient(api_key='placeholder')
  with patch.object(c,'_request',return_value=b'<result><status>014</status><message>unavailable</message></result>'):
   with self.assertRaises(DartApiError) as error:c.download_document('synthetic-receipt')
   self.assertEqual(error.exception.status,'014')
 def test_tls_verification_remains_enabled(self):
  client=DartClient(api_key='placeholder')
  self.assertEqual(client.ssl_context.verify_mode,ssl.CERT_REQUIRED)
  self.assertTrue(client.ssl_context.check_hostname)
if __name__=='__main__':unittest.main()
