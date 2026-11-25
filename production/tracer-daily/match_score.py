"""Read the matched public scoreboard DOM; never split flattened numeric text."""
import json,re
from html.parser import HTMLParser
from urllib.parse import urlsplit
class Node:
 def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[];self.parts=[]
 def walk(self):
  yield self
  for child in self.children:yield from child.walk()
 def text(self):return ''.join(self.parts).strip()
class Tree(HTMLParser):
 def __init__(self):super().__init__();self.root=Node();self.stack=[self.root]
 def handle_starttag(self,tag,attrs):
  n=Node(tag,attrs);self.stack[-1].children.append(n)
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(n)
 def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==tag:self.stack=self.stack[:i];break
 def handle_data(self,data):
  for n in self.stack:n.parts.append(data)
def has(n,component,suffix):return any(c.startswith(component+'-module') and c.endswith('__'+suffix) for c in n.attrs.get('class','').split())
def extract_score(body,url):
 if urlsplit(url).hostname not in ('www.tennis.com','tennis.com') or '/matches/' not in urlsplit(url).path:return None
 tree=Tree();tree.feed(body);nodes=list(tree.root.walk());events=[]
 for n in nodes:
  if n.tag=='script' and n.attrs.get('type')=='application/ld+json':
   try:d=json.loads(n.text())
   except (ValueError,TypeError):continue
   if isinstance(d,dict) and d.get('@type')=='SportsEvent' and d.get('url','').rstrip('/')==url.rstrip('/'):events.append(d)
 if len(events)!=1:return None
 event=events[0]
 if event.get('eventStatus')!='https://schema.org/EventCompleted':return None
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',event.get('startDate','')):return None
 names=[event.get(side,{}).get('name','') for side in ('homeTeam','awayTeam')]
 if not all(names) or names[0]==names[1]:return None
 cards=[n for n in nodes if n.tag=='article' and has(n,'Match','card') and any(x.tag=='a' and urlsplit(x.attrs.get('href','')).path==urlsplit(url).path for x in n.walk())]
 if len(cards)!=1:return None
 rows=[n for n in cards[0].walk() if has(n,'Match','competitorRow')]
 if len(rows)!=2:return None
 scores=[]
 for row in rows:
  labels=[n.text() for n in row.walk() if has(n,'PlayerRow','name')]
  cells=[n for n in row.walk() if has(n,'SetScore','cell')];sets=[]
  if len(labels)!=1 or not 2<=len(cells)<=5:return None
  for cell in cells:
   games=[n.text() for n in cell.walk() if has(n,'SetScore','games')];ties=[n.text() for n in cell.walk() if has(n,'SetScore','tiebreak')]
   if len(games)!=1 or not re.fullmatch(r'\d{1,2}',games[0]) or len(ties)>1 or any(not re.fullmatch(r'\d{1,3}',t) for t in ties):return None
   sets.append({'games':int(games[0]),'tiebreak':int(ties[0]) if ties else None})
  scores.append({'label':labels[0],'sets':sets})
 if len(scores[0]['sets'])!=len(scores[1]['sets']):return None
 # Finished conventional sets; incomplete/retired/unsupported match-tiebreaks stay pending.
 for a,b in zip(scores[0]['sets'],scores[1]['sets']):
  hi,lo=sorted((a['games'],b['games']),reverse=True)
  if not ((hi==6 and lo<=4) or (hi==7 and lo in (5,6)) or (hi>7 and hi-lo==2)):return None
  if any(v['tiebreak'] is not None for v in (a,b)) and (hi,lo)!=(7,6):return None
 return {'players':names,'start_date':event['startDate'],'event_name':event.get('superEvent',{}).get('name',''),'rows':scores,'source_url':url}
