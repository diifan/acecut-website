"""Reviewed answer types, independent of the tracer workflow registry.

Each topic is a single search intent, not one page per wording or per source URL.
An evidence pattern must match independently fetched body text before rendering.
"""
import re

RULES='https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf'
TOPICS={
 'court_dimensions':dict(kind='court_reference',title='Tennis court dimensions: singles and doubles',
  query=r'\b(court|courts)\b.*\b(dimensions?|measurements?|width|length|size|diagram|layout)\b|\b(dimensions?|width|length|size)\b.*\b(court|courts)\b',
  evidence=r'23\.77|78\s*(?:feet|ft)',
  answer='A full-size tennis court is 78 feet (23.77 metres) long. Singles uses a width of 27 feet (8.23 metres); doubles uses 36 feet (10.97 metres). The doubles alleys change the playing width, not the court length.',
  sections=[('Playing lines versus surrounding space','These dimensions describe the marked playing court. They do not specify the total land, fencing or run-off space needed for a facility. Keep facility planning separate from measuring the playing lines.'),('Use the right boundary','For a singles recording, identify the inner sidelines before judging a rally. For doubles, use the outer sidelines. A perspective-distorted video is not a reliable measurement of court dimensions.')],
  checklist=['Identify whether the session is singles or doubles.','Mark which sidelines the players are using.','Keep surrounding run-off space separate from the marked court.'],authority=RULES),
 'net_height':dict(kind='court_reference',title='Tennis net height at the centre and posts',
  query=r'\bnet\b.*\b(height|high|tall)\b|\b(height|high|tall)\b.*\bnet\b',
  evidence=r'0\.914|3 feet|three feet|36 inches',
  answer='A regulation tennis net is 3 feet (0.914 metres) high at the centre and 3½ feet (1.07 metres) at the posts. The centre strap holds the middle of the net at its specified height.',
  sections=[('Measure the centre separately','Checking a post does not establish the height at the centre. Measure at the centre strap and then check the support arrangement specified for the court.'),('What a recording cannot establish','Camera height and perspective change the apparent clearance over the net. Use a physical measurement for setup; use video to review visible play, not to certify net height.')],
  checklist=['Locate the centre strap.','Measure the centre height directly.','Check the applicable singles or doubles support arrangement.'],authority=RULES),
 'scoring_basics':dict(kind='rules_explainer',title='How tennis scoring works: points, games and sets',
  query=r'^(?:how (?:does|do) (?:the )?tennis scoring(?: system)? work|tennis scoring(?: explained| system| rules)?|how (?:is tennis scored|to (?:score|keep score in) tennis))\??$',
  evidence=r'15.{0,80}30.{0,80}40',
  answer='In a standard advantage game, point scores progress through love, 15, 30 and 40. At 40–40 the score is deuce. A player must then win two consecutive points to take the game: advantage, followed by game. Losing the advantage point returns the game to deuce.',
  sections=[('Keep three levels separate','Points make up a game; games make up a set; sets make up a match. Write each level separately when taking notes so a point score cannot be mistaken for a game count.'),('Confirm the format before starting','No-ad games, tie-break sets and match tie-breaks have different procedures. Check the event format before play; this explanation covers standard advantage games rather than every competition format.')],
  checklist=['Write down the agreed match format.','Call the server’s score first.','Record the game count separately from the point score.'],authority=RULES),
 'continental_grip':dict(kind='technique_guide',title='Continental tennis grip: identify and check your hand position',
  query=r'\bcontinental grip\b|\bgrip continental\b',evidence=r'bevel',
  answer='A continental grip is a specific hand position on the racket handle, not a grip size or an overgrip product. Use the handle bevels and the position of your index-finger base knuckle as reference points when checking it against the illustrated source.',
  sections=[('Compare the same hand and handle view','Right-handed and left-handed diagrams must be interpreted for the hand holding the racket. Match the orientation before copying a reference; a mirrored photo can make the position confusing.'),('Separate identification from shot selection','Identifying a grip does not establish that it is the right choice for every stroke. Consult the source’s stroke-specific explanation and, for technique corrections, a qualified coach. A ball-trail effect cannot identify your hand position.')],
  checklist=['Identify which hand the source diagram shows.','Take a close view of the handle and base knuckle.','Compare hand position before reviewing a full-speed stroke.']),
 'beat_pusher':dict(kind='tactics_guide',title='Playing a tennis pusher: build a point-review plan',
  query=r'how to beat (?:a )?pusher(?: in tennis)?',evidence=r'pusher',
  answer='Start by separating the opponent’s style from your own errors. Review whether points ended through your missed attacking shot, a short ball you did not use, or a passing shot after your approach. Choose a tactical experiment based on that pattern rather than trying to hit every ball harder.',
  sections=[('Make a small point log','For several points, record the first short ball, your next decision and how the point ended. These are observations from your match, not a promise that one tactic defeats every defensive opponent.'),('Test one decision at a time','Choose one pattern to discuss with your coach, then compare a few points where you used it with points where you did not. Keep the opponent’s court position in view; a close crop of your racket alone loses the tactical context.')],
  checklist=['Log the point-ending error or winner.','Mark whether a short ball appeared before the point ended.','Choose one tactical decision to compare in the next session.']),
}

def topic(word):
    text=' '.join(word.casefold().split())
    if re.search(r'\b(cost|build|construction|pickleball|badminton|mini|kids|padel|squash)\b',text):return None
    return next((key for key,value in TOPICS.items() if re.search(value['query'],text)),None)

def supported(word,data):
    key=topic(word)
    if not key:return None
    body=data.get('text','')
    if data.get('http')==200 and len(body)>=300 and 'tennis' in body.casefold() and re.search(TOPICS[key]['evidence'],body,re.I):return key
    return None
