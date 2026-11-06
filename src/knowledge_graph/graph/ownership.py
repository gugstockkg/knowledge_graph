"""Bounded, offline research pilot against ontology v0.1; no LLM/API calls."""
from pathlib import Path
from html.parser import HTMLParser
import argparse,csv,json,hashlib,re,datetime,collections

from ..config import get_paths
PATHS=get_paths()
HERE=PATHS.graph
SOURCE=PATHS.collection
SCHEMA=PATHS.schema
VERSION='ownership-fields-v1'
COMPANIES=['00608839','01440153','01627363','00105606','01453944']
def digest(s):return hashlib.sha256(s.encode()).hexdigest()[:20]
def norm(s):return ' '.join(s.split())
def date(s):
 s=re.sub(r'\D','',s or '')
 if len(s)!=8:return None
 try:return datetime.datetime.strptime(s,'%Y%m%d').date().isoformat()
 except ValueError:return None
def number(s):
 s=(s or '').replace(',','').strip()
 if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',s):return None
 return float(s) if '.' in s else int(s)

from ..extraction.tagged import FieldParser

def select():
 filings=json.loads((SOURCE/'filings.json').read_text());chosen=[]
 for code in COMPANIES:
  for kind in ['large','officer']:
   rs=[r for r in filings if r['corp_code']==code and (('대량보유상황보고서' in r['report_nm']) if kind=='large' else ('특정증권등소유상황보고서' in r['report_nm']))]
   rs=sorted(rs,key=lambda r:(r['rcept_dt'],r['rcept_no']))
   corr=[r for r in rs if '정정' in r['report_nm']];plain=[r for r in rs if '정정' not in r['report_nm']]
   picks=[]
   if corr:picks.append(corr[0])
   if plain:picks.append(plain[0])
   for r in rs:
    if len(picks)>=2:break
    if r not in picks:picks.append(r)
   for r in picks:r=dict(r);r['kind']=kind;r['selection_reason']='5개 기업 × 2양식 × 2건; 정정 및 일반 공시 우선';chosen.append(r)
 return chosen

def extract(r):
 folder=SOURCE/'documents'/r['corp_code']/r['rcept_no'];files=sorted(folder.glob('*.xml'))
 matches=[]
 for x in files:
  raw=x.read_bytes()
  try:text=raw.decode('utf-8')
  except UnicodeDecodeError:text=raw.decode('cp949',errors='replace')
  if ('00634' in text[:2000] if r['kind']=='officer' else ('00636' in text[:2000] or '00637' in text[:2000])):matches.append((x,raw,text))
 if len(matches)!=1:raise ValueError('expected one primary form '+r['rcept_no'])
 x,raw,text=matches[0];p=FieldParser();p.feed(text);fields=p.fields
 # Whitelist excludes contact, birth dates, addresses, registration and account identifiers.
 keys=['IFR_NM','IFR_TP','CRP_TP','RPT_DST2','RPT_REF_DT','CRP_CD','FLT_SUM','FLT_STK_CNT','AFR_RPT_DT','BFR_RPT_DT','THS_RPT_DT','AFR_UN_CNT','AFR_UN_RT','AFR_PS_CPT_CNT','AFR_PS_CPT_RT','BFR_UN_CNT','BFR_UN_RT','BFR_PS_CPT_CNT','BFR_PS_CPT_RT','MDF_UN_CNT','MDF_PS_CPT_CNT','THS_STK_CNT','THS_STK_RT','THS_CMT_CNT','THS_CMT_RT','THS_STK_CT','BFR_STK_CNT','BFR_CMT_CNT','MDF_STK_CNT','MDF_CMT_CNT','STF_PSM','STF_RYN']
 selected={};conflicts=[]
 for k in keys:
  fs=[v for v in fields if v['key']==k]
  if fs:
   selected[k]=fs[-1]
   if len({v['text'] for v in fs})>1:conflicts.append(k)
 summary=[]
 if r['kind']=='officer':
  configurations=[('specific_securities','AFR_UN_CNT','AFR_UN_RT','BFR_UN_CNT','MDF_UN_CNT'),('share_certificates','AFR_PS_CPT_CNT','AFR_PS_CPT_RT','BFR_PS_CPT_CNT','MDF_PS_CPT_CNT')]
  dt='AFR_RPT_DT';scope='individual';basis='reported_ownership'
 else:
  configurations=[('shares_etc','THS_STK_CNT','THS_STK_RT','BFR_STK_CNT','MDF_STK_CNT'),('share_certificates','THS_CMT_CNT','THS_CMT_RT','BFR_CMT_CNT','MDF_CMT_CNT')]
  dt='THS_RPT_DT';basis='reported_holding'
  # The summary table covers reporter + related parties; do not assign its total to reporter personally.
  reporting=selected.get('RPT_DST2',{}).get('text','')
  scope='reporting_group' if '연명' in reporting else 'individual' if ('단명' in reporting or '개별' in reporting) else 'unknown'
 for category,qty,pct,prev,delta in configurations:
  def val(k):return selected.get(k,{}).get('text')
  current=number(val(qty));previous=number(val(prev));change=number(val(delta));ratio=number(val(pct));asof=date(selected.get(dt,{}).get('unit_value') or val(dt))
  summary.append({'category':category,'shares':current,'percentage':ratio,'as_of_date':asof,'previous_reported_quantity':previous,'reported_quantity_delta':change,'arithmetic_consistent':(current-previous==change) if all(v is not None for v in [current,previous,change]) else None,'quantity_field':qty,'ratio_field':pct,'date_field':dt,'scope':scope,'holding_basis':basis})
 return {'filing':r,'source_path':str(x),'sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw),'raw_chars':len(text),'fields':selected,'field_conflicts':conflicts,'holdings':summary,'compact_chars':len(json.dumps(selected,ensure_ascii=False))}

def writecsv(path,headers,rows):
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)

def run(limit):
 out=HERE/('stage1_three' if limit==3 else 'stage2_twenty');out.mkdir(parents=True,exist_ok=True)
 chosen=select()[:limit];records=[extract(r) for r in chosen]
 (out/'extracted.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 print(json.dumps([{'receipt':e['filing']['rcept_no'],'company':e['filing']['corp_name'],'kind':e['filing']['kind'],'reporter':e['fields'].get('IFR_NM',{}).get('text'),'reporter_type':e['fields'].get('IFR_TP',e['fields'].get('CRP_TP',{})).get('text'),'corrected':'정정' in e['filing']['report_nm'],'conflicts':e['field_conflicts'],'holdings':e['holdings']} for e in records],ensure_ascii=False,indent=2))
 nodes={};edges={};evidences=[];checks=[];assertions=[]
 def node(id,typ,name,attrs):
  if id not in nodes:nodes[id]={'entity_id':id,'entity_type':typ,'name':name,'attributes_json':json.dumps(attrs,ensure_ascii=False)}
  return id
 def edge(a,p,z,attrs=None):
  key=digest(a+'|'+p+'|'+z+'|'+json.dumps(attrs or {},sort_keys=True));edges[key]={'relation_id':key,'subject_id':a,'predicate':p,'object_id':z,'attributes_json':json.dumps(attrs or {},ensure_ascii=False)}
 runid=node('run:'+digest(VERSION+'|'+str(limit)),'ExtractionRun',VERSION,{'method':'rule','ontology_version':'0.1','llm_calls':0})
 for e in records:
  r=e['filing'];receipt=r['rcept_no'];fields=e['fields'];company=node('company:'+r['corp_code'],'Company',r['corp_name'],{'corp_code':r['corp_code'],'stock_code':r['stock_code']});filing=node('filing:'+receipt,'Filing',r['report_nm'],{'receipt_date':date(r['rcept_dt']),'source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,'is_correction':'정정' in r['report_nm']});doc=node('doc:'+receipt+':'+e['sha256'][:16],'DocumentVersion',Path(e['source_path']).name,{'sha256':e['sha256'],'source_path':e['source_path']});edge(filing,'IS_ABOUT',company);edge(filing,'HAS_DOCUMENT',doc)
  rawname=fields.get('IFR_NM',{}).get('text') or r['flr_nm'];tp=fields.get('IFR_TP',fields.get('CRP_TP',{})).get('text','');typ='Person' if '개인' in tp else 'Organization' if '법인' in tp else 'UnresolvedParty'
  actor=node('reporter:'+receipt,'{}'.format(typ),rawname,{'resolution_status':'filing_scoped_provisional','reporter_type':tp,'name_evidence':fields.get('IFR_NM'),'type_evidence':fields.get('IFR_TP',fields.get('CRP_TP'))});edge(filing,'SUBMITTED_BY',actor)
  if r['kind']=='large' and e['holdings'][0]['scope']!='individual':holder=node('group:'+receipt,'UnresolvedParty',rawname+' 외 보고집단',{'resolution_status':'report_scoped_group_placeholder','note':'대표 보고자의 개인 보유량으로 해석 금지; 연명 또는 미확정 합산 범위'})
  else:holder=actor
  def evidence(k):
   if k not in fields:return None
   v=fields[k];id='evidence:'+receipt+':'+digest(v['path']);node(id,'EvidenceSpan',k,{'line':v['line'],'path':v['path'],'table':v['table'],'row':v['row'],'quote':v['text']});edge(id,'LOCATED_IN',doc)
   evidences.append({'evidence_id':id,'receipt_no':receipt,'field':k,'text':v['text'],'line':v['line'],'table':v['table'],'row':v['row'],'path':v['path'],'source_path':e['source_path'],'document_sha256':e['sha256']});return id
  for h in e['holdings']:
   status='needs_review' if ('정정' in r['report_nm'] or e['field_conflicts'] or h['shares'] is None or h['as_of_date'] is None) else 'candidate'
   sid=node('holding:'+receipt+':'+h['category'],'HoldingSnapshot',h['category'],{**h,'verification_status':status,'scope_evidence':fields.get('RPT_DST2'),'denominator':None,'denominator_basis':'not_confirmed_for_this_category','note':'증권 종류·분모 미확정. 주식등과 주권 현황은 중복 합산 금지'})
   edge(sid,'HELD_BY',holder);edge(sid,'HOLDING_IN_COMPANY',company)
   for prop,k in [('shares',h['quantity_field']),('percentage',h['ratio_field']),('as_of_date',h['date_field'])]:
    ev=evidence(k)
    if not ev:continue
    aid=node('assertion:'+receipt+':'+h['category']+':'+prop,'Assertion',prop,{'predicate':prop,'literal_value':h[prop],'verification_status':status,'ontology_version':'0.1'});edge(aid,'HAS_SUBJECT',sid);edge(aid,'SUPPORTED_BY',ev);edge(aid,'GENERATED_BY',runid);assertions.append({'assertion_id':aid,'subject_id':sid,'property':prop,'value':h[prop],'evidence_id':ev,'verification_status':status})
   checks.append({'receipt_no':receipt,'category':h['category'],'arithmetic_consistent':h['arithmetic_consistent'],'required_present':h['shares'] is not None and h['percentage'] is not None and h['as_of_date'] is not None,'percentage_in_range':h['percentage'] is not None and 0<=h['percentage']<=100,'field_conflicts':';'.join(e['field_conflicts']),'review_status':status})
 allowed_nodes={x['개념 ID'] for x in csv.DictReader((SCHEMA/'02_concept_definitions.csv').open(encoding='utf-8-sig'))};allowed_rels={x['관계 ID'] for x in csv.DictReader((SCHEMA/'03_relationship_definitions.csv').open(encoding='utf-8-sig'))}
 assert all(n['entity_type'] in allowed_nodes for n in nodes.values())
 assert all(v['predicate'] in allowed_rels and v['subject_id'] in nodes and v['object_id'] in nodes for v in edges.values())
 evidences=list({v['evidence_id']:v for v in evidences}.values())
 for name,rows in [('nodes',list(nodes.values())),('relationships',list(edges.values())),('evidence',evidences),('assertions',assertions),('checks',checks),('sample_manifest',chosen)]:writecsv(out/(name+'.csv'),list(rows[0]),rows)
 summary={'ontology_version':'0.1','parser_version':VERSION,'filings':len(records),'companies':len({e['filing']['corp_code'] for e in records}),'nodes':len(nodes),'relationships':len(edges),'holdings':sum(len(e['holdings']) for e in records),'raw_bytes':sum(e['raw_bytes'] for e in records),'raw_chars':sum(e['raw_chars'] for e in records),'compact_chars':sum(e['compact_chars'] for e in records),'llm_calls':0,'llm_api_tokens':0,'checks_all_required':all(c['required_present'] for c in checks),'arithmetic_failures':sum(c['arithmetic_consistent'] is False for c in checks),'node_types':dict(collections.Counter(n['entity_type'] for n in nodes.values())),'relation_types':dict(collections.Counter(v['predicate'] for v in edges.values()))}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print('SUMMARY',json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,choices=[3,20],default=3);run(p.parse_args().limit)
