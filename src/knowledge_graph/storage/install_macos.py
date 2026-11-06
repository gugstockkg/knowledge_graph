"""Download official, checksum-verified local runtimes without global installs."""
from pathlib import Path
import urllib.request,ssl,json,hashlib,concurrent.futures,subprocess,platform
if platform.system()!='Darwin' or platform.machine()!='arm64':
 raise SystemExit('install-macos supports Apple Silicon only; use the EC2 runbook on Linux.')
from ..config import get_paths
ROOT=get_paths().root;RT=get_paths().runtime;DL=RT/'downloads'
CTX=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
def getjson(url):return json.load(urllib.request.urlopen(url,context=CTX))
java=getjson('https://api.azul.com/metadata/v1/zulu/packages/f2caf8b1-ed9c-4405-9145-06f58c4fc129')
neo='https://dist.neo4j.org/neo4j-community-2026.10.1-unix.tar.gz'
neo_sha=urllib.request.urlopen(neo+'.sha256',context=CTX).read().decode().strip().split()[0]
items=[{'name':'neo4j','url':neo,'sha256':neo_sha},{'name':'java','url':java['download_url'],'sha256':java['sha256_hash']}]
DL.mkdir(parents=True,exist_ok=True)
def download(item):
 path=DL/item['url'].split('/')[-1]
 if not path.exists():
  temp=path.with_suffix(path.suffix+'.part')
  with urllib.request.urlopen(item['url'],context=CTX,timeout=120) as src,temp.open('wb') as dst:
   while True:
    chunk=src.read(1024*1024)
    if not chunk:break
    dst.write(chunk)
  temp.rename(path)
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 if h.hexdigest()!=item['sha256']:raise RuntimeError('checksum mismatch '+str(path))
 item['file']=str(path);item['bytes']=path.stat().st_size;print(item['name'],'checksum verified',item['bytes'],flush=True)
 return item
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:items=list(pool.map(download,items))
for item in items:
 marker=RT/('.'+item['name']+'-extracted')
 if not marker.exists():subprocess.run(['tar','-xzf',item['file'],'-C',str(RT)],check=True);marker.touch()
neohome=RT/'neo4j-community-2026.10.1';javahome=next(RT.glob('zulu*/Contents/Home'))
for link,target in [(RT/'neo4j-community',neohome),(RT/'java21',javahome)]:
 if not link.exists():link.symlink_to(target, target_is_directory=True)
(RT/'install_manifest.json').write_text(json.dumps({'neo4j_version':'2026.10.1','java_version':java['java_version'],'sources':items},indent=2))
subprocess.run([str(RT/'java21/bin/java'),'-version'],check=True)
print('RUNTIMES_READY',flush=True)
