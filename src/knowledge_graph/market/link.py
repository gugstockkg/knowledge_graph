"""Link a validated daily-price snapshot to v0.1 Security/PriceObservation."""
import argparse,csv,json,hashlib
from ..config import get_paths
from ..storage.manage import table,query,wait_ready

def build_payload(manifest):
 if manifest.get('failures'):raise ValueError('Incomplete download: do not import')
 securities=[];prices=[];seen=set()
 for snapshot in manifest['snapshots']:
  if snapshot['mapping_status']!='name_match' or not snapshot['bars']:raise ValueError('Unverified company-symbol mapping or empty series')
  code=snapshot['stock_code'];sid='security:naver:'+code
  securities.append({'entity_id':sid,'company_id':snapshot['company_id'],'properties':{'name':snapshot['provider_name']+' ('+code+')','stock_code':code,'source':'NAVER_FCHART','security_type':'equity','currency':'KRW','identity_status':'source_symbol_provisional'}})
  for bar in snapshot['bars']:
   pid='price:'+manifest['dataset_id']+':'+code+':'+bar['date']
   if pid in seen:raise ValueError('duplicate price identity')
   seen.add(pid)
   properties={k:v for k,v in bar.items() if k!='date'}
   properties.update({'name':bar['date']+' · '+snapshot['provider_name'],'trade_date':bar['date'],'stock_code':code,'source':'NAVER_FCHART','dataset_id':manifest['dataset_id'],'interval':'1d','currency':'KRW','source_url':snapshot['source_url'],'retrieved_at':snapshot['retrieved_at'],'raw_sha256':snapshot['raw_sha256'],'adjustment_status':'provider_adjustment_unverified'})
   prices.append({'entity_id':pid,'security_id':sid,'properties':properties})
 if len(prices)!=manifest['prices']:raise ValueError('price count mismatch')
 return securities,prices

def link(directory):
 paths=get_paths();manifest=json.loads((directory/'manifest.json').read_text());securities,prices=build_payload(manifest);wait_ready()
 allowed={r['개념 ID'] for r in csv.DictReader((paths.schema/'02_concept_definitions.csv').open(encoding='utf-8-sig'))}
 if not {'Security','PriceObservation'}<=allowed:raise ValueError('missing v0.1 concepts')
 company_ids=[s['company_id'] for s in securities]
 found=table('MATCH (c:Company) WHERE c.entity_id IN $ids RETURN c.entity_id AS id',{'ids':company_ids})
 if sorted(r['id'] for r in found)!=sorted(company_ids):raise ValueError('KG company mapping mismatch')
 before=table('MATCH (n:GUGPilot) RETURN count(n) AS n')[0]['n']
 before_rel=table('MATCH (:GUGPilot)-[r]->(:GUGPilot) RETURN count(r) AS n')[0]['n']
 query('CREATE CONSTRAINT market_entity_id IF NOT EXISTS FOR (n:MarketPilot) REQUIRE n.entity_id IS UNIQUE')
 query('UNWIND $rows AS row MATCH (c:Company {entity_id:row.company_id}) MERGE (s:MarketPilot:Security {entity_id:row.entity_id}) SET s += row.properties MERGE (s)-[:ISSUED_BY]->(c)',{'rows':securities})
 params={'rows':prices,'source':'NAVER_FCHART','symbols':[s['properties']['stock_code'] for s in securities]}
 loaded=table('MATCH (old:MarketPilot:PriceObservation) WHERE old.source=$source AND old.stock_code IN $symbols SET old.active=false WITH count(old) AS previous UNWIND $rows AS row MATCH (s:MarketPilot:Security {entity_id:row.security_id}) MERGE (p:MarketPilot:PriceObservation {entity_id:row.entity_id}) SET p += row.properties,p.trade_date=date(row.properties.trade_date),p.active=true MERGE (p)-[:PRICE_OF]->(s) RETURN count(p) AS n',params)[0]['n']
 if loaded!=len(prices):raise RuntimeError('partial market import')
 assert table('MATCH (n:GUGPilot) RETURN count(n) AS n')[0]['n']==before
 assert table('MATCH (:GUGPilot)-[r]->(:GUGPilot) RETURN count(r) AS n')[0]['n']==before_rel
 result={'dataset_id':manifest['dataset_id'],'security_nodes':len(securities),'active_price_nodes':loaded,'core_nodes_preserved':before,'core_relationships_preserved':before_rel,'company_mapping':'provider and DART names matched; security IDs remain provider-specific','prediction_model_trained':False}
 (directory/'neo4j_import.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--dataset',type=__import__('pathlib').Path,default=get_paths().data/'market/naver_daily/20260901_20261105');args=p.parse_args();link(args.dataset)
