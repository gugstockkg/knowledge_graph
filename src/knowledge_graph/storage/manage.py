"""Local authenticated Neo4j lifecycle and HTTP Query API helper."""
from pathlib import Path
import os,json,secrets,subprocess,urllib.request,base64,time,sys
from ..config import get_paths
PATHS=get_paths()
HERE=PATHS.graph;ROOT=PATHS.root;RT=PATHS.runtime;NEO=RT/'neo4j-community';CONF=RT/'neo4j-conf';AUTH=PATHS.secrets/'neo4j-auth.json'

def env():
 e=os.environ.copy();e.update({'JAVA_HOME':str(RT/'java21'),'NEO4J_HOME':str(NEO),'NEO4J_CONF':str(CONF),'LC_ALL':'C'});return e
def credentials():
 password=os.environ.get('NEO4J_PASSWORD')
 if password:return {'username':os.environ.get('NEO4J_USERNAME','neo4j'),'password':password}
 return json.loads(AUTH.read_text())
def query(statement,parameters=None):
 auth=credentials();token=base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
 request=urllib.request.Request(os.environ.get('NEO4J_HTTP_URL','http://127.0.0.1:7474').rstrip('/')+'/db/neo4j/query/v2',data=json.dumps({'statement':statement,'parameters':parameters or {}}).encode(),headers={'Content-Type':'application/json','Accept':'application/json','Authorization':'Basic '+token})
 try:
  with urllib.request.urlopen(request,timeout=90) as response:result=json.load(response)
 except urllib.error.HTTPError as error:
  raise RuntimeError('Query API HTTP '+str(error.code)+': '+error.read().decode()[:1500]) from None
 if result.get('errors'):raise RuntimeError(json.dumps(result['errors']))
 return result
def table(statement,parameters=None):
 result=query(statement,parameters);data=result.get('data',{});return [dict(zip(data.get('fields',[]),row)) for row in data.get('values',[])]
def wait_ready(attempts=60):
 for i in range(attempts):
  try:
   rows=table('RETURN 1 AS ready')
   if rows and rows[0]['ready']==1:return
  except (OSError,RuntimeError):pass
  if i+1<attempts:time.sleep(1)
 raise RuntimeError('Neo4j readiness check failed; inspect configuration, authentication and server logs')
def setup():
 for d in [PATHS.secrets,CONF,PATHS.database,RT/'neo4j-logs',RT/'neo4j-run',PATHS.imports]:d.mkdir(parents=True,exist_ok=True)
 settings={'server.default_listen_address':'127.0.0.1','server.http.listen_address':'127.0.0.1:7474','server.bolt.listen_address':'127.0.0.1:7687','server.http.advertised_address':'localhost:7474','server.bolt.advertised_address':'localhost:7687','server.memory.heap.initial_size':'512m','server.memory.heap.max_size':'1g','server.memory.pagecache.size':'512m','dbms.security.auth_enabled':'true','server.directories.data':str(PATHS.database),'server.directories.logs':str(RT/'neo4j-logs'),'server.directories.run':str(RT/'neo4j-run'),'server.directories.import':str(PATHS.imports)}
 settings.update({'dbms.usage_report.enabled':'false','dbms.fleet_manager.enabled':'false','server.fleet_discovery.enabled':'false','server.http.x_forward.enabled':'false','db.import.csv.legacy_quote_escaping':'false'})
 (CONF/'neo4j.conf').write_text('\n'.join(k+'='+v for k,v in settings.items())+'\n')
 if not AUTH.exists():
  fd=os.open(str(AUTH),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  with os.fdopen(fd,'w') as f:json.dump({'username':'neo4j','password':secrets.token_urlsafe(24),'browser':'http://localhost:7474','bolt':'bolt://localhost:7687'},f,indent=2)
 if not (RT/'.initial-auth-set').exists():
  result=subprocess.run([str(NEO/'bin/neo4j-admin'),'dbms','set-initial-password',credentials()['password']],env=env(),capture_output=True,text=True)
  if result.returncode:raise RuntimeError('initial auth setup failed: '+(result.stdout+result.stderr).replace(credentials()['password'],'[redacted]'))
  (RT/'.initial-auth-set').touch()
def start():
 setup();p=subprocess.run([str(NEO/'bin/neo4j'),'start'],env=env(),capture_output=True,text=True,start_new_session=True);print(p.stdout,p.stderr)
 if p.returncode:raise RuntimeError('server start failed')
 wait_ready();print('SERVER_READY http://localhost:7474')
def stop():
 p=subprocess.run([str(NEO/'bin/neo4j'),'stop'],env=env(),capture_output=True,text=True);print(p.stdout,p.stderr)
 if p.returncode:raise RuntimeError('stop failed')
def load():
 wait_ready()
 for file in ['schema.cypher','load.cypher']:
  statements=[s.strip() for s in (PATHS.imports/file).read_text().split(';') if s.strip()]
  for statement in statements:query(statement)
 print(json.dumps(table('MATCH (n:GUGPilot) RETURN n.entity_type AS type,count(*) AS count ORDER BY type'),ensure_ascii=False))
if __name__=='__main__':
 command=sys.argv[1] if len(sys.argv)>1 else 'status'
 if command=='start':start()
 elif command=='stop':stop()
 elif command=='import':load()
 elif command=='wait':wait_ready();print('SERVER_READY')
 elif command=='credentials':print(AUTH.read_text())
 elif command=='query':print(json.dumps(table(sys.argv[2]),ensure_ascii=False,indent=2))
 else:print(json.dumps(table('CALL dbms.components() YIELD name,versions,edition RETURN name,versions,edition'),ensure_ascii=False))
