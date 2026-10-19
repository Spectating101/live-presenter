"""Native visual-only output. No browser, pages, cards or onscreen controls.

Use --demo for terminal-driven rehearsal, or attach read-only to an existing
store/project. The optional Qt dependency is isolated from the backend.
"""
import argparse
import base64
from collections import OrderedDict
import fcntl
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time

from .native_output import VisualOutput, demo_engine, axis_label


def qt_types():
    try:
        from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
        from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError:
        raise SystemExit('Native output needs the optional environment: .venv-native/bin/python -m pip install -r requirements-native.txt') from None

    class VisualSurface(QWidget):
        def __init__(self, *, animate=False, clock=time.perf_counter):
            super().__init__()
            self.setWindowTitle('Live Presenter visual output')
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
            self.setCursor(Qt.CursorShape.BlankCursor)
            self.resize(1600, 900)
            self.scene = self.attention = None
            self.images = OrderedDict()
            self.samples = []
            self.pending_at = None
            self.animate, self.clock = animate, clock
            self.transition_started = clock()
            self.from_weights = []
            self.to_weights = []
            self.animation_timer = QTimer(self)
            self.animation_timer.timeout.connect(self.advance_motion)
            self.setAccessibleName('Live visual explanation')

        def advance_motion(self):
            if self.clock() - self.transition_started >= .7:
                self.animation_timer.stop()
            self.update()

        def motion_progress(self):
            return min(1,max(0,(self.clock()-self.transition_started)/.42)) if self.animate else 1

        def emphasis_weights(self):
            t=self.motion_progress();t=t*t*(3-2*t)
            return [a+(b-a)*t for a,b in zip(self.from_weights,self.to_weights)]

        def present(self, state, received_at=None):
            scene = state.scene
            previous_weights=self.emphasis_weights()
            same_scene=bool(scene and self.scene and scene['id']==self.scene['id'])
            if scene and scene['kind'] in {'image','annotated_image'}:
                digest = scene['asset']['sha256']
                if digest not in self.images:
                    encoded = scene['asset']['data_url'].split(',', 1)[1]
                    image = QImage.fromData(base64.b64decode(encoded, validate=True))
                    if image.isNull():
                        raise ValueError('An approved image could not be decoded; keeping the last visual.')
                    self.images[digest] = image
                    while len(self.images) > 8:
                        self.images.popitem(last=False)
                self.images.move_to_end(digest)
            self.scene, self.attention = scene, state.attention
            if scene and scene['kind']=='chart':
                chosen=set((self.attention or {}).get('target_ids',[]))
                single=(self.attention or {}).get('annotation_id')
                if single:chosen.add(single)
                self.to_weights=[1 if not chosen or f'datum_{i}' in chosen else .25 for i,_ in enumerate(scene['data'])]
                self.from_weights=previous_weights if same_scene and len(previous_weights)==len(self.to_weights) else [1]*len(self.to_weights)
            else:
                self.from_weights=self.to_weights=[]
            self.transition_started=self.clock()
            if self.animate:self.animation_timer.start(16)
            self.pending_at = received_at if received_at is not None else time.perf_counter()
            if scene and scene['kind'] == 'chart':
                self.setAccessibleDescription(scene['y']+' by '+scene['x']+': '+', '.join(
                    f"{r['label']} {r['value']:g}" for r in scene['data']))
            elif scene:
                self.setAccessibleDescription(scene.get('asset',{}).get('alt',scene.get('label','')))
            else:
                self.setAccessibleDescription('No visual displayed.')
            self.update()

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(event)

        def paintEvent(self, event):
            started = time.perf_counter()
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.fillRect(self.rect(), QColor('#101416'))
            if self.scene:
                if self.scene['kind'] == 'chart':
                    self.draw_chart(painter)
                elif self.scene['kind'] in {'image','annotated_image'}:
                    self.draw_image(painter)
                elif self.scene['kind'] == 'metric':
                    self.draw_metric(painter)
            painter.end()
            finished = time.perf_counter()
            if self.pending_at is not None:
                self.samples.append({'scene_id':(self.scene or {}).get('id'),
                    'target_id':(self.attention or {}).get('annotation_id'),
                    'target_ids':(self.attention or {}).get('target_ids',[]),
                    'motion_enabled':self.animate,
                    'received_to_paint_callback_ms':(finished-self.pending_at)*1000,
                    'paint_callback_ms':(finished-started)*1000})
                self.samples = self.samples[-100:]
                self.pending_at = None

        def make_font(self, pixels, weight=QFont.Weight.Normal):
            font = QFont('Sans Serif')
            font.setPixelSize(max(12, round(pixels)))
            font.setWeight(weight)
            return font

        def draw_chart(self, p):
            scene, rows = self.scene, self.scene['data']
            if not rows:
                return
            w,h = self.width(),self.height()
            p.fillRect(self.rect(), QColor('#f8fafb'))
            size = max(14, min(h*.035, (h-120)/max(len(rows),1)*.55))
            p.setFont(self.make_font(size))
            metrics = QFontMetricsF(p.font())
            left = min(w*.30, max(w*.13, max(metrics.horizontalAdvance(r['label']) for r in rows)+w*.04))
            top, bottom, right = h*.10, h*.86, w*.89
            lo, hi = min(0, *(r['value'] for r in rows)), max(0, *(r['value'] for r in rows))
            if hi == lo:
                hi = lo+1
            normalizer=max(1,abs(lo),abs(hi))
            scaled_lo,scaled_hi=lo/normalizer,hi/normalizer
            x = lambda value: left+((value/normalizer-scaled_lo)/(scaled_hi-scaled_lo))*(right-left)
            p.setPen(QColor('#87949b'))
            p.drawLine(QPointF(x(0),top),QPointF(x(0),bottom))
            p.setFont(self.make_font(h*.024))
            for i in range(5):
                value=lo*(1-i/4)+hi*(i/4)
                xx=x(value)
                p.setPen(QPen(QColor('#dce3e7'),1))
                p.drawLine(QPointF(xx,top),QPointF(xx,bottom))
                p.setPen(QColor('#38464f'))
                p.drawText(QRectF(xx-55,bottom+12,110,h*.04),Qt.AlignmentFlag.AlignHCenter,f'{value:g}')
            band=(bottom-top)/len(rows)
            focus=(self.attention or {}).get('annotation_id')
            comparison=(self.attention or {}).get('comparison')
            targets=set((self.attention or {}).get('target_ids',[]))
            if focus:targets.add(focus)
            weights=self.emphasis_weights()
            for i,row in enumerate(rows):
                yy=top+band*(i+.5)
                active=f'datum_{i}' in targets
                p.setFont(self.make_font(size,QFont.Weight.DemiBold if active else QFont.Weight.Normal))
                p.setPen(QColor('#152e3c'))
                name=QFontMetricsF(p.font()).elidedText(row['label'],Qt.TextElideMode.ElideRight,left-w*.05)
                p.drawText(QRectF(w*.02,yy-size,left-w*.04,size*2),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,name)
                p.setPen(Qt.PenStyle.NoPen)
                weight=weights[i] if i<len(weights) else 1
                muted,ink=QColor('#cbd4d8'),QColor('#126a96')
                p.setBrush(QColor.fromRgbF(*(a+(b-a)*weight for a,b in zip(
                    (muted.redF(),muted.greenF(),muted.blueF()),(ink.redF(),ink.greenF(),ink.blueF())))))
                height=min(band*.42,h*.105)
                # Keep quantitative geometry correct in every frame. Motion
                # may direct attention, but cannot fabricate transient values.
                endpoint=x(row['value'])
                bar=QRectF(min(x(0),endpoint),yy-height/2,abs(endpoint-x(0)),height)
                p.drawRect(bar)
                if active:
                    p.setBrush(QColor('#152e3c'))
                    p.drawEllipse(QPointF(x(row['value']),yy),max(4,size*.17),max(4,size*.17))
                p.setPen(QColor('#152e3c'))
                value_x=x(row['value'])+12 if row['value']>=0 else x(row['value'])-105
                align=Qt.AlignmentFlag.AlignLeft if row['value']>=0 else Qt.AlignmentFlag.AlignRight
                p.drawText(QRectF(value_x,yy-size,94,size*2),align|Qt.AlignmentFlag.AlignVCenter,f"{row['value']:g}")
            p.setFont(self.make_font(h*.029))
            p.setPen(QColor('#243d4a'))
            p.drawText(QRectF(left,bottom+h*.065,right-left,h*.05),Qt.AlignmentFlag.AlignHCenter,axis_label(scene['y']))
            p.setFont(self.make_font(h*.025))
            p.drawText(QRectF(w*.02,h*.035,left-w*.04,h*.04),Qt.AlignmentFlag.AlignRight,scene['x'].replace('_',' '))
            if comparison:
                first,second=rows[comparison['first_index']],rows[comparison['second_index']]
                delta=comparison['delta'];ratio=comparison['ratio']
                line=f"{first['label']} → {second['label']}: {delta:+g}"
                unit=axis_label(scene['y'])
                if '(' in unit:line+=' '+unit.rsplit('(',1)[1].rstrip(')')
                if ratio is not None:line+=f' · {ratio:.3g}×'
                p.setFont(self.make_font(h*.034,QFont.Weight.DemiBold))
                p.setPen(QColor('#126a96'))
                p.drawText(QRectF(left,h*.025,right-left,h*.05),Qt.AlignmentFlag.AlignHCenter,line)
                y1=top+band*(comparison['first_index']+.5)
                y2=top+band*(comparison['second_index']+.5)
                progress=self.motion_progress()
                end=y1+(y2-y1)*progress
                p.setPen(QPen(QColor('#126a96'),3))
                p.drawLine(QPointF(w*.97,y1),QPointF(w*.97,end))
                p.drawLine(QPointF(w*.957,y1),QPointF(w*.97,y1))
                p.drawLine(QPointF(w*.957,end),QPointF(w*.97,end))

        def draw_image(self, p):
            image=self.images[self.scene['asset']['sha256']]
            scale=min(self.width()/image.width(),self.height()/image.height())
            width,height=image.width()*scale,image.height()*scale
            frame=QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
            p.drawImage(frame,image)
            target=next((t for t in self.scene.get('annotations',[]) if t['id']==(self.attention or {}).get('annotation_id')),None)
            if not target:
                return
            point=QPointF(frame.x()+target['x']*width,frame.y()+target['y']*height)
            p.setFont(self.make_font(self.height()*.031))
            fm=QFontMetricsF(p.font())
            label_width=min(width-16,max(120,self.width()*.23))
            text_flags=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter|Qt.TextFlag.TextWordWrap
            measured=fm.boundingRect(QRectF(0,0,label_width-24,self.height()),int(text_flags),target['label'])
            box_w,box_h=min(label_width,measured.width()+24),measured.height()+18
            cx=frame.x()+target['label_x']*width;cy=frame.y()+target['label_y']*height
            lx=max(frame.left()+8,min(frame.right()-box_w-8,cx-box_w/2))
            ly=max(frame.top()+8,min(frame.bottom()-box_h-8,cy-box_h/2))
            box=QRectF(lx,ly,box_w,box_h)
            progress=self.motion_progress()
            leader=QPointF(point.x()+(box.center().x()-point.x())*progress,point.y()+(box.center().y()-point.y())*progress)
            p.setPen(QPen(QColor('#ffffff'),7));p.drawLine(point,leader)
            p.setPen(QPen(QColor('#142f40'),2));p.drawLine(point,leader)
            p.setBrush(Qt.BrushStyle.NoBrush)
            radius=max(7,self.height()*.014)
            p.setPen(QPen(QColor('#ffffff'),7));p.drawEllipse(point,radius,radius)
            p.setPen(QPen(QColor('#142f40'),3));p.drawEllipse(point,radius,radius)
            p.setOpacity(progress)
            p.fillRect(box,QColor('#ffffff'))
            p.setPen(QColor('#142f40'))
            p.drawText(box.adjusted(12,9,-12,-9),int(text_flags),target['label'])

        def draw_metric(self,p):
            p.setPen(QColor('#f5f8fa'))
            p.setFont(self.make_font(self.height()*.22))
            p.drawText(QRectF(0,self.height()*.26,self.width(),self.height()*.32),Qt.AlignmentFlag.AlignCenter,self.scene['value'])
            p.setFont(self.make_font(self.height()*.045))
            p.drawText(QRectF(self.width()*.1,self.height()*.61,self.width()*.8,self.height()*.2),Qt.AlignmentFlag.AlignHCenter|Qt.TextFlag.TextWordWrap,self.scene['label'])

    return QApplication, VisualSurface, QTimer


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--demo',action='store_true',help='Sourced charts; terminal text drives the existing matching engine.')
    ap.add_argument('--store',type=Path)
    ap.add_argument('--project',help='Existing project ID; read-only attachment, no server required by the renderer.')
    ap.add_argument('--export',type=Path,help='Render a deterministic demo sequence offscreen to this folder and exit.')
    ap.add_argument('--export-motion',type=Path,help='Render the speech-cue demonstration to a headless MP4 and audit file.')
    ap.add_argument('--reduced-motion',action='store_true',help='Use immediate stable visual updates.')
    args=ap.parse_args()
    if args.export and args.export_motion:
        ap.error('Choose one export mode.')
    if (args.export or args.export_motion) and not args.demo:
        ap.error('Export requires --demo')
    if not args.demo and not args.project:
        ap.error('Choose --demo or --project PROJECT_ID')
    args.store=args.store or Path('artifacts/native_demo' if args.demo else 'artifacts/studio')
    if args.export or args.export_motion:
        os.environ['QT_QPA_PLATFORM']='offscreen'
    QApplication,VisualSurface,QTimer=qt_types()
    app=QApplication([])
    surface=VisualSurface(animate=bool(args.export_motion) or not args.reduced_motion and not args.export)
    if args.demo:
        args.store.mkdir(parents=True,exist_ok=True)
        writer_lock=(args.store/'.server.lock').open('a')
        try:
            fcntl.flock(writer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('This store has another writer. Use a separate native demo directory.') from None
        store,studio,pid=demo_engine(args.store)
    else:
        from .engine import Store
        store,studio,pid=Store(args.store),None,args.project
    output=VisualOutput()
    if args.export_motion:
        from .native_motion import export_motion
        export_motion(app,surface,store,studio,pid,args.export_motion,reduced=args.reduced_motion)
        surface.close();return
    if args.export:
        args.export.mkdir(parents=True,exist_ok=True)
        surface.show()
        cases=[('flow-overview',None),('flow-high','At the high setting.'),
               ('power-overview','Now electrical power consumption.'),('power-low','At the low setting.')]
        rows=[]
        for i,(name,utterance) in enumerate(cases):
            begun=time.perf_counter()
            p=store.read(pid)
            if utterance:
                p=studio.transcript(pid,utterance,i,generation=p['live']['generation'])
            output.accept(p);surface.present(output,begun);app.processEvents()
            path=args.export/(name+'.png')
            surface.grab().save(str(path))
            rows.append({'name':name,'utterance':utterance,'scene_id':output.scene['id'],
                         'attention':output.attention,'engine_decision':p['live']['decision'],
                         'paint':surface.samples[-1]})
        report={'schema':'live_presenter.native_output_probe.v1','browser_used':False,'asr_used':False,
            'window_visible':False,'physical_projector_used':False,'size':[surface.width(),surface.height()],
            'timing_scope':'Terminal-style text through the local engine to a Qt offscreen paint callback; excludes ASR, network retrieval and physical display.',
            'cases':rows}
        (args.export/'report.json').write_text(json.dumps(report,indent=2))
        surface.close();print('Native chart sequence exported to '+str(args.export));return
    incoming=queue.Queue()
    if studio:
        def listen():
            for line in sys.stdin:
                incoming.put(line.strip())
        threading.Thread(target=listen,daemon=True).start()
        print('Visual output is fullscreen. Type explanations here; /hold, /resume, /stop, /start. Escape closes the visual window.',flush=True)
    else:
        print('Read-only native output attached. Escape closes the visual window.',flush=True)
    previous_mtime=None
    seq=0
    def tick():
        nonlocal previous_mtime,seq
        try:
            while studio and not incoming.empty():
                line=incoming.get_nowait()
                if not line:continue
                if line in {'/hold','/resume','/stop','/start'}:
                    studio.control(pid,line[1:])
                else:
                    p=store.read(pid);seq=max(seq,p['live']['last_seq']+1)
                    studio.transcript(pid,line,seq,generation=p['live']['generation']);seq+=1
            stamp=store.path(pid).stat().st_mtime_ns
            if stamp==previous_mtime:return
            previous_mtime=stamp
            received=time.perf_counter()
            if output.accept(store.read(pid)):
                surface.present(output,received)
        except (ValueError,OSError,KeyError) as e:
            # Generic status belongs backstage; no error panel covers the visual.
            print('Native output retained: '+type(e).__name__,file=sys.stderr,flush=True)
    timer=QTimer();timer.timeout.connect(tick);timer.start(20)
    tick();surface.showFullScreen()
    sys.exit(app.exec())


if __name__=='__main__':
    main()
