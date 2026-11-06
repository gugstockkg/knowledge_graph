"""Enable this repository's pre-commit guard; never change global Git config."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
current=subprocess.run(['git','config','--local','--get','core.hooksPath'],cwd=root,capture_output=True,text=True).stdout.strip()
if current and current!='.githooks':raise SystemExit('Existing hooksPath preserved; integrate the safety check manually.')
(root/'.githooks/pre-commit').chmod(0o755)
subprocess.run(['git','config','--local','core.hooksPath','.githooks'],cwd=root,check=True)
print('Repository-local pre-commit safety guard enabled.')
