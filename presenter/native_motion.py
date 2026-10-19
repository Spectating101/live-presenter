"""Headless native-motion export with explicit scripted-cue provenance."""
import json
from pathlib import Path
import shutil
import subprocess
import time


SCRIPT = [
    (0, 'Flow rate in the supplied measurements.'),
    (2, 'At the high setting.'),
    (4, 'Compare the low setting and the high setting.'),
    (7, 'Now electrical power consumption.'),
    (9, 'At the high setting.'),
    (11, 'Compare the low setting and the high setting.'),
]


def export_motion(app, surface, store, studio, pid, folder, *, reduced=False):
    from PySide6.QtGui import QImage
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('Motion export requires ffmpeg; no visible window was opened.')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    surface.resize(1280,720)
    surface.animate=not reduced
    virtual=[0.]
    surface.clock=lambda:virtual[0]
    # The caller sets QT_QPA_PLATFORM=offscreen before creating QApplication.
    # Showing an offscreen widget is needed for ordinary paint-event delivery;
    # it cannot occupy or capture the user's desktop.
    surface.show()
    from .native_output import VisualOutput
    output=VisualOutput()
    fps,duration=24,14
    video=folder/'explanation-motion.mp4'
    command=[ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-y',
        '-f','rawvideo','-pixel_format','rgba','-video_size','1280x720',
        '-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264',
        '-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
    events=[];cue=0;begun=time.perf_counter()
    with (folder/'encoder.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            for frame in range(fps*duration):
                virtual[0]=frame/fps
                if cue<len(SCRIPT) and virtual[0]>=SCRIPT[cue][0]:
                    at,words=SCRIPT[cue];p=store.read(pid)
                    p=studio.transcript(pid,words,cue,generation=p['live']['generation'])
                    output.accept(p);surface.present(output)
                    events.append({'at_s':at,'utterance':words,'scene_id':output.scene['id'],
                        'attention':output.attention,'decision':p['live']['decision']})
                    cue+=1
                surface.update();app.processEvents()
                image=surface.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                process.stdin.write(image.constBits())
                if frame in {round(5.5*fps),round(12.5*fps)}:
                    image.save(str(folder/f'comparison-{frame}.png'))
            process.stdin.close();process.wait(timeout=30)
            if process.returncode:
                raise RuntimeError('The native motion encoder failed; inspect encoder.log.')
        except BaseException:
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
            raise
    project=store.read(pid)
    report={'schema':'live_presenter.native_motion_probe.v1',
        'browser_used':False,'visible_window_opened':False,'desktop_captured':False,
        'renderer':'Qt QPainter offscreen','frame_rate':fps,'duration_s':duration,
        'reduced_motion':reduced,'frames':fps*duration,'size':[1280,720],
        'input':'Scripted text cues supplied causally at the listed export times.',
        'asr_used':False,'model_calls':0,'source':'Illustrative supplied measurements; heat removal was not measured.',
        'source_sha256':project['sources'][0]['sha256'],
        'approved_package_hash':project['approval']['package_hash'],
        'interpretation':'Native rendering and grounded arithmetic demonstration. Editorial timing is scripted; not a live microphone, AI-visual-generation, or audience-learning evaluation.',
        'encoding_wall_s':time.perf_counter()-begun,'events':events}
    (folder/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('Headless native motion sample saved to '+str(video),flush=True)
