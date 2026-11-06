import unittest,os,tempfile,subprocess,importlib.util,io,contextlib,json
from pathlib import Path
from unittest.mock import patch
from knowledge_graph.ingestion import collection
from knowledge_graph.storage import manage

class OperationsTests(unittest.TestCase):
 def test_collection_failure_exit_propagates(self):
  with patch.dict(os.environ,{'OPENDART_API_KEY':'placeholder'}),patch.object(collection,'main',return_value=2):
   self.assertEqual(collection.entry(['--start','2026-10-01','--end','2026-11-05']),2)
 def test_wait_ready_retries_bounded(self):
  with patch.object(manage,'table',side_effect=[OSError('not yet'),[{'ready':1}]]),patch.object(manage.time,'sleep'):
   manage.wait_ready(attempts=2)
  with patch.object(manage,'table',side_effect=OSError('offline')),patch.object(manage.time,'sleep'):
   with self.assertRaises(RuntimeError):manage.wait_ready(attempts=2)
 def test_staged_secret_detected_after_working_file_is_clean(self):
  root=Path(__file__).resolve().parents[2]
  spec=importlib.util.spec_from_file_location('git_safety',root/'scripts/check_git_safety.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as tmp:
   repo=Path(tmp);subprocess.run(['git','init','-q',str(repo)],check=True)
   (repo/'.gitignore').write_text((root/'.gitignore').read_text())
   p=repo/'config.py';p.write_text('OPENDART_API_KEY="'+('f'*40)+'"\n');subprocess.run(['git','add','config.py'],cwd=repo,check=True)
   p.write_text('# clean working tree content\n')
   output=io.StringIO()
   with patch.object(module,'ROOT',repo),contextlib.redirect_stdout(output):code=module.main()
   result=json.loads(output.getvalue());self.assertEqual(code,1);self.assertTrue(any(i['rule']=='staged_literal_api_key' for i in result['issues']))
if __name__=='__main__':unittest.main()
