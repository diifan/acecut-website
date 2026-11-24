"""Tennis-only source-aligned review workflows. Input must pass Semrush/evidence gates."""
import html,hashlib,json,re,urllib.parse
from common import *
from source_cache import classify
from editorial_topics import TOPICS
E=html.escape
WORKFLOWS={
 'drop_shot':('Review a drop-shot sequence',['Keep the approach, racket contact and first bounce in one continuous shot.','Use court lines to describe the visible landing area; do not infer distance from a screen-space trail.','Keep the opponent in frame when comparing their starting position and response.','Review the plain replay before adding a short trail; stop the overlay when the ball becomes hidden.']),
 'lob':('Review a lob sequence',['Frame the ball high enough to keep its visible flight and landing in the recording.','Keep the opposing net player in view when possible to understand the shot context.','If the ball leaves the frame, split the trail at that point instead of inventing the missing arc.','Compare the original and edited clip; the effect does not measure height, depth or whether a ball was in.']),
 'overhead':('Review an overhead sequence',['Start before the player moves under the incoming ball.','Keep the preparation, contact and landing visible in the original recording.','Note whether the camera actually shows contact; do not reconstruct contact hidden behind the racket or player.','Inspect the outgoing ball trail separately from the player movement; the overlay does not evaluate technique.']),
 'serve':('Review the serve sequence',['Start the clip before the toss so preparation remains visible.','Mark the racket-contact frame only if the ball is visible. Leave an obscured contact unmarked.','Keep the ball flight and the next visible bounce in the same continuous shot.','Compare a plain replay with a short ball trail; discard the overlay if it drifts away from the ball.']),
 'forehand':('Review a forehand clip',['Keep preparation, contact and recovery in one clip.','Use the visible ball as the reference when checking a trail, rather than guessing its path behind the player.','Separate cross-court and down-the-line examples in your notes only when the camera view makes the direction clear.','Compare the same moment with and without the overlay at normal playback speed.']),
 'backhand':('Review a backhand clip',['Include the approach to the ball and recovery after contact.','Mark whether the contact frame is visible before making a technique note.','Check the overlay near the player: a racket or body can hide the ball.','Keep one camera angle per tracer segment so a replay cut cannot join unrelated positions.']),
 'volley':('Review a net-play clip',['Choose a continuous view of the approach and volley.','Mark any moment where the net player blocks the ball.','Use a short, unobstructed segment rather than asking a trail to bridge a hidden contact.','Check whether the effect improves the actual visible shot before exporting.']),
 'rally':('Review one continuous rally',['Choose a single uninterrupted point.','Mark the visible start and end of the ball flight you want to show.','Split the clip at camera cuts or replays.','Watch the finished segment at normal speed and remove any trail that jumps away from the ball.']),
 'spin':('Review a spin-related clip',['Choose footage where the ball remains visible around contact and flight.','Record the shot you intended in your own notes; a screen-space trail does not measure spin rate.','Compare the plain video and overlaid video side by side.','Do not use the trail as a physical trajectory measurement or proof of a line call.']),
 'footwork':('Review movement alongside the ball',['Keep the player’s feet and the relevant court area inside the original frame.','Mark preparation, contact and recovery in separate notes.','Review the unedited clip first: a ball trail is not a body-pose or footwork measurement.','Use the overlay only where it makes the ball easier to follow without hiding the player.']),
 'practice':('Build a reviewable practice clip',['Record a short test before starting a practice set.','Choose one drill repetition and state what you want to observe.','Keep the camera fixed and note when the ball is blurred or hidden.','Compare the same repetition before and after applying a trail; retain the plain version when it is clearer.']),
 'recording':('Prepare source footage for a ball trail',['Keep the court and the ball in frame with a stable camera position.','Inspect a short test recording for blur, glare and obstructions.','Choose one continuous segment of up to 30 seconds for the online Tracer.','Check the detected trail at normal playback speed before exporting or sharing.'])}

def slug(row):return re.sub('[^a-z0-9]+','-',row['keyword'].lower()).strip('-')[:110].rstrip('-')
def excerpt(row,evidence):
 from evidence_text import context_excerpt
 return context_excerpt(row['keyword'],evidence['text'])

def shell(title,description,path,body):
 original=(WORK/'public/tennis-ball-tracer.html').read_text();header=re.search(r'<header>.*?</header>',original,re.S)[0].replace('src="assets/','src="/assets/');footer=re.search(r'<footer\b.*?</footer>',original,re.S)[0].replace('src="assets/','src="/assets/')
 fonts=re.search(r'<link href="https://fonts.googleapis.com/css2[^>]*>',original)
 font_link=fonts[0] if fonts else ''
 return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)} | AceCut</title><meta name="description" content="{E(description,quote=True)}"><link rel="canonical" href="{ORIGIN}{path}"><meta name="robots" content="index,follow">{font_link}<link rel="stylesheet" href="/style.css?v=20261022-mobile2"><link rel="stylesheet" href="/guides.css"><link rel="stylesheet" href="/tracer-guides.css"><script defer src="/tracer-guides.js"></script></head><body>{header}<main class="guide-article">{body}</main>{footer}</body></html>'

def render(row,related):
 evidence=read(Path(row['evidence_path']));family,error=classify(row,evidence)
 if not family:raise ValueError('Source relevance failed: '+str(error))
 if family.startswith('editorial:'):return render_editorial(row,evidence,TOPICS[family.split(':',1)[1]],related)
 quote=excerpt(row,evidence);heading,steps=WORKFLOWS[family];path='/tennis-tracer/'+slug(row);host=urllib.parse.urlsplit(row['evidence_url']).hostname
 body=f'<nav><a href="/tennis-ball-tracer">Tennis ball tracer</a> / <a href="/tennis-tracer">Review guides</a></nav><h1>{E(row["keyword"])}</h1><p class="guide-intro">A source-led tennis video review workflow for {E(row["keyword"])}.</p><section><h2>Start with the tennis context</h2><p>Read the <a href="{E(row["evidence_url"],quote=True)}">topic reference from {E(host)}</a> alongside your own recording. The source was checked on {E(evidence["checked_at"][:10])}. This short excerpt identifies the context for the review:</p><blockquote>{E(quote)}…</blockquote><p>The workflow below focuses on what you can observe in footage you own or have permission to edit. It does not claim that AceCut has analysed the source page or any player mentioned there.</p></section><section><h2>{heading}</h2><ol>'+''.join('<li>'+E(x)+'</li>' for x in steps)+'</ol></section>'
 body+=f'''<section class="clip-plan" data-key="{E(slug(row))}"><h2>Make your clip plan</h2><p>Use this worksheet to state what you will look for before uploading a segment. It stays in your browser; it does not upload footage.</p><form id="clip-plan"><label>What do you want to observe?<textarea id="observation" required maxlength="500" placeholder="Describe one visible moment you want to review."></textarea></label><label>Start time (mm:ss)<input id="start" required pattern="[0-9]+:[0-5][0-9]" value="0:00"></label><label>Segment length in seconds<input id="duration" type="number" min="1" max="30" value="10" required></label><label><input id="visible" type="checkbox"> The ball is visible throughout this segment</label><label><input id="continuous" type="checkbox"> This segment uses one continuous camera angle</label><button type="submit">Save clip plan</button><button type="button" id="download-plan">Download plan</button><p id="plan-status" role="status"></p></form></section><section><h2>Apply a trail, then check it</h2><p>Upload your own video to <a href="/try-tracer">AceCut’s online tennis Tracer</a> and choose a segment of up to 30 seconds. Select one of the 25 available visual styles. Processing may take several minutes; blurred, hidden or very small balls can produce missed or inaccurate detections.</p><p>Play the result at normal speed. The trail should follow visible ball points. If it jumps, bridges a camera cut or obscures the shot, shorten the segment or keep the plain clip. A trail is an editing effect, not a measured spin rate, ball speed or official line call.</p><p><a href="/try-tracer">Try the existing tennis Tracer</a> · <a href="/how-to-record-tennis-matches">Record clearer source footage</a> · <a href="/privacy">Upload privacy</a></p></section><section><h2>Related review workflows</h2><ul>'''
 body+=''.join(f'<li><a href="/tennis-tracer/{slug(r)}">{E(r["keyword"])}</a></li>' for r in related)+'</ul></section>'
 return shell(row['keyword']+' — tennis video review',f'Explore {row["keyword"]} with a cited tennis source, a clip-planning worksheet and the existing AceCut ball-tracer workflow.',path,body)

def hubs(rows):
 for i in range(0,len(rows),100):
  n=i//100;path='/tennis-tracer' if n==0 else f'/tennis-tracer/guides-{n+1}'
  body='<nav><a href="/tennis-ball-tracer">Tennis ball tracer</a></nav><h1>Tennis video review guides'+('' if n==0 else f' — page {n+1}')+'</h1><p>Source-led workflows for planning and reviewing your own tennis footage with AceCut.</p><ul>'
  body+=''.join(f'<li><a href="/tennis-tracer/{slug(r)}">{E(r["keyword"])}</a></li>' for r in rows[i:i+100])+'</ul><nav>'
  body+=' '.join('<a href="'+('/tennis-tracer' if j==0 else f'/tennis-tracer/guides-{j+1}')+f'">{j+1}</a>' for j in range((len(rows)+99)//100))+'</nav>'
  p=WORK/'public'/(path[1:]+'.html');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(shell('Tennis video review guides'+('' if n==0 else f' — page {n+1}'),f'Source-led tennis Tracer review workflows, page {n+1}.',path,body))


def render_editorial(row,evidence,spec,related):
 path='/tennis-tracer/'+slug(row)
 body='<nav><a href="/tennis-tracer">Tennis guides</a></nav><article data-page-type="'+E(spec['kind'])+'"><h1>'+E(spec['title'])+'</h1><p class="guide-intro">'+E(spec['answer'])+'</p>'
 for heading,paragraph in spec['sections']:body+='<section><h2>'+E(heading)+'</h2><p>'+E(paragraph)+'</p></section>'
 body+='<section><h2>Use this checklist</h2><ul>'+''.join('<li>'+E(x)+'</li>' for x in spec['checklist'])+'</ul></section>'
 body+='<section><h2>Sources and scope</h2><p><a href="'+E(row['evidence_url'],quote=True)+'">Read the topic reference</a>, checked '+E(evidence['checked_at'][:10])+'.</p>'
 if spec.get('authority'):body+='<p><a href="'+spec['authority']+'">2026 ITF Rules of Tennis</a>. Confirm the format used by your event.</p>'
 body+='</section><section><h2>Keep useful moments from your own session</h2><p>If you record your session, retain the original clip and use clear notes to identify what happened. <a href="/try-tracer">AceCut’s optional ball-trail tool</a> is for editing visible ball flight; it does not verify rules, court dimensions or technique.</p></section></article>'
 return shell(spec['title'],spec['answer'][:155],path,body)
