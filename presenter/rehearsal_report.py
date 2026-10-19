"""Export a watchable reconstruction of measured stage API observations."""
import argparse
import base64
import html
import io
import json
from pathlib import Path
import subprocess
import textwrap
import wave

from .recording import save


TERMS={'prepared_loop':('pump','radiator'),'heat_pipe_detour':('heat pipe','heatpipe'),
       'thermoelectric_detour':('thermoelectric','peltier'),'unrelated_control':('sourdough','bread'),
       'return_to_loop':('pump','radiator')}


def summarize(result):
    duration=result['script'][-1]['end_s'];events=result['stage_events'];scenes=result['scenes'];segments=[]
    for section in result['script']:
        hits=[];visible_s=0
        for index,event in enumerate(events):
            scene=scenes.get(event['scene_id'],{})
            text=' '.join([scene.get('title',''),scene.get('asset',{}).get('alt',''),
                           *(r['quote'] for r in scene.get('source_refs',[]))]).lower()
            start=max(section['start_s'],event['at_s']);end=min(section['end_s'],events[index+1]['at_s'] if index+1<len(events) else duration)
            if end<=start:continue
            if any(term in text for term in section.get('topic_terms',TERMS.get(section['id'],()))):
                visible_s+=end-start;hits.append({'at_s':start,'scene_id':event['scene_id'],
                    'fresh_retrieval':bool(scene.get('web_source') and not scene['web_source'].get('presenter_reviewed')),
                    'url':scene.get('web_source',{}).get('url')})
        segments.append({'id':section['id'],'condition':section['condition'],'start_s':section['start_s'],'end_s':section['end_s'],
            'lexical_topic_on_stage_s':visible_s,'matching_stage_intervals':hits,
            'section_start_to_first_matching_scene_s':hits[0]['at_s']-section['start_s'] if hits else None})
    return {'schema':'live_presenter.rehearsal_observation_summary.v1','duration_s':duration,
        'preparation_s':result['preparation_s'],'prepared_source_count':result['prepared_source_count'],
        'prepared_scene_count':result['prepared_scene_count'],'operator_interventions_during_speech':result['operator_interventions_during_speech'],
        'online_results_injected_by_operator':result['online_results_injected_by_operator'],
        'research_completions':len(result['research_history']),'automatically_displayed_research':sum(r['displayed_automatically'] for r in result['research_history']),
        'stage_changes':max(0,len(events)-1),'worker':result['worker'],'observer_errors':result['observer_errors'],
        'segments':segments,'evaluation':'Lexical checks of actual scene title, quotation and image description. Query strings are excluded. No independent factual, visual or audience-quality judgment.',
        'browser_used':False,'physical_microphone_used':False,'speech':result['input']['speech'],
        'limitations':result['limitations']}


def frame(scene,destination,*,recorded=False):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    image=Image.new('RGB',(1280,720),'#f5f6f0');draw=ImageDraw.Draw(image)
    regular='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    font=lambda size,strong=False:ImageFont.truetype(bold if strong else regular,size)
    origin=scene.get('web_source',{})
    label='PREPARED VISUAL' if not origin else 'RESEARCHED BEFORE TALK · REVIEWED' if origin.get('presenter_reviewed') else 'RETRIEVED DURING TALK · PROVISIONAL'
    draw.text((38,18),'STAGE API RECONSTRUCTION · '+('RECORDED TED AUDIO' if recorded else 'SYNTHETIC SPEECH')+' · NOT A SCREEN RECORDING',font=font(15),fill='#53675c')
    draw.rounded_rectangle((24,52,1256,690),radius=16,fill='white',outline='#dce3dc',width=2)
    draw.text((48,68),label,font=font(17,True),fill='#2d6657')
    title=scene.get('title','').replace('_',' ')
    if scene['kind']=='image':
        for suffix in ('.png','.jpg','.jpeg','.svg'):title=title.removesuffix(suffix)
    for i,line in enumerate(textwrap.wrap(title,64)[:2]):draw.text((48,98+36*i),line,font=font(30,True),fill='#173a30')
    top=183
    if scene['kind']=='image':
        data=base64.b64decode(scene['asset']['data_url'].split(',',1)[1])
        picture=Image.open(io.BytesIO(data)).convert('RGB');picture=ImageOps.contain(picture,(1150,380))
        image.paste(picture,((1280-picture.width)//2,top+(380-picture.height)//2))
    else:
        content=scene.get('body') or [r['quote'] for r in scene.get('source_refs',[])]
        if scene['kind']=='flow':content=scene.get('nodes',content)
        lines=[]
        for point in content:lines.extend(textwrap.wrap(point,83));lines.append('')
        for i,line in enumerate(lines[:11]):draw.text((54,top+32*i),line,font=font(24),fill='#173a30')
    if origin:
        credit=origin['url']
        if origin.get('image_url'):credit+=' | '+origin.get('artist','')+' | '+origin.get('image_license','')
    else:credit=' · '.join(dict.fromkeys(r['source_name'] for r in scene.get('source_refs',[])))
    for i,line in enumerate(textwrap.wrap(credit,135)[:3]):draw.text((48,605+21*i),line,font=font(15),fill='#526359')
    image.save(destination)


def report(folder,*,video=False):
    folder=folder.absolute();result=json.loads((folder/'result.json').read_text());summary=summarize(result)
    save(folder/'summary.json',summary)
    events=result['stage_events'];scenes=result['scenes'];frames=folder/'frames';frames.mkdir(exist_ok=True)
    for index,event in enumerate(events):frame(scenes[event['scene_id']],frames/f'{index:03d}.png',recorded=bool(result['input'].get('fixture')))
    if video and events:
        with wave.open(str(folder/'audio.wav'),'rb') as wav:duration=wav.getnframes()/wav.getframerate()
        lines=['ffconcat version 1.0']
        for index,event in enumerate(events):
            start=0 if index==0 else event['at_s'];end=events[index+1]['at_s'] if index+1<len(events) else duration
            if start>=duration:continue
            lines.extend([f"file 'frames/{index:03d}.png'",f'duration {max(.04,end-start):.6f}'])
        lines.append(f"file 'frames/{len(events)-1:03d}.png'")
        (folder/'frames.ffconcat').write_text('\n'.join(lines)+'\n')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i','frames.ffconcat',
            '-i','audio.wav','-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-crf','23',
            '-pix_fmt','yuv420p','-c:a','aac','-shortest','-movflags','+faststart','stage-api-reconstruction.mp4'],
            cwd=folder,check=True,capture_output=True,timeout=180)
    esc=lambda value:html.escape(str(value),quote=True)
    rows=''.join('<tr><td>'+esc(row['id'])+'</td><td>'+esc(row['condition'])+'</td><td>'+f'{row["lexical_topic_on_stage_s"]:.1f}s'+'</td><td>'+esc(row['section_start_to_first_matching_scene_s'])+'</td></tr>' for row in summary['segments'])
    links=''.join(f'<li><a href="{esc(scene["web_source"]["url"])}">{esc(scene["title"])}</a></li>' for scene in scenes.values() if scene.get('web_source'))
    cards=''.join(f'<section><h3>{event["at_s"]:.2f}s · {esc(scenes[event["scene_id"]]["title"])}</h3><img src="frames/{i:03d}.png" alt="Observed stage API scene"></section>' for i,event in enumerate(events))
    media='<video controls preload="metadata" src="stage-api-reconstruction.mp4"></video>' if video else '<audio controls src="audio.wav"></audio>'
    (folder/'index.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Researched rehearsal</title><style>body{{font:18px/1.5 system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#f5f6f0;color:#173a30}}
video,img{{width:100%}}section{{background:white;padding:1rem;border-radius:12px;margin:1rem 0}}td,th{{text-align:left;padding:.6rem;border-bottom:1px solid #ccd5ce}}a{{color:#235f80}}</style>
<h1>Continuous researched rehearsal</h1><p>Actual paced audio → local ASR → unattended web research → stage API.</p>
<p><strong>{esc(result['input']['speech'])}; reconstructed API visuals. Browser paint, physical microphone and independent quality were not tested.</strong></p>
{media}<section><h2>Supplied brief and notes</h2><p>{esc(result['input']['brief'])}</p><p>{esc(result['input']['supplied_notes'])}</p>
<p>Preparation took {result['preparation_s']:.2f}s and produced {result['prepared_source_count']} sources / {result['prepared_scene_count']} scenes.
The detour script was withheld from preparation. Operator interventions during speech: {result['operator_interventions_during_speech']}.</p></section>
<h2>Observed topic checks</h2><p>{esc(summary['evaluation'])}</p><table><tr><th>Segment</th><th>Condition</th><th>Topic terms visible</th><th>First match after segment start (s)</th></tr>{rows}</table>
<p>See <a href="summary.json">summary.json</a> and private result.json for measurements and provenance.</p>
<h2>Source links</h2><ul>{links}</ul><h2>Actual scene changes</h2>{cards}
<h2>Limits</h2><ul>{''.join('<li>'+esc(value)+'</li>' for value in summary['limitations'])}</ul></html>''',encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);parser.add_argument('--video',action='store_true')
    args=parser.parse_args();summary=report(args.folder,video=args.video)
    print(json.dumps({k:summary[k] for k in ('duration_s','research_completions','automatically_displayed_research','stage_changes')}))


if __name__=='__main__':main()
