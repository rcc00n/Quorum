#!/usr/bin/env python3
"""Create private presentation/docs from verified local evidence. Never submits or publishes."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import tarfile
import textwrap

EVENT='https://hackathon.genai.works/event/open-agent-hackathon-2026'
REPO='https://github.com/rcc00n/Quorum'
SLIDES=[
 ('01 / PROBLEM','Reporting is abundant. Evidence is harder to inspect.',
  ['For readers and researchers: separate reported claims, editorial position and actual checks.',
   'Repeated wire coverage is not independent confirmation.',
   'Uncertainty belongs next to the result, not hidden in a footnote.']),
 ('02 / SOLUTION','Quorum keeps reporting and verification inspectable.',
  ['A daily roundup preserves source links and producer-attributed status.',
   'Four external rating modes describe editorial position, not factual accuracy.',
   'Recorded checks, partial failures and provenance limits remain visible.']),
 ('03 / ARCHITECTURE','An agent graph behind a bounded web product.',
  ['Collection / intended sponsor data route: collectors → PostgreSQL → Zetaris.',
   'Reasoning: LangGraph research/verification loops → immutable snapshot.',
   'Verified local path: original v3 + source registry → Django API → Next.js.',
   'Production bridge, actual sponsor workflow and owner adoption remain gated.']),
 ('04 / GENUINE DEMO','28 roundup events. Zero featured stories.',
  ['Original provisional v3, displayed through authenticated local HTTP.',
   'Source attribution → event-scoped timeline → four rating modes.',
   'Partial / provisional / unpublished throughout. No manufactured article.']),
 ('05 / TECHNOLOGIES','Sponsor use: evidence and open gates.',
  ['Next.js / TypeScript + Django: authenticated local presentation verified.',
   'Zetaris: code/contract and producer declarations; operational proof remains blocked.',
   'NVIDIA: recorded model declarations; full execution attestation still blocked.',
   'Meterless: reference conformance 13/13; hooks provisional; Nightshift probes alone are insufficient.',
   'Proposed distinction: source-grounded recall with exact DocRefs and fresh checks.']),
 ('06 / VERIFICATION','Tested locally. Not certified for production.',
  ['222 candidate reasoning / 70 Django / 12 deployment / 8 tooling tests pass.',
   'Genuine browser path and 40-source / four-mode binding verified.',
   'Config digest mismatch blocks full original execution acceptance.',
   'Owner reviews, sponsor proof, secure bridge and release approval remain open.']),
 ('07 / NEXT','A useful product with an honest critical path.',
  ['Yelysei: execution/config evidence; privacy and memory review.',
   'Anastasia: exact DocRefs, corpus manifest and operational data evidence.',
   'Vadim: final voice/edit, workspace checks and submission packaging.',
   'Then: approved ordered integration, genuine sponsor proof and secure release.',
   'Future: richer evidence chains, correction history and changes in framing over time.']),
]


def contains_secret(data):
    # DECISION(2026-10-25, rcc00n/Codex): detect complete PEM headers, not security-checker regex source.
    # Why: existing validators contain marker words; those are not private key material.
    begin=b'-----BEGIN '
    label=b'PRIVATE KEY-----'
    pem=re.escape(begin)+rb'(?:RSA |EC |DSA |OPENSSH )?'+re.escape(label)
    return bool(re.search(pem,data) or re.search(rb'(?:gh[pousr]_|nvapi-)[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_.-]{20,}',data))


def write(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

def wrap_draw(c,text,x,y,width,font='QS',size=18,color='#253b38'):
    c.setFont(font,size);c.setFillColor(color)
    words=text.split();line=''
    for word in words:
        if pdfmetrics.stringWidth((line+' '+word).strip(),font,size)>width:
            c.drawString(x,y,line);y-=size*1.35;line=word
        else:line=(line+' '+word).strip()
    if line:c.drawString(x,y,line);y-=size*1.35
    return y


def make_deck(root,scenes):
    global pdfmetrics
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('QS','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('QB','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('QT','/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'))
    path=root/'slides/quorum-presentation.pdf';path.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(path),pagesize=(960,540));c.setTitle('Quorum — evidence, reporting and verification');c.setAuthor('Quorum team')
    notes='# Quorum presentation — speaker notes\n\nPrivate submission draft. No production, sponsor-completion or full-provenance claim.\n\n'
    htmlslides=[]
    for index,(tag,title,points) in enumerate(SLIDES):
        c.setFillColor('#f5f3ed');c.rect(0,0,960,540,fill=1,stroke=0)
        c.setFillColor('#137b70');c.rect(0,0,12,540,fill=1,stroke=0)
        c.setFont('QB',14);c.drawString(46,501,'quorum.');c.setFont('QS',10);c.drawRightString(914,501,tag)
        wrap_draw(c,title,46,445,870,'QT',30)
        if index==3:
            c.drawImage(str(scenes/'scene-32.png'),46,100,width=560,height=300,preserveAspectRatio=True,anchor='c')
            y=360
            for point in points:y=wrap_draw(c,point,635,y,270,size=17)-18
        elif index==2:
            labels=[('COLLECTION / DATA','Sponsor path: evidence pending'),('REASONING GRAPH','Loops, gates, snapshot output'),('LOCAL WEB','Verified original-file presentation')]
            for i,(label,sub) in enumerate(labels):
                x=46+i*298;c.setFillColor('#e0ebe5');c.roundRect(x,265,275,105,8,fill=1,stroke=0);wrap_draw(c,label,x+16,341,245,'QB',13);wrap_draw(c,sub,x+16,315,245,size=12)
                if i<2:c.setStrokeColor('#137b70');c.line(x+276,317,x+295,317)
            y=220
            for point in points:y=wrap_draw(c,point,46,y,870,size=15)-10
        else:
            y=345
            for point in points:
                c.setFillColor('#137b70');c.circle(52,y+6,3,fill=1,stroke=0)
                y=wrap_draw(c,point,72,y,830,size=19 if len(points)<4 else 16)-22
        c.setFillColor('#5b716b');c.setFont('QS',9);c.drawString(46,40,'PRIVATE REVIEW · PARTIAL / PROVISIONAL · SPONSOR AND RELEASE GATES OPEN');c.drawRightString(914,40,f'{index+1} / {len(SLIDES)}')
        c.linkURL(REPO, (46,18,700,34),relative=0);c.setFont('QS',8);c.drawString(46,22,REPO+' · Issue #2 · Draft PR #6')
        c.showPage()
        notes+=f'## {tag} — {title}\n\n'+ '\n'.join('- '+p for p in points)+'\n\n'
        htmlslides.append('<section><small>'+html.escape(tag)+'</small><h1>'+html.escape(title)+'</h1>'+('<img alt="Original genuine provisional preview" src="genuine-preview.png">' if index==3 else '')+'<ul>'+''.join('<li>'+html.escape(p)+'</li>' for p in points)+'</ul><footer>PRIVATE REVIEW · PARTIAL / PROVISIONAL · NOT PRODUCTION</footer></section>')
    c.save();write(root/'slides/SPEAKER_NOTES.md',notes)
    import shutil
    shutil.copy2(scenes/'scene-32.png',root/'slides/genuine-preview.png')
    write(root/'slides/quorum-presentation.html','''<!doctype html><meta charset="utf-8"><title>Quorum · Private presentation</title><style>body{margin:0;background:#f5f3ed;color:#18342f;font:24px system-ui}section{display:none;box-sizing:border-box;height:100vh;padding:6vh 7vw;border-left:12px solid #137b70}section.active{display:block}small{color:#137b70;font-size:16px}h1{font:48px Georgia;max-width:1100px}li{margin:22px 0;max-width:1100px}img{float:left;width:48%;margin-right:40px}footer{position:absolute;bottom:25px;color:#5b716b;font-size:14px}nav{position:fixed;bottom:20px;right:25px}button{font-size:20px;margin-left:12px}</style>'''+''.join(htmlslides)+'''<nav aria-label="Slides"><button id="prev" aria-label="Previous slide">←</button><button id="next" aria-label="Next slide">→</button></nav><script>let at=0;const slides=[...document.querySelectorAll('section')];function show(n){at=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>s.classList.toggle('active',i===at));}document.querySelector('#prev').onclick=()=>show(at-1);document.querySelector('#next').onclick=()=>show(at+1);addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(at+1);if(e.key==='ArrowLeft')show(at-1)});show(0);</script>''')


def prepare(repo,candidate,root,scenes):
    if not (root/'video/EDIT_MANIFEST.json').is_file():raise ValueError('Build and verify private video first')
    import shutil
    make_deck(root,scenes)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    candidate_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=candidate,text=True).strip()
    for name in ('ARCHITECTURE.md','DECISIONS.md'):
        (root/'architecture').mkdir(exist_ok=True);shutil.copy2(candidate/'docs'/name,root/'architecture'/name)
    (root/'evidence').mkdir(exist_ok=True)
    for name in ('RELEASE_MATRIX.md','DEMO.md'):shutil.copy2(repo/'integration_support'/name,root/'evidence'/name)
    shutil.copy2(repo/'docs/RULES_CHECK.md',root/'evidence/ORGANIZER_REQUIREMENTS.md')
    write(root/'README.md',f'''# Quorum — private submission review package

Primary track intended: 03, Reasoning Architecture. Deadline: October 27, 2026, 23:45 UTC.

Private package; no upload, deployment, publication or submission has occurred. Overall sign-off: NO-GO until the blockers below close. Video master is silent with burned captions; the exact recording script is the authorized alternative to an unreliable synthetic voice.

## Contents

- `video/quorum-final-3m42s.webm`: exact 3:42 captioned edit of genuine recorded footage and authenticated UI still holds. The still holds are editorial pacing, not live inference.
- `video/quorum-captions.vtt` / `.srt`: synchronized to the frame-indexed edit; `RECORDING_SCRIPT.md`: exact script for Vadim.
- `slides/quorum-presentation.pdf` / `.html`: seven-slide deck; `SPEAKER_NOTES.md`.
- `architecture/`: canonical candidate architecture and decisions, including superseded historical entries. Local preview is verified; sponsor production route is intended/unproved.
- `SETUP.md`, `DEPENDENCIES.md`, `DISCLOSURES.md`, `ORGANIZER_CHECKLIST.md`.
- `source/candidate-source.tar.gz`: complete tracked candidate source, not private runtime data or original v3 files. Unapproved local assembly; no owner adoption claim.
- `evidence/`: test matrix and organizer evidence. `QA/`: transition/privacy review and hashes.

## Revisions and links

Support source: {sha}. Candidate: {candidate_sha} (local only). Preserve reasoning `3d89448` → collection `8f126c5` → web `f59e758`. Original snapshot and sidecar remain private and unchanged; neither is distributed here.

Repository: {REPO}
Tracker: {REPO}/issues/2
Reasoning: {REPO}/pull/4 · Web: {REPO}/pull/5 · Support proposals: {REPO}/pull/6
Candidate pipeline baseline: {REPO}/actions/runs/40146091869 and {REPO}/actions/runs/40146088967
Organizer: {EVENT}

## Remaining human gates

Yelysei: original config/execution evidence, privacy/memory review, genuine full Nightshift/NVIDIA workflow evidence. Anastasia: exact DocRefs/corpus manifest and actual Zetaris/database evidence. Vadim: optional voice recording, timing/privacy/content review, actual workspace format/link checks and final authorized upload. All: owner approvals, pre-existing-work attestation, team/track selection and final submission. Public release additionally needs secure bridge/auth, restricted backup/restore and deployment approval.
''')
    write(root/'SETUP.md',f'''# Reproduce safely

Source code: {REPO}; this package contains the tracked local candidate. It is not an approved merged release. Prerequisites: Python 3.11, Node 22, Git and existing/offline-installable dependencies. Use an external virtualenv and build directory. No model or data-service credentials are needed for fixture tests.

```bash
python3 -m venv <external-venv>
<external-python> -m pip install -r backend/requirements.txt
<external-python> -m pip install -e 'reasoning[dev]'
QUORUM_DRY_RUN=1 PYTHONPATH=reasoning <external-python> -m pytest reasoning/tests -q
DJANGO_DEBUG=1 QUORUM_PORTAL_DATA=<new-external-test-data> <external-python> backend/manage.py test portal
QUORUM_WEB_BUILD=<external-build> bash deploy/build-web.sh
QUORUM_PYTHON=<external-python> node web/tests/boundary.cjs --reasoning
```

The last command uses clearly fictional bundled inputs and temporary local auth. It is not genuine evidence. For genuine preview acceptance, request the original v3 and sidecar privately, verify the pinned hashes in `video/EDIT_MANIFEST.json`, export the pinned 40-source registry with `deploy/export-catalog.py`, and follow `integration_support/DEMO.md` on the support branch. The package deliberately excludes the original private artifacts. Execution attestation still fails `producer_config_mismatch`; do not edit evidence to make it pass.

No inference, collection, publisher activation, deployment or public uploads are part of these commands. Dependency installation may require network if not cached; it is not sponsor operational evidence. Do not point test auth/snapshot paths at production.
''')
    write(root/'TECHNOLOGY_USE.md',"""# Technology-use explanation — evidence boundaries

**Zetaris:** intended as the reasoning graph's single read layer over collected publications, official records and source metadata. Stable DocRefs, hashes/access levels and Unicode quote offsets carry provenance across the boundary. Schema/CSV/hash contracts pass offline; authentic query/row and corpus-manifest proof still needs Anastasia. Do not claim the federation is independently demonstrated by this package.

**Meterless Nightshift / NVIDIA Nemotron:** the planned lane split uses fast research and separate larger-model blind verification/review. Five historical small routing probes and original producer model declarations exist. They do not prove the complete Nightshift-powered Quorum workflow, nor resolve the original config discrepancy. Yelysei supplies genuine execution/route evidence; no inference was run to build these presentation assets.

**H-MEM Engine proposal:** memory may prioritize exact current authorized source candidates; it must not copy a remembered verdict/quote into evidence. Fresh source/stance/quote/access/independence checks still apply. Reference conformance is 13/13, with prior 16 TEST-state hook cases. Hooks/storage safeguards remain default-off proposals pending Yelysei/Anastasia review and genuine owner-graph proof. The reference component passing tests is not sponsor integration completion.

**Web product:** Django owns sessions, CSRF and bounded APIs; Next.js/TypeScript renders an authenticated original-file local preview, explicit partial/provisional states, source attribution, four rating modes and recorded operations. Secure production transport/publisher activation remain gated. The distinctive design goal is inspectable provenance and visible verification limits rather than treating the model's label as a fact.

**Development:** Vadim uses Codex; Yelysei uses Claude Code; Anastasia confirms her tool. Cursor is optional under the current organizer rule. Do not invent Cursor use, live sponsor requests, genuine featured stories or a production release.
""")
    depfiles=['backend/requirements.txt','collectors/requirements.txt','reasoning/pyproject.toml','web/package.json','web/package-lock.json']
    for name in depfiles:
        target=root/'dependencies'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(candidate/name,target)
    write(root/'DEPENDENCIES.md','''# Dependencies

Exact project requirements and web lockfile are in `dependencies/`. Runtime: Python 3.11, Node 22, Django, Next.js/React/TypeScript, LangGraph and collector Python packages. Authoritative pins are the copied files, not an unrelated machine-wide freeze.

Private presentation tooling: Python Pillow and ReportLab, installed Playwright/Chromium, and the official Playwright FFmpeg 1013 build (PNG encoding, MJPEG input, VP9/WebM output). Existing offline tools do not provide a reliable natural voice; no voice clone or paid TTS was used. Final master has no audio track. WebM/PDF acceptance and upload limits in the authenticated workspace remain unverified.

Third-party packages and the unchanged official H-MEM reference retain their own licenses. No dependencies, vendor checkout, model weights or service credentials are bundled. Sponsor code availability/reference tests do not establish operational sponsor integration.
''')
    dates=subprocess.check_output(['git','log',candidate_sha,'--format=%aI|%cI'],cwd=repo,text=True).splitlines()
    earliest=min(datetime.fromisoformat(x).astimezone(timezone.utc) for row in dates for x in row.split('|'))
    write(root/'DISCLOSURES.md',f'''# Disclosures — team approval required

- Original genuine provisional v3: 28 roundup items, zero featured stories, 264 trace rows, 63 errors. Original bytes unchanged. Presentation compatible; full execution/config/source-text attestation not accepted.
- H-MEM: reference conformance 13/13 and TEST-state hook evidence; default-off owner-graph proposals are not adopted/genuinely demonstrated.
- Nightshift/NVIDIA: five historical small routing probes and producer model declarations do not prove the complete required workflow.
- Zetaris: code/contracts and owner documentation exist; this package does not independently prove actual queries/rows.
- Current actual development tools: Codex (Vadim), Claude Code (Yelysei), Anastasia to confirm her tool. Organizer rule 5.1 now makes Cursor optional. Do not invent Cursor use.
- Git-recorded earliest author/committer timestamp in the candidate ancestry: {earliest.isoformat()}. The build window starts 2026-10-22T00:00:00Z. This does not prove no work was reused from elsewhere. All team members must attest to pre-existing product code and declare it in the form where applicable.
- No Colab runtime is claimed; the team must confirm whether any additional Colab links are applicable.
- The organizer may show submitted demo/screenshots/description. Before upload, team members must review the political reporting excerpts, source attribution, privacy and publication rights. No article text, original private snapshot/sidecar, credentials or private auth database is bundled separately.
- No submission, deployment or production publishing is authorized by preparing this package.
''')
    write(root/'ORGANIZER_CHECKLIST.md',f'''# Organizer checklist — checked 2026-10-25 UTC

Authority: [expanded official event rules]({EVENT}); [official Academy](https://academy.genai.works/courses/open-agent-hackathon-2026/details). Public requirements are verified; authenticated workspace fields/formats/limits are NOT TESTED. This supplements, not replaces, Issue #2.

| Requirement | Package / outcome | Owner |
| --- | --- | --- |
| 1–4 minute workflow/sponsor video (6.1) | 3:42 captioned WebM; final human content/timing/voice review pending. | Vadim |
| Deck topics and visuals (6.2) | Seven-slide PDF + offline HTML and notes prepared. | Vadim / all |
| GitHub source and setup/usage/dependencies (6.3) | Repo/PR links, tracked candidate archive, README/setup/locks included; combined candidate not yet approved remotely. | All |
| Technology-use explanation (6.4) | Evidence/limitations disclosed; genuine sponsor end-to-end proof remains BLOCKED. | Yelysei / Anastasia |
| Required Zetaris + Meterless (5.1) | BLOCKED for complete verified integration. | Yelysei / Anastasia |
| NVIDIA contribution (5.2) | Partial producer/probe evidence; complete genuine route proof BLOCKED. | Yelysei |
| Cursor optional (5.1) | VERIFIED; no Cursor waiver evidence blocker remains. | Vadim |
| One primary track (3.2) | Intended Track 03; actual team workspace selection NOT TESTED. | Vadim / team lead |
| Team/eligibility (1–2) | Human account, team size/membership and eligibility confirmations pending. | All |
| Pre-existing work (4.2/5.4) | DISCLOSURES.md supplied; human attestation/form disclosure pending. | All |
| Publication permission (9) | Human privacy/rights approval pending before organizer display. | All |
| Deadline and updates (4/10) | October 27, 2026, 23:45 UTC; recheck current notices before upload. | Team lead |

Missing workspace-only details: accepted video/deck formats and size limits, judge-accessible video link or upload, repository visibility/access, any required form fields, account/track confirmation and final submission receipt. No public rule requires a particular MP4/PDF format; do not infer platform support. If Colab was used elsewhere, add its links. No entry has been submitted.
''')
    (root/'source').mkdir(exist_ok=True)
    with (root/'source/candidate-source.tar.gz').open('wb') as stream:subprocess.run(['git','archive','--format=tar.gz',candidate_sha],cwd=repo,stdout=stream,check=True)
    # DECISION(2026-10-25, rcc00n/Codex): archive tracked source only; never original/private runtime evidence.
    # Why: a judge's reproduction package must not accidentally redistribute credentials or private corpora.
    with tarfile.open(root/'source/candidate-source.tar.gz') as archive:
        for entry in archive:
            path=Path(entry.name)
            if path.is_absolute() or '..' in path.parts or entry.issym() or entry.islnk():raise ValueError('Unsafe source archive path')
            if path.name.startswith('.env') and path.name!='.env.example':raise ValueError('Private environment path')
            if path.suffix in ('.sqlite','.sqlite3','.dump','.log') or 'LOCAL-DEMO-accounts' in path.name or 'provisional-v3.snapshot' in path.name:raise ValueError('Private source artifact')
            if entry.isfile():
                data=archive.extractfile(entry).read()
                if contains_secret(data):raise ValueError('Credential pattern in source archive')
    write(root/'evidence/REVISIONS.json',json.dumps(dict(support=sha,candidate=candidate_sha,reasoning='3d89448',collection='8f126c5',web='f59e758',owner_reviews='pending',published=False,submitted=False),indent=2)+'\n')
    print('PASS: seven-slide PDF/HTML, setup/dependencies/disclosures/checklist and safe tracked source archive prepared privately')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','candidate','root','scenes'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();prepare(args.repo.resolve(),args.candidate.resolve(),args.root.resolve(),args.scenes.resolve())
