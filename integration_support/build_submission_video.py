#!/usr/bin/env python3
"""Offline edit of genuine footage and authenticated stills. No network or provider calls."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import textwrap

FPS=10
WIDTH,HEIGHT=1920,1080
# DECISION(2026-10-25, rcc00n/Codex): frame-indexed edits and captions replace wall-clock recording deadlines.
# Why: capture timestamps drifted; an exact 222-second edit must preserve genuine states and every rating mode.
PLAN=[
 (12,('video',0), 'News reaches us through many outlets, often with different claims and framing. Quorum helps readers inspect the reporting, its sources, and the checks behind it.'),
 (26,('video',12), 'This is an authenticated local preview of the original provisional result. It contains twenty-eight roundup events and zero featured stories. The output is partial. Quorum keeps those limits visible instead of filling the page with an invented article. A recorded result is not a verified production release.'),
 (22,('video',38), 'Each roundup entry keeps the producer’s status and original source links. These are attributions, not independent confirmation. Readers can follow the reporting back to its publisher and inspect the recorded checks for that event. We have not opened external publisher pages during this demonstration.'),
 (40,('video',60), 'The investigation timeline shows recorded operations, not live inference or private chain-of-thought. Filters keep the stages within the selected event. Repeated stages reveal a return for more research; they do not prove that the conclusion is correct. A skipped independent check must remain explicit. Missing checks never mean confirmed. This result supplies no featured article or exported claim-evidence chain, so we do not manufacture one for the demo.'),
 (12,('still',125), 'Here is the AllSides rating view. Positions come from the joined source registry. Editorial position describes the source; it is not a measure of factual accuracy.'),
 (12,('still',140), 'Switching to MBFC recalculates the displayed source positions. The source identities stay the same. Missing provider ratings remain missing, rather than quietly becoming a neutral score.'),
 (12,('still',155), 'Ad Fontes gives another external rating view. This is the same genuine forty-source registry. Audience estimates are shown only where the registry supplies attribution.'),
 (12,('still',162), 'The average combines available normalized ratings. It does not invent values for missing providers. Readers can compare all four modes without changing the producer’s fixed reported coverage counts.'),
 (16,('still',170), 'Open a source’s rating provenance to inspect the reported values, provider links and registry date. These links make attribution inspectable. They do not establish source accuracy or independently verify every audience estimate.'),
 (18,('still',185), 'Provenance matters as much as presentation. The snapshot and sidecar bytes are unchanged. Their binding is checked, but a configuration digest discrepancy still blocks full execution acceptance. Model names remain producer declarations, not independent provider receipts.'),
 (10,('still',195), 'Partial failures stay visible through safe diagnostics. We show uncertainty instead of turning missing evidence or provider failures into a successful verification claim.'),
 (30,('still',212), 'The local product, validators, packaging and rollback mechanisms pass offline checks. H-MEM reference conformance passes, while genuine owner-graph memory remains unproved. Historical Nightshift probes do not establish the complete workflow. Zetaris and Meterless remain required sponsor gates. Next come owner review, genuine execution evidence and secure integration. Quorum’s value is an inspectable path from reporting to evidence, with its limits left visible.'),
]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def timeline():
    result=[];start=0
    for duration,source,text in PLAN:
        words=text.split();chunks=[];current=[]
        for word in words:
            current.append(word)
            if len(' '.join(current))>=85 and (word.endswith(('.', ';', ',')) or len(current)>=20):
                chunks.append(' '.join(current));current=[]
        if current:chunks.append(' '.join(current))
        weight=sum(len(c.split()) for c in chunks);at=start
        for index,chunk in enumerate(chunks):
            end=start+duration if index==len(chunks)-1 else at+duration*len(chunk.split())/weight
            result.append(dict(start=at,end=end,text=chunk));at=end
        start+=duration
    assert start==222
    return result

def stamp(seconds,separator='.'):
    ms=round(seconds*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}{separator}{ms%1000:03}'

def validate_output(output):
    if not output.is_absolute() or output.exists():raise ValueError('Use a NEW absolute external output directory')
    if any((p/'.git').exists() for p in (output,*output.parents)):raise ValueError('Keep private package outside repositories')

def validate_inputs(raw,scenes):
    receipt=json.loads((scenes/'receipt.json').read_text())
    if receipt.get('capture_type')!='authenticated-stills':raise ValueError('Authenticated original-evidence scenes required')
    if receipt.get('snapshot_sha256')!='c223bc156b7d80049db24483140f45a1ee065f20106062d69bb249171fa07a30' or receipt.get('sidecar_sha256')!='1afba4c0eb7934139d0428f15f55db4d0683bf73d6a0da7edb08992aa5785775':raise ValueError('Pinned originals required')
    if any(receipt.get(k) is not False for k in ('published','execution_attested','owner_memory_adopted','sponsor_completion')):raise ValueError('Unverified claims cannot be promoted')
    if digest(raw)!='4a03ef5049b8c8eec1cd5068fe89f53bb6027963ca224de95ae26693477f245e':raise ValueError('Reviewed genuine source footage required')
    for _,(kind,value),_ in PLAN:
        if kind=='still' and not (scenes/f'scene-{value}.png').is_file():raise ValueError('Missing authenticated scene')
    return receipt

def render(image,caption,scene):
    from PIL import Image, ImageDraw, ImageFont
    canvas=Image.new('RGB',(WIDTH,HEIGHT),'#101e20');canvas.paste(image.convert('RGB'),(240,0))
    draw=ImageDraw.Draw(canvas)
    small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',21)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',29)
    draw.text((80,917),'QUORUM  /  RECORDED LOCAL PREVIEW  ·  PARTIAL / PROVISIONAL  ·  28 ROUNDUP ITEMS  ·  0 STORIES',font=small,fill='#9bd4cb')
    lines=textwrap.wrap(caption,width=110)
    if len(lines)>3:raise ValueError('Caption exceeds reserved band')
    for i,line in enumerate(lines):draw.text((WIDTH/2,958+i*35),line,font=font,anchor='mt',fill='#faf8f2')
    stream=BytesIO();canvas.save(stream,format='JPEG',quality=94,subsampling=0);return stream.getvalue(),canvas

def build(raw,scenes,output,ffmpeg):
    from PIL import Image
    validate_output(output);receipt=validate_inputs(raw,scenes)
    output.mkdir(parents=True,mode=0o700);(output/'work').mkdir();(output/'review').mkdir();(output/'video').mkdir()
    cues=timeline();vtt='WEBVTT\n\n'+''.join(f"{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}\n\n" for c in cues)
    (output/'video/quorum-captions.vtt').write_text(vtt)
    srt=''.join(f"{i+1}\n{stamp(c['start'],',')} --> {stamp(c['end'],',')}\n{c['text']}\n\n" for i,c in enumerate(cues))
    (output/'video/quorum-captions.srt').write_text(srt)
    script='# Vadim — exact recording script\n\nTarget: 3:42. Natural English, calm delivery. Captions are burned in and supplied separately. No synthetic voice or audio track was generated. Pause naturally at punctuation. Record against the exact scene slots below; final voice recording/mux remains a human gate.\n\n'
    at=0;edits=[]
    for duration,source,text in PLAN:
        script+=f'## {stamp(at)}–{stamp(at+duration)}\n\n{text}\n\n';edits.append(dict(start=at,end=at+duration,source=list(source),spoken_words=len(text.split())));at+=duration
    (output/'video/RECORDING_SCRIPT.md').write_text(script)
    video=output/'video/quorum-final-3m42s.webm';log=(output/'work/encode.log').open('wb')
    command=[str(ffmpeg),'-hide_banner','-loglevel','error','-f','image2pipe','-c:v','mjpeg','-r',str(FPS),'-i','pipe:0','-an','-c:v','libvpx-vp9','-b:v','0','-crf','28','-deadline','realtime','-cpu-used','6','-row-mt','1','-threads','4','-pix_fmt','yuv420p',str(video)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
    frame_index=0;cue_index=0;inputs=[]
    try:
        for index,(duration,(kind,value),_) in enumerate(PLAN):
            count=duration*FPS
            if kind=='video':
                directory=output/'work'/f'clip-{index}';directory.mkdir()
                subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-ss',str(value),'-i',str(raw),'-t',str(duration),'-r',str(FPS),'-c:v','png',str(directory/'frame-%06d.png')],check=True,stdout=subprocess.DEVNULL,stderr=log)
                frames=sorted(directory.glob('frame-*.png'))
                if not frames:raise ValueError('Footage decode failed')
                inputs.append(dict(type='genuine-recorded-video',start=value,duration=duration))
            else:
                frames=[scenes/f'scene-{value}.png'];inputs.append(dict(type='authenticated-still-hold',scene=value,sha256=digest(frames[0])))
            cache={}
            for offset in range(count):
                time=frame_index/FPS
                while cue_index<len(cues)-1 and time>=cues[cue_index]['end']:cue_index+=1
                source=frames[min(offset,len(frames)-1)]
                key=(str(source),cue_index)
                if key not in cache:
                    with Image.open(source) as image:
                        if image.size!=(1440,900):raise ValueError('Unexpected source dimensions')
                        data,review=render(image,cues[cue_index]['text'],index)
                    if kind=='still':cache={key:data}
                else:data=cache[key];review=None
                if offset in (0,1,count-2,count-1):
                    if review is None:
                        with Image.open(source) as image:_,review=render(image,cues[cue_index]['text'],index)
                    review.save(output/'review'/f'transition-{index:02}-{offset:04}.png')
                process.stdin.write(data);frame_index+=1
            print(f'PASS: edited scene {index+1}/{len(PLAN)} through {frame_index/FPS:.1f}s',flush=True)
        process.stdin.close()
        if process.wait()!=0:raise ValueError('Offline encode failed; inspect private log')
    finally:
        if process.poll() is None:process.kill();process.wait()
        log.close()
    if frame_index!=222*FPS:raise ValueError('Incorrect final frame count')
    probe=subprocess.run([str(ffmpeg),'-hide_banner','-i',str(video)],capture_output=True,text=True)
    match=re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)',probe.stderr)
    if not match:raise ValueError('Encoded duration unavailable')
    h,m,s=map(float,match.groups());actual=h*3600+m*60+s
    if not 220<=actual<=225:raise ValueError('Final video outside requested duration')
    manifest=dict(duration_seconds=actual,frame_count=frame_index,fps=FPS,video_sha256=digest(video),raw_sha256=digest(raw),original_snapshot_sha256=receipt['snapshot_sha256'],original_sidecar_sha256=receipt['sidecar_sha256'],candidate=receipt['candidate'],edits=edits,inputs=inputs,audio_track=False,voiceover_status='exact-script-for-Vadim',caption_sync='frame-indexed and burned-in',public_upload=False,execution_attested=False,sponsor_completion=False)
    (output/'video/EDIT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',duration_seconds=actual,frame_count=frame_index,video_sha256=manifest['video_sha256'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('raw','scenes','output','ffmpeg'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();build(args.raw.resolve(),args.scenes.resolve(),args.output,args.ffmpeg.resolve())
