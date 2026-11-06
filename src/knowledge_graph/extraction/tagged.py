"""Read whitelisted DART field locations without loading text into an LLM."""
from html.parser import HTMLParser
import collections

def norm(s):return " ".join(s.split())

class FieldParser(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.stack=[];self.count=collections.Counter();self.fields=[];self.active=None
 def handle_starttag(self,tag,attrs):
  a=dict(attrs);self.count[tag]+=1;entry={'tag':tag,'attrs':a,'index':self.count[tag],'line':self.getpos()[0],'data':[]};self.stack.append(entry)
  if tag in ('te','tu') and (a.get('acode') or a.get('aunit')):
   self.active=entry;entry['key']=a.get('acode') or a.get('aunit');entry['path']='/'.join(x['tag']+'['+str(x['index'])+']' for x in self.stack)
   entry['table']=next((x['index'] for x in reversed(self.stack) if x['tag']=='table'),None)
   entry['row']=next((x['index'] for x in reversed(self.stack) if x['tag']=='tr'),None)
 def handle_startendtag(self,t,a):self.handle_starttag(t,a);self.handle_endtag(t)
 def handle_data(self,s):
  if self.active:self.active['data'].append(s)
 def handle_endtag(self,tag):
  if self.active and self.active['tag']==tag:
   e=self.active;self.fields.append({'key':e['key'],'text':norm(''.join(e['data'])),'unit_value':e['attrs'].get('aunitvalue'),'line':e['line'],'path':e['path'],'table':e['table'],'row':e['row']});self.active=None
  for i in range(len(self.stack)-1,-1,-1):
   if self.stack[i]['tag']==tag:self.stack=self.stack[:i];break

