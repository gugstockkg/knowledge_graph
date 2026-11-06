"""Bounded public daily prices; no credentials, model calls or forecasts."""
import argparse,csv,datetime as dt,hashlib,json,re,ssl,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path
from ..config import get_paths

SOURCE='NAVER_FCHART'
def parse_chart(body,symbol,start,end):
 start=dt.date.fromisoformat(start).isoformat();end=dt.date.fromisoformat(end).isoformat()
 declared=re.search(br'encoding=[\x22\x27]([^\x22\x27]+)',body[:160],re.I)
 encoding=declared.group(1).decode('ascii') if declared else 'utf-8'
 root=ET.fromstring(body.decode(encoding));chart=root.find('chartdata')
 if chart is None or chart.get('symbol')!=symbol:raise ValueError('chart symbol mismatch or missing data')
 rows=[];seen=set()
 for item in chart.iter('item'):
  parts=item.get('data','').split('|')
  if len(parts)!=6:raise ValueError('unexpected daily-price format')
  day=dt.datetime.strptime(parts[0],'%Y%m%d').date().isoformat()
  if day in seen:raise ValueError('duplicate daily price')
  seen.add(day)
  if not start<=day<=end:continue
  values=[int(v) for v in parts[1:]];o,h,l,c,v=values
  if any(x<0 for x in values):raise ValueError('negative daily price/volume')
  halted=(o==h==l==0 and v==0)
  if not halted and not (o>0 and c>0 and l>0 and h>=max(o,c) and l<=min(o,c) and h>=l):raise ValueError('inconsistent OHLC')
  rows.append(dict(date=day,open=o,high=h,low=l,close=c,volume=v,is_tradable=o>0 and c>0 and v>0))
 rows.sort(key=lambda r:r['date'])
 return dict(chart.attrib),rows

def event_returns(receipt_date,bars,horizons=(1,5,20)):
 future=sorted((r for r in bars if r['date']>receipt_date),key=lambda r:r['date'])
 result={'receipt_date':receipt_date,'entry_date':None,'entry_open':None,'status':'no_future_bars','horizons':{}}
 entry=future[0] if future else None
 if entry:result.update(entry_date=entry['date'],entry_open=entry['open'],status='available' if entry['open']>0 and entry['volume']>0 else 'nontradable_entry')
 for n in horizons:
  target=future[n-1] if len(future)>=n else None;value=None
  if not entry:status='no_future_bars'
  elif result['status']=='nontradable_entry':status='nontradable_entry'
  elif target is None:status='insufficient_future_bars'
  elif target['close']<=0 or target['volume']<=0:status='nontradable_exit'
  else:status='available';value=100*(target['close']/entry['open']-1)
  result['horizons'][str(n)]={'exit_date':target['date'] if target else None,'exit_close':target['close'] if target else None,'return_pct':value,'status':status}
 return result

def csv_write(path,rows):
 if not rows:return
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def canonical_name(name):return re.sub(r'[^A-Za-z0-9가-힣]','',name.replace('주식회사','').replace('(주)','')).casefold()

def collect(start,end,refresh=False):
 paths=get_paths();start=dt.date.fromisoformat(start).isoformat();end=dt.date.fromisoformat(end).isoformat()
 if end<start:raise ValueError('end precedes start')
 if end>=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat():raise ValueError('use completed prior-day bars only')
 source=paths.graph/'stage2_twenty';out=paths.data/'market/naver_daily'/(start.replace('-','')+'_'+end.replace('-',''));raw=out/'raw';raw.mkdir(parents=True,exist_ok=True)
 companies=[]
 with (source/'nodes.csv').open(encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):
   if row['entity_type']=='Company':companies.append({'company_id':row['entity_id'],'company_name':row['name'],**json.loads(row['attributes_json'])})
 context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)
 snapshots=[];prices=[];failures=[]
 for company in companies:
  code=company['stock_code']
  if not re.fullmatch(r'\d{6}',code):raise ValueError('invalid stock code')
  url='https://fchart.stock.naver.com/sise.nhn?timeframe=day&count=6000&requestType=0&symbol='+code
  file=raw/(code+'.xml');meta_file=raw/(code+'.metadata.json')
  try:
   if refresh or not file.exists() or not meta_file.exists():
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),context=context,timeout=45) as response:body=response.read()
    # Validate before promoting cached bytes.
    parse_chart(body,code,start,end)
    file.write_bytes(body);meta_file.write_text(json.dumps({'source_url':url,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2));time.sleep(.3)
   body=file.read_bytes();chart,bars=parse_chart(body,code,start,end);meta=json.loads(meta_file.read_text());name_ok=canonical_name(chart.get('name',''))==canonical_name(company['company_name'])
   snapshot={**company,'provider_name':chart.get('name'),'mapping_status':'name_match' if name_ok else 'name_mismatch_review','rows':len(bars),'first_date':bars[0]['date'] if bars else None,'last_date':bars[-1]['date'] if bars else None,'source_url':url,'retrieved_at':meta['retrieved_at'],'raw_sha256':hashlib.sha256(body).hexdigest(),'adjustment_status':'provider_adjustment_unverified','bars':bars}
   snapshots.append(snapshot)
   for bar in bars:prices.append({'stock_code':code,'provider_name':chart.get('name'),**bar})
   print(code,chart.get('name'),len(bars),snapshot['mapping_status'],flush=True)
  except Exception as error:failures.append({'stock_code':code,'error_type':type(error).__name__,'message':str(error)[:250]})
 identity=hashlib.sha256(json.dumps([{'stock_code':s['stock_code'],'raw_sha256':s['raw_sha256']} for s in snapshots],sort_keys=True).encode()).hexdigest()[:16]
 manifest={'source':SOURCE,'start':start,'end':end,'dataset_id':'naver_daily:'+start+':'+end+':'+identity,'companies_requested':len(companies),'companies_received':len(snapshots),'prices':len(prices),'failures':failures,'adjustment_status':'provider_adjustment_unverified','interpretation':'Exploratory event alignment; not predictions, not a point-in-time backtest','snapshots':snapshots}
 (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));csv_write(out/'prices.csv',prices)
 records=json.loads((source/'extracted.json').read_text());lookup={s['corp_code']:s for s in snapshots};events=[]
 for record in records:
  filing=record['filing'];snapshot=lookup.get(filing['corp_code'])
  if not snapshot or snapshot['mapping_status']!='name_match':continue
  received=dt.datetime.strptime(filing['rcept_dt'],'%Y%m%d').date().isoformat();event=event_returns(received,snapshot['bars'])
  for n,result in event['horizons'].items():events.append({'receipt_no':filing['rcept_no'],'company':filing['corp_name'],'stock_code':snapshot['stock_code'],'receipt_date':received,'is_correction':'정정' in filing['report_nm'],'entry_date':event['entry_date'],'entry_open':event['entry_open'],'horizon_bars':int(n),**result,'adjustment_status':manifest['adjustment_status'],'dataset_id':manifest['dataset_id']})
 csv_write(out/'event_returns.csv',events)
 print('DATASET',out,'prices',len(prices),'event_rows',len(events),'failures',len(failures))
 if failures:raise RuntimeError('Some price downloads failed; inspect the local manifest before importing')
 return out

if __name__=='__main__':
 p=argparse.ArgumentParser(description='Collect bounded daily prices for the existing KG companies')
 p.add_argument('--start',default='2026-09-01');p.add_argument('--end',default='2026-11-05');p.add_argument('--refresh',action='store_true');args=p.parse_args();collect(args.start,args.end,args.refresh)
