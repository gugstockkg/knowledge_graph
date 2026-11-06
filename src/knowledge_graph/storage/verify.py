"""Live acceptance checks; rerun import only, never delete database contents."""
from pathlib import Path
import json,datetime,urllib.request,urllib.error,csv
from .manage import table,query,load,HERE,RT,PATHS

def statements(path):
 lines=[line for line in path.read_text().splitlines() if not line.strip().startswith('//')]
 return [s.strip() for s in '\n'.join(lines).split(';') if s.strip()]
def snapshot():
 return {'nodes':table('MATCH (n:GUGPilot) RETURN count(n) AS n')[0]['n'],'relationships':table('MATCH (:GUGPilot)-[r]->(:GUGPilot) RETURN count(r) AS n')[0]['n'],'node_ids':table('MATCH (n:GUGPilot) RETURN n.entity_id AS id ORDER BY id'),'relation_ids':table('MATCH (:GUGPilot)-[r]->(:GUGPilot) RETURN r.relation_id AS id ORDER BY id'),'relationship_details':table('MATCH (a:GUGPilot)-[r]->(b:GUGPilot) RETURN r.relation_id AS id,a.entity_id AS subject,type(r) AS predicate,b.entity_id AS object ORDER BY id')}
def assert_graph_matches_source(source_dir,snap):
 with (source_dir/'nodes.csv').open(encoding='utf-8-sig',newline='') as f:nodes=list(csv.DictReader(f))
 with (source_dir/'relationships.csv').open(encoding='utf-8-sig',newline='') as f:rels=list(csv.DictReader(f))
 assert sorted(n['entity_id'] for n in nodes)==sorted(n['id'] for n in snap['node_ids']),'source node IDs differ'
 expected=sorted((r['relation_id'],r['subject_id'],r['predicate'],r['object_id']) for r in rels)
 actual=sorted((r['id'],r['subject'],r['predicate'],r['object']) for r in snap['relationship_details'])
 assert expected==actual,'source relationship IDs/types/endpoints differ'
def verify():
 components=table('CALL dbms.components() YIELD name,versions,edition RETURN name,versions,edition')
 assert any(c['edition']=='community' for c in components)
 before=snapshot();assert before['nodes']==332 and before['relationships']==600
 (PATHS.artifacts/'neo4j').mkdir(parents=True,exist_ok=True)
 source=Path(json.loads((PATHS.imports/'manifest.json').read_text())['source_dir']);assert_graph_matches_source(source,before)
 expect={'Assertion':120,'Company':5,'DocumentVersion':20,'EvidenceSpan':100,'ExtractionRun':1,'Filing':20,'HoldingSnapshot':40,'Organization':11,'Person':6,'UnresolvedParty':9}
 counts={r['type']:r['n'] for r in table('MATCH (n:GUGPilot) RETURN n.entity_type AS type,count(n) AS n')};assert counts==expect
 sample=table("MATCH (h:HoldingSnapshot {entity_id:'holding:20261021000306:shares_etc'}) RETURN h.shares AS shares,h.percentage AS percentage,toString(h.as_of_date) AS date,h.scope AS scope,valueType(h.shares) AS shares_type,valueType(h.percentage) AS percentage_type,valueType(h.as_of_date) AS date_type,h.denominator IS NULL AS unknown_denominator")
 assert sample[0]['shares']==1048415 and sample[0]['percentage']==24.15 and sample[0]['date']=='2026-10-14' and sample[0]['scope']=='reporting_group' and sample[0]['unknown_denominator']
 assert sample[0]['shares_type'].startswith('INTEGER') and sample[0]['percentage_type'].startswith('FLOAT') and sample[0]['date_type'].startswith('DATE')
 zero=table('MATCH (h:HoldingSnapshot) WHERE h.percentage=0 RETURN count(h) AS n')[0]['n'];assert zero>0
 stock=table("MATCH (c:Company {corp_code:'00608839'}) RETURN c.stock_code AS code")[0]['code'];assert stock=='096690'
 for id,attrs in [('holding:20261021000306:shares_etc',{'percentage':24.15}),('holding:20261021000238:specific_securities',{'date':'2026-06-25'})]:
  if 'date' in attrs:assert table('MATCH (h:HoldingSnapshot {entity_id:$id}) RETURN toString(h.as_of_date) AS date',{'id':id})[0]['date']==attrs['date']
 provenance=table('MATCH (a:Assertion) WHERE NOT EXISTS {MATCH (a)-[:SUPPORTED_BY]->(:EvidenceSpan)-[:LOCATED_IN]->(:DocumentVersion)} RETURN count(a) AS n')[0]['n'];assert provenance==0
 results=[]
 for i,q in enumerate(statements(PATHS.queries/'examples.cypher'),1):
  rows=table(q);assert rows;results.append({'query':i,'row_count':len(rows),'preview':rows[:2] if i not in [1,6] else 'Graph paths verified; view in Browser'})
 load();after=snapshot();assert before==after
 unauthorized=False
 try:urllib.request.urlopen(urllib.request.Request(__import__('os').environ.get('NEO4J_HTTP_URL','http://127.0.0.1:7474').rstrip('/')+'/db/neo4j/query/v2',data=b'{"statement":"RETURN 1"}',headers={'Content-Type':'application/json'}))
 except urllib.error.HTTPError as e:unauthorized=e.code==401
 assert unauthorized
 result={'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'components':components,'node_count':before['nodes'],'relationship_count':before['relationships'],'node_types':counts,'typed_sample':sample,'zero_values_preserved':zero,'stock_code_preserved':stock,'unlinked_assertions':provenance,'repeat_import_identical':True,'source_ids_and_relationship_endpoints_match':True,'unauthenticated_query_rejected':unauthorized,'queries':results,'credentials_location':str(PATHS.secrets/'neo4j-auth.json'),'llm_api_calls':0}
 (PATHS.artifacts/'neo4j/acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['queries','credentials_location']},ensure_ascii=False,indent=2))
if __name__=='__main__':verify()
