from pathlib import Path
import json,csv,hashlib,subprocess,sys,zipfile,os
from .ownership import HERE,SCHEMA,writecsv
from ..config import get_paths
PATHS=get_paths()

out=HERE/'stage2_twenty';rs=json.loads((out/'extracted.json').read_text());summary=json.loads((out/'summary.json').read_text())
# Recorded after direct inspection of source tags, not generated from extractor output.
gold=[('20261021000257','최정임','2026-06-04',783687,19.10,702439,17.46),('20261021000306','최정임','2026-10-14',1048415,24.15,730096,18.15),('20261021000238','이대성','2026-06-25',81461,2.01,61230,1.52)]
grows=[]
for receipt,name,dt,q,p,sq,sp in gold:
 e=next(r for r in rs if r['filing']['rcept_no']==receipt);expected=[name,dt,q,p,sq,sp];actual=[e['fields']['IFR_NM']['text'],e['holdings'][0]['as_of_date'],e['holdings'][0]['shares'],e['holdings'][0]['percentage'],e['holdings'][1]['shares'],e['holdings'][1]['percentage']]
 for field,a,z in zip(['보고자','기준일','특정증권등/주식등 수량','특정증권등/주식등 비율','주권 수량','주권 비율'],expected,actual):grows.append({'접수번호':receipt,'필드':field,'원문 직접대조 기준값':a,'추출값':z,'일치':a==z,'검증자':'에이전트 원문 직접 대조; 독립 사람 검수 아님'})
assert all(x['일치'] for x in grows)
writecsv(out/'source_spotcheck.csv',list(grows[0]),grows)
with (out/'evidence.csv').open(encoding='utf-8-sig',newline='') as f:evidence=list(csv.DictReader(f))
for e in evidence:
 line=Path(e['source_path']).read_text().splitlines()[int(e['line'])-1]
 assert ('ACODE="'+e['field']+'"') in line or ('AUNIT="'+e['field']+'"') in line,(e['receipt_no'],e['field'])
files=['nodes.csv','relationships.csv','assertions.csv','evidence.csv','checks.csv']
before={f:hashlib.sha256((out/f).read_bytes()).hexdigest() for f in files}
subprocess.run([sys.executable,'-m','knowledge_graph.graph.ownership','--limit','20'],check=True,stdout=subprocess.DEVNULL,env={**os.environ,'PYTHONPATH':str(PATHS.root/'src')})
after={f:hashlib.sha256((out/f).read_bytes()).hexdigest() for f in files};assert before==after
summary['validation']={'source_spotcheck_fields':len(grows),'source_spotcheck_matches':sum(x['일치'] for x in grows),'source_line_checks':len(evidence),'deterministic_rerun':True,'holdout_accuracy_evaluated':False}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
flat=[]
for e in rs:
 r=e['filing']
 for h in e['holdings']:
  flat.append({'기업명':r['corp_name'],'접수번호':r['rcept_no'],'공시명':r['report_nm'],'접수일':r['rcept_dt'],'보고자':e['fields']['IFR_NM']['text'],'범위':h['scope'],'항목':h['category'],'기준일':h['as_of_date'],'수량':h['shares'],'비율(%)':h['percentage'],'직전보고수량':h['previous_reported_quantity'],'보고된증감수량':h['reported_quantity_delta'],'수량산술일치':h['arithmetic_consistent'],'검토상태':'needs_review' if ('정정' in r['report_nm'] or e['field_conflicts']) else 'candidate','수량근거행':e['fields'][h['quantity_field']]['line'],'수량필드':h['quantity_field'],'원문경로':e['source_path'],'공식링크':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+r['rcept_no'],'팀 검토 의견':''})
writecsv(out/'holdings_review.csv',list(flat[0]),flat)
q=[]
for id,question,receipt,category in [('Q1','에이루트의 2026-10-14 연명 보고 주식등 보유현황과 근거는?','20261021000306','shares_etc'),('Q2','같은 공시 안의 직전보고 대비 수량 변화는?','20261021000306','shares_etc'),('Q3','10월 접수된 정정 보고서의 현황 기준일은 언제인가?','20261021000238','specific_securities')]:
 e=next(r for r in rs if r['filing']['rcept_no']==receipt);h=next(h for h in e['holdings'] if h['category']==category)
 answer=(f"연명 보고집단 {h['shares']:,}주, {h['percentage']}%; 대표 보고자 개인 보유와 구분" if id=='Q1' else f"직전 {h['previous_reported_quantity']:,} → 이번 {h['shares']:,}, 보고 증감 {h['reported_quantity_delta']:,}" if id=='Q2' else f"접수일 {e['filing']['rcept_dt']}; 현황 기준일 {h['as_of_date']}; 제출일로 대체 금지")
 q.append({'질문ID':id,'질문':question,'파일럿 답변':answer,'접수번호':receipt,'근거필드':h['quantity_field']+'; '+h['ratio_field']+'; '+h['date_field'],'근거경로':e['source_path'],'상태':'추출 후보 기준 응답; 사람 검수 전'})
writecsv(out/'competency_answers.csv',list(q[0]),q)
types=summary['node_types'];rels=summary['relation_types']
cypher=['// Neo4j Community용 선택적 적재. 아래 CSV를 Neo4j import 디렉터리에 복사한 뒤 실행.', '// attrs_json은 문자열로 보존; 수치·날짜의 Neo4j 속성 변환은 후속 작업. APOC 불필요.', 'CREATE CONSTRAINT pilot_entity_id IF NOT EXISTS FOR (n:GUGPilot) REQUIRE n.entity_id IS UNIQUE;', "LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row MERGE (n:GUGPilot {entity_id:row.entity_id}) SET n.entity_type=row.entity_type,n.name=row.name,n.attributes_json=row.attributes_json;"]
for t in types:cypher.append(f"MATCH (n:GUGPilot) WHERE n.entity_type='{t}' SET n:{t};")
for p in rels:cypher.append(f"LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row WITH row WHERE row.predicate='{p}' MATCH (a:GUGPilot {{entity_id:row.subject_id}}),(b:GUGPilot {{entity_id:row.object_id}}) MERGE (a)-[r:{p} {{relation_id:row.relation_id}}]->(b) SET r.attributes_json=row.attributes_json;")
(out/'import_neo4j.cypher').write_text('\n'.join(cypher))
reduction=100*(1-summary['compact_chars']/summary['raw_chars']);groups=sum(e['holdings'][0]['scope']=='reporting_group' for e in rs if e['filing']['kind']=='large');corrected=sum('정정' in e['filing']['report_nm'] for e in rs)
report=f'''# v0.1 공시 지분 파일럿 결과

## 결과
기업 5개(에이루트·넥사다이내믹스·세미파이브·금호에이치티·벡트로보틱스), 공시 20건. 대량보유 10건과 임원·주요주주 소유상황 10건. 정정 {corrected}건 포함. 목록·원문·온톨로지 v0.1은 수정하지 않았습니다.

원문에서 현재 보고 수량·비율·기준일과 직전 수량·보고 증감을 추출했습니다. {summary['holdings']}개 보유현황을 {summary['nodes']}개 노드와 {summary['relationships']}개 관계로 표현했습니다. 노드·관계 수에는 문서·근거·주장 등 관리 객체가 포함되며 경제적 관계 {summary['relationships']}개를 발견했다는 뜻은 아닙니다. 원본 설계도의 개념 ID·관계 ID만 사용했습니다.

## 효율
20건 원문 {summary['raw_bytes']:,}바이트 / {summary['raw_chars']:,}문자에서 선택 필드와 원문 위치를 {summary['compact_chars']:,}문자로 축소했습니다. 문자 수 기준 약 {reduction:.1f}% 감소이며 토큰 절감률 측정은 아닙니다. 추출용 LLM API 호출 0회, 외부 모델 API 토큰 0개입니다. 이 대화의 읽기·추론에 소비된 토큰을 0이라고 뜻하지 않습니다. 추가 다운로드·추출 서비스 호출·Neo4j 서버 설치는 하지 않았습니다.

원문 전체를 LLM에 보내는 대신 ACODE/AUNIT 필드 표식과 AUNITVALUE를 사용했습니다. 필드의 표 번호·행 번호·원본 줄 번호·문서 해시를 보존했습니다. 동일 문서 해시/추출 버전 결과를 재사용할 수 있는 기반이며 영구 자동 캐시 서비스는 아직 구현하지 않았습니다.

## 검증
- 첫 3건에서 원문 태그를 직접 대조해 보고자·기준일·수량·비율 18개 값 일치. 같은 표본을 본 에이전트의 대조이며 독립 사람 검수나 미사용 검증셋 정확도가 아닙니다.
- 전체 40개 현황에서 수량·비율·기준일 확보, 직전 수량 + 보고 증감 = 현재 수량 산술 검사 통과. 비율 분모가 달라질 수 있어 비율 재계산은 실시하지 않았습니다.
- 근거 100개에서 원문 줄의 필드 코드 확인. 모든 관계의 양끝 노드 존재, v0.1 개념·관계 ID 준수 확인.
- 재실행 후 nodes/relationships/assertions/evidence/checks CSV 해시 동일. 검증 가능한 반복 실행 결과입니다.
- 모든 추출은 candidate 또는 needs_review로 보존했습니다. validated로 자동 승격하지 않았습니다.

## 발견한 의미 차이
1. 대량보유 표의 '주식등'과 '주권'은 서로 다른 열입니다. '주권'을 '의결권주식'으로 명명하려던 초기 오류를 원문 표 머리글 대조로 수정했습니다. 두 현황을 더하면 중복 계산됩니다.
2. 대량보유 10건 중 연명 {groups}건은 보고자 외 관계자 합산입니다. 대표 개인에게 합산 수량을 부여하지 않고 문서별 UnresolvedParty 집단 자리표시자로 연결했습니다. 나머지 개별 보고는 보고자에 연결했습니다. 집단은 v0.1의 임시 표현이며 확정 실체가 아닙니다.
3. 20261021000238은 10월 접수이지만 현황 기준일은 2026-06-25입니다. 정정 공시 때문에 수집기간과 사실 기준일이 달라집니다.
4. 같은 코드가 거래내역 여러 행에서 반복됩니다. 이번 추출은 요약표 필드를 대상으로 하고 충돌 코드 목록을 남겼습니다. 마지막 값을 선택한 필드의 의미는 사람 검수 전 확정하지 않습니다.
5. 같은 이름은 문서별 임시 ID로 남겼습니다. 실제 같은 사람·기관이라는 병합을 하지 않았으므로 기업 간 다중 홉 인물 분석은 아직 불가합니다.

## 아직 만들지 않은 것
개별 매매행 OwnershipChange, 증권 종류별 Security, 보고된 임원 재임 ExecutiveTenure는 이번 결과에 생성하지 않았습니다. 거래행·역할·증권 종류를 확인하지 않은 상태에서 추측하여 연결하지 않기 위함입니다. 증감 수량은 현황 속성으로 보존했습니다. 정정의 원공시를 CORRECTS로 연결하거나 최신 유효 현황을 확정하는 작업도 미실시입니다. 전체 초기 보유 상태를 복원한 결과가 아닙니다.

## 확인할 파일
- holdings_review.csv: 팀원이 먼저 확인할 한글 보유현황 표 40행.
- nodes.csv / relationships.csv: 원본 v0.1으로 표현한 그래프 후보.
- evidence.csv / assertions.csv: 수치·기준일과 원문 위치 연결.
- source_spotcheck.csv / checks.csv: 직접 대조·자동 검증 결과.
- competency_answers.csv: 질문 3개와 근거 연결 예시.
- extracted.json: 원문 재독 없이 검토할 화이트리스트 필드와 위치.
- sample_manifest.csv / summary.json: 표본 선정·범위·통계.
- import_neo4j.cypher: CSV를 Neo4j import 디렉터리에 복사한 뒤 실행하는 선택적 적재 스크립트. 실제 DB 적재는 아직 하지 않았습니다.

## 다음 작업 권장
팀원이 먼저 holdings_review.csv의 정정·합산 사례를 검수한 뒤, 동일 회사의 같은 보고자·기준일을 가진 정정 전후 문서를 짝지어 비교합니다. 집단 구성원 추출, 보고자 식별, 증권 종류 확인을 통과한 경우에만 Security·OwnershipChange와 원공시 연결을 추가하세요. 다음 20건은 다른 기업에서 선정하여 추출 규칙을 수정하지 않고 평가해야 일반화 정도를 알 수 있습니다. 현재 표본은 가용성과 경계 사례 중심의 목적 표본이며 시장 전체 대표 표본은 아닙니다.

재실행: python3 scripts/kg.py graph --limit 20
검증·리포트: python3 scripts/kg.py report
'''
(out/'REPORT.md').write_text(report)
bundle=HERE/'ownership_pilot_v01_results.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.iterdir()):
  if p.is_file():z.write(p,'ownership_pilot_v01/'+p.name)
 for p in [Path(__file__),Path(__file__).with_name('ownership.py')]:z.write(p,'ownership_pilot_v01/code/'+p.name)
print(json.dumps(summary,ensure_ascii=False,indent=2));print('ZIP',bundle)
