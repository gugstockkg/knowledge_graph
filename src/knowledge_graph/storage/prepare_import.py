"""Validate v0.1 graph CSV and expose typed, queryable scalar properties."""
from pathlib import Path
import csv,json,datetime,math,hashlib,re,argparse

from ..config import get_paths
PATHS=get_paths()
HERE=PATHS.graph
SOURCE=PATHS.graph/'stage2_twenty'
SCHEMA=PATHS.schema
DATES={'as_of_date','receipt_date','valid_from','valid_to','event_date'}
INTS={'shares','previous_reported_quantity','reported_quantity_delta','denominator','line','table','row','llm_calls'}
FLOATS={'percentage'}
BOOLS={'arithmetic_consistent','is_correction'}
BASE=['entity_id','entity_type','name','attributes_json']
def encode_scalar(value,typ=None):
 if value is None:return ''
 if isinstance(value,float) and not math.isfinite(value):raise ValueError('nonfinite numeric value')
 if typ=='date':datetime.date.fromisoformat(value)
 if isinstance(value,bool):return 'true' if value else 'false'
 if isinstance(value,(dict,list)):raise ValueError('nested value cannot be flattened')
 return str(value)
def readcsv(path):
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(path,headers,rows):
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)
def convert(source_dir,output_dir):
 source_dir=Path(source_dir);output_dir=Path(output_dir)
 nodes=readcsv(source_dir/'nodes.csv');rels=readcsv(source_dir/'relationships.csv')
 ids=[n['entity_id'] for n in nodes];rids=[r['relation_id'] for r in rels]
 if len(ids)!=len(set(ids)) or len(rids)!=len(set(rids)):raise ValueError('duplicate ID')
 allowed_types={r['개념 ID'] for r in readcsv(SCHEMA/'02_concept_definitions.csv')}
 allowed_rels={r['관계 ID'] for r in readcsv(SCHEMA/'03_relationship_definitions.csv')}
 for n in nodes:
  if n['entity_type'] not in allowed_types:raise ValueError('unknown entity type')
 for r in rels:
  if r['predicate'] not in allowed_rels:raise ValueError('unknown relationship type')
  if r['subject_id'] not in ids or r['object_id'] not in ids:raise ValueError('orphan relationship')
 columns=set();flat=[]
 for n in nodes:
  out={k:n[k] for k in BASE}
  for k,v in json.loads(n['attributes_json']).items():
   if k in BASE:raise ValueError('reserved attribute collision '+k)
   if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',k):raise ValueError('unsafe property name')
   if isinstance(v,(dict,list)):continue
   if k in INTS and v is not None and (isinstance(v,bool) or int(v)!=v):raise ValueError('invalid integer '+k)
   if k in FLOATS and v is not None and (isinstance(v,bool) or not isinstance(v,(int,float))):raise ValueError('invalid decimal '+k)
   if k in BOOLS and v is not None and not isinstance(v,bool):raise ValueError('invalid boolean '+k)
   columns.add(k);out[k]=encode_scalar(v,'date' if k in DATES and v is not None else None)
  flat.append(out)
 output_dir.mkdir(parents=True,exist_ok=True);writecsv(output_dir/'nodes.csv',BASE+sorted(columns),flat);writecsv(output_dir/'relationships.csv',list(rels[0]) if rels else ['relation_id','subject_id','predicate','object_id','attributes_json'],rels)
 manifest={'source_dir':str(source_dir),'nodes':len(nodes),'relationships':len(rels),'properties':sorted(columns),'source_sha256':{f:hashlib.sha256((source_dir/f).read_bytes()).hexdigest() for f in ['nodes.csv','relationships.csv']}}
 (output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 setters=['n.'+k+' = row.'+k for k in BASE if k!='entity_id']
 for k in sorted(columns):
  expr='row.'+k
  fn='date' if k in DATES else 'toInteger' if k in INTS else 'toFloat' if k in FLOATS else 'toBoolean' if k in BOOLS else None
  if fn:expr=fn+'('+expr+')'
  setters.append("n.`"+k+"` = CASE WHEN row.`"+k+"` = '' THEN null ELSE "+expr+" END")
 schema='CREATE CONSTRAINT pilot_entity_id IF NOT EXISTS FOR (n:GUGPilot) REQUIRE n.entity_id IS UNIQUE;\n'
 (output_dir/'schema.cypher').write_text(schema)
 load=["LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row MERGE (n:GUGPilot {entity_id:row.entity_id}) SET "+', '.join(setters)+';']
 for typ in sorted({n['entity_type'] for n in nodes}):load.append("MATCH (n:GUGPilot) WHERE n.entity_type='"+typ+"' SET n:"+typ+';')
 for p in sorted({r['predicate'] for r in rels}):load.append("LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row WITH row WHERE row.predicate='"+p+"' MATCH (a:GUGPilot {entity_id:row.subject_id}),(b:GUGPilot {entity_id:row.object_id}) MERGE (a)-[r:"+p+" {relation_id:row.relation_id}]->(b) SET r.attributes_json=row.attributes_json;")
 (output_dir/'load.cypher').write_text('\n'.join(load))
 return manifest
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=SOURCE);parser.add_argument('--output',type=Path,default=PATHS.imports);args=parser.parse_args();print(json.dumps(convert(args.source,args.output),ensure_ascii=False,indent=2))
