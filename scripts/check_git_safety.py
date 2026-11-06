"""Inspect Git candidates without staging them or printing sensitive values."""
from pathlib import Path
import subprocess,json,re,sys,os
ROOT=Path(__file__).resolve().parents[1]
def git(*args,**kwargs):return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,check=False,**kwargs)
def main():
 candidates=set(p.decode() for p in git('ls-files','--cached','--others','--exclude-standard','-z').stdout.split(b'\0') if p)
 issues=[]
 forbidden=['data/','artifacts/','.runtime/','.secrets/']
 patterns=[('literal_api_key',re.compile(rb'(?i)(?:OPENDART_API_KEY|crtfc_key|api_key)\s*[=:]\s*[\x22\x27]?([a-f0-9]{40})(?![a-f0-9])')),('private_key',re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),('provider_token',re.compile(rb'(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]{20,}'))]
 known=[]
 for key in ['OPENDART_API_KEY','NEO4J_PASSWORD']:
  value=os.environ.get(key)
  if value:known.append(value.encode())
 auth=ROOT/'.secrets/neo4j-auth.json'
 if auth.exists():known.append(json.loads(auth.read_text())['password'].encode())
 def scan(relative,body,scope):
  if len(body)>5*1024*1024:issues.append({'path':relative,'rule':scope+'unexpected_large_file'});return
  for label,pattern in patterns:
   if pattern.search(body):issues.append({'path':relative,'rule':scope+label})
  if any(value in body for value in known):issues.append({'path':relative,'rule':scope+'known_local_secret'})
 for relative in sorted(candidates):
  p=ROOT/relative
  if relative.startswith(tuple(forbidden)) or (p.name.startswith('.env') and p.name!='.env.example'):issues.append({'path':relative,'rule':'forbidden_path'});continue
  if not p.is_file():continue
  size=p.stat().st_size
  if size>5*1024*1024:issues.append({'path':relative,'rule':'unexpected_large_file'});continue
  body=p.read_bytes()
  scan(relative,body,'working_')
 # Index blobs can differ from the working tree, including files deleted locally.
 for entry in git('ls-files','--stage','-z').stdout.split(b'\0'):
  if not entry:continue
  meta,path=entry.split(b'\t',1);mode,blob,stage=meta.split();relative=path.decode()
  if relative.startswith(tuple(forbidden)) or (Path(relative).name.startswith('.env') and Path(relative).name!='.env.example'):
   issues.append({'path':relative,'rule':'staged_forbidden_path'})
  if stage!=b'0':issues.append({'path':relative,'rule':'unmerged_index_entry'})
  scan(relative,git('cat-file','blob',blob.decode()).stdout,'staged_')
 checks={}
 for relative in ['data/raw/probe.xml','data/neo4j/probe','artifacts/results.csv','.runtime/probe','.secrets/neo4j-auth.json','.env.local']:
  checks[relative]=git('check-ignore','--no-index','-q',relative).returncode==0
  if not checks[relative]:issues.append({'path':relative,'rule':'missing_ignore_rule'})
 for relative in ['.env.example','ontology/v0.1/02_concept_definitions.csv','ontology/drafts/v0.2/GUG_ontology_v0.2_team_review.xlsx','src/knowledge_graph/config.py','docs/diagrams/overview.drawio']:
  if git('check-ignore','--no-index','-q',relative).returncode==0:issues.append({'path':relative,'rule':'source_unexpectedly_ignored'})
 result={'candidate_files':len(candidates),'ignore_checks':checks,'issues':issues,'clean':not issues,'note':'This is a bounded local guard, not a guarantee that every possible secret can be detected.'}
 print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if issues else 0
if __name__=='__main__':raise SystemExit(main())
