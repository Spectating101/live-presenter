"""Optional RealtimeSTT stabilization for the existing causal PCM worker."""
import array
import math
import sys

from .vendor.realtimestt.text_stabilizer import RealtimeTextObservation, RealtimeTextStabilizer, RealtimeTextStabilizationConfig


class StableTranscript:
    """Stable text drives decisions; unstable recognition remains diagnostic.

    A simple acoustic gap starts a new segment. This is not a full VAD model;
    it is an experimental adapter evaluated separately from the default path.
    """
    def __init__(self):
        # Four confirmations work at high update frequency, but a 1Hz rolling
        # window loses its left edge before four observations can accumulate.
        self.model=RealtimeTextStabilizer(RealtimeTextStabilizationConfig(
            space_min_confirmations=2,punctuation_min_confirmations=2))
        self.segment=0;self.last_sound=-100;self.started=False;self.last_emitted=''

    def observe(self,text,seq,pcm,received,recognized):
        samples=array.array('h',pcm[-32000:])
        if sys.byteorder!='little':samples.byteswap()
        rms=math.sqrt(sum(n*n for n in samples)/max(1,len(samples)))
        sound=rms>=180
        if not self.started or sound and seq-self.last_sound>=3:
            self.segment+=1;self.model.reset('pcm',self.segment);self.started=True;self.last_emitted=''
        if sound:self.last_sound=seq
        event=self.model.observe(RealtimeTextObservation(
            recording_id='pcm',segment_id=self.segment,sequence=seq+1,raw_text=text,
            audio_start_sample=max(0,(seq-3)*16000),audio_end_sample_exclusive=(seq+1)*16000,
            sample_rate=16000,created_at_monotonic=received,completed_at_monotonic=recognized))
        changed=event.stable_text!=self.last_emitted and bool(event.stable_text.strip())
        if changed:self.last_emitted=event.stable_text
        return (event.stable_text if changed else ''),{
            'provider':'RealtimeSTT vendored MIT stabilizer','segment':self.segment,
            'stable_text':event.stable_text[:600],'unstable_text':event.unstable_text[:600],
            'accepted':event.accepted,'commit_reason':event.commit_reason,
            'has_new_stable_text':event.has_new_stable_text,'acoustic_rms':round(rms,1)}
