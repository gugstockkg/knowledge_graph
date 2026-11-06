"""Portable paths and explicit credentials; no shell-history fallback."""
from pathlib import Path
from types import SimpleNamespace
import os

def get_paths():
 root=Path(__file__).resolve().parents[2]
 def path(key,default):return Path(os.environ.get(key) or default).expanduser().resolve()
 data=path('KG_DATA_DIR',root/'data');artifacts=path('KG_ARTIFACT_DIR',root/'artifacts')
 runtime=path('KG_RUNTIME_DIR',root/'.runtime');secrets=path('KG_SECRETS_DIR',root/'.secrets')
 collection_id=os.environ.get('KG_COLLECTION_ID','20261001_20261105')
 version=os.environ.get('KG_ONTOLOGY_VERSION','v0.1')
 if '/' in collection_id or '..' in collection_id:raise ValueError('Invalid collection ID')
 if version!='v0.1':raise ValueError('Pilot currently requires KG_ONTOLOGY_VERSION=v0.1')
 return SimpleNamespace(root=root,data=data,artifacts=artifacts,runtime=runtime,secrets=secrets,collection=data/'raw/opendart/collections'/collection_id,raw=data/'raw/opendart',graph=data/'graph/ownership_pilot_v01',schema=root/'ontology/v0.1',ontology=root/'ontology/v0.1',imports=data/'graph/ownership_pilot_v01/import',database=data/'neo4j',backups=data/'backups',queries=root/'queries')

def require_api_key():
 key=os.environ.get('OPENDART_API_KEY','').strip()
 if not key:raise ValueError('OPENDART_API_KEY 환경변수를 설정하세요. 키 값은 로그에 기록하지 않습니다.')
 return key
