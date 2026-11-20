"""Offline deterministic availability-conditioned sample. No network, DB or source writes."""
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
COL=ROOT/'data/raw/opendart/collections'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def classify(n):
 if '철회' in n or '해지' in n:return 'withdrawal_or_termination'
 if '정정' in n and ('계약' in n or '주요사항' in n):return 'correction'
 if '대량보유' in n:return 'holding'
 if '특정증권등소유' in n:return 'officer_ownership'
 if '판매' in n and '계약' in n:return 'supply_contract'
 if '주주총회' in n or '선임' in n:return 'governance'
 if ('분할' in n or '합병' in n or '양수' in n or '유상증자결정' in n):return 'corporate_action'
 if re.match(r'(사업|반기|분기)보고서',n):return 'financial_periodic'
 return None

class Rows(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.row=None;self.cell=None;self.rows=[]
 def handle_starttag(self,t,a):
  if t=='tr':self.row=[];self.line=self.getpos()[0]
  if t in ('td','th','te','tu') and self.row is not None:self.cell=[]
 def handle_data(self,d):
  if self.cell is not None:self.cell.append(d)
 def handle_endtag(self,t):
  if t in ('td','th','te','tu') and self.cell is not None:
   if self.row is not None:self.row.append(' '.join(' '.join(self.cell).split()))
   self.cell=None
  if t=='tr' and self.row is not None:self.rows.append((self.line,self.row));self.row=None

def main():
 sources=[];rows={}
 for cid in ['20260101_20261105','20261001_20261105','20261106_20261108']:
  p=COL/cid/'filings.json';rs=json.loads(p.read_text());sources.append({'path':str(p.relative_to(ROOT)),'count':len(rs),'sha256':sha(p)})
  for r in rs:
   if r['rcept_no'] not in rows:rows[r['rcept_no']]={**r,'list_source':str(p.relative_to(ROOT))}
 strata={k:[] for k in ['holding','officer_ownership','supply_contract','correction','withdrawal_or_termination','governance','corporate_action','financial_periodic']}
 for r in rows.values():
  k=classify(r['report_nm'].strip())
  if k:strata[k].append(r)
 selected=[];availability_attempts={}
 for k,rs in strata.items():
  # Hash order avoids selecting only the earliest filings. Not probability sampling.
  rs.sort(key=lambda r:hashlib.sha256(('ontology-eval-20261113|'+r['rcept_no']).encode()).hexdigest())
  picked=[];attempts=0
  for r in rs:
   attempts+=1
   found=None
   for cid in ['20260101_20261105','20261001_20261105','20261106_20261108']:
    p=COL/cid/'documents'/r['corp_code']/(r['rcept_no']+'.zip')
    if p.is_file() and zipfile.is_zipfile(p):
     with zipfile.ZipFile(p) as z:
      members=[{'name':i.filename,'bytes':i.file_size,'sha256':hashlib.sha256(z.read(i)).hexdigest()} for i in z.infolist() if i.filename.lower().endswith(('.xml','.html','.htm'))]
     if members:found=(p,members);break
   if not found:continue
   p,members=found
   picked.append({'sample_id':'S%02d'%(len(selected)+len(picked)+1),'stratum':k,'receipt_no':r['rcept_no'],'receipt_date':r['rcept_dt'],'report_name':r['report_nm'].strip(),'corp_code':r['corp_code'],'corp_name':r['corp_name'],'correction_title_flag':'정정' in r['report_nm'],'withdrawal_or_termination_title_flag':any(t in r['report_nm'] for t in ['철회','해지']),'list_source':r['list_source'],'zip_path':str(p.relative_to(ROOT)),'zip_exists':True,'zip_sha256':sha(p),'document_members':members,'review_scope':'archive/member existence and hashes; source semantics not reviewed','human_review_status':'not_reviewed','split':'holdout_reserved' if len(picked)>=4 else 'development','correction_predecessor_verified':False})
   if len(picked)==6:break
  availability_attempts[k]={'title_candidates':len(rs),'checked_until_quota':attempts,'selected':len(picked)};selected.extend(picked)
 # One representative per stratum, at most 5 table rows x 160 chars. Never export entire text.
 targets={'holding':r'보고구분|보고서작성기준일|보유주식|보유비율|보유상황|연명|단명','officer_ownership':r'보고서작성기준일|특정증권|소유주식|소유상황','supply_contract':r'계약금액|계약상대|유보사유|종료일','correction':r'정정대상|정정사항|정정전|정정후|정정 전|정정 후|계약금액','withdrawal_or_termination':r'철회|해지|해제|관련공시','governance':r'선임|후보|주주총회|일시','corporate_action':r'분할기일|합병기일|예정|결정일|취득예정|납입일','financial_periodic':r'연결재무|별도재무|당분기|누적|당기순이익|매출액'}
 for k in strata:
  s=next((x for x in selected if x['stratum']==k),None)
  if not s:continue
  with zipfile.ZipFile(ROOT/s['zip_path']) as z:
   member=max(s['document_members'],key=lambda x:x['bytes'])['name'];b=z.read(member)
  try:t=b.decode('utf-8')
  except UnicodeDecodeError:t=b.decode('cp949',errors='replace')
  parser=Rows();parser.feed(t);matches=[]
  for line,cells in parser.rows:
   # Exclude personal and contact rows; excerpt is a bounded observation, not a truth label.
   joined=' | '.join(cells)
   if re.search(r'주민|생년|주소|연락처|전화|성명|담당자|팩스|신규선임여부',joined):continue
   if re.search(targets[k],joined):
    matches.append({'line':line,'cells_excerpt':joined[:160]})
    if len(matches)==5:break
  s['review_scope']='AI inspected only listed bounded table excerpts; locally parsed table structure, not full semantic review'
  s['bounded_observation']={'member':member,'matching_rows_returned':len(matches),'max_rows':5,'max_chars_per_row':160,'rows':matches,'status':'AI_observation_unreviewed_not_gold'}
 result={'created_on':'2026-11-13','purpose':'48-file offline evaluation candidate set, not human-validated gold','method':'mutually exclusive title strata; deterministic SHA256 order; six available ZIP+XML/HTML per stratum; availability-conditioned purposive sample','split_note':'first four each stratum development, last two reserved holdout; representative reading restricted to first development sample; prior project exposure unknown, so not pristine holdout','sources':sources,'stratum_selection':availability_attempts,'selected_count':len(selected),'counts':dict(Counter(x['stratum'] for x in selected)),'privacy':'Only archive references, hashes and bounded public business table excerpts; no source archives copied. Individual reporter names omitted.','samples':selected}
 (OUT/'SAMPLE_MANIFEST.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'selected':len(selected),'strata':result['counts'],'attempts':availability_attempts,'bounded_representatives':sum('bounded_observation' in x for x in selected)},ensure_ascii=False))
if __name__=='__main__':main()
