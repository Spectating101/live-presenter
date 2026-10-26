"""Approved visual output independent of HTML, pages and operator controls."""
import copy

from .engine import Conflict, Studio


VISUAL_KINDS = {'chart', 'image', 'annotated_image', 'metric'}


def axis_label(column):
    # Only format unit suffixes actually present in the supplied column name.
    for suffix, unit in [('L_min','L/min'),('m_s','m/s'),('ms','ms'),('kg','kg'),('W','W')]:
        if column.endswith('_'+suffix):
            return column[:-len(suffix)-1].replace('_',' ')+' ('+unit+')'
    return column.replace('_',' ')


class VisualOutput:
    """Read-only projection of an approved running explanation.

    Unsupported prose templates hold the last valid visual in this package.
    Stop, a return to the speaker or revoked/changed approval clears the output. No draft can leak
    through the native path just because it can draw an image.
    """
    def __init__(self):
        self.package_hash = None
        self.scene = None
        self.attention = None
        self.reason = 'blank'

    def accept(self, project):
        previous = (self.package_hash, (self.scene or {}).get('id'), self.attention)
        try:
            package = Studio.package(project)
        except Conflict:
            self.package_hash = None
            self.scene = self.attention = None
            self.reason = 'No current approval; output cleared.'
        else:
            digest = project['approval']['package_hash']
            if digest != self.package_hash:
                self.scene = self.attention = None
            self.package_hash = digest
            live = project['live']
            if not live['active']:
                self.scene = self.attention = None
                self.reason = 'Explanation stopped; output cleared.'
            else:
                scene = (live.get('research_scene') if live.get('research_enabled') else None) or next(
                    (s for s in package['scenes'] if s['id'] == live['current_scene_id']), None)
                if scene is None and live['current_scene_id'] is None:
                    self.scene = self.attention = None
                    self.reason = 'Attention returned to the speaker; output cleared.'
                elif scene and scene['kind'] in VISUAL_KINDS:
                    self.scene = copy.deepcopy(scene)
                    focus = live.get('attention')
                    self.attention = copy.deepcopy(focus) if focus and focus['scene_id'] == scene['id'] else None
                    self.reason = 'Visual updated.'
                else:
                    self.reason = 'No supported illustration for this request; retaining the last visual.'
        return previous != (self.package_hash, (self.scene or {}).get('id'), self.attention)


def demo_engine(root, *, brief=None):
    """A sourced numeric demonstration, explicitly not an ASR benchmark."""
    from .engine import Store
    from .materials import ingest
    from .planning import validate_plan
    source = ingest('illustrative_measurements.csv',
        b'Setting,Flow_L_min,Electrical_power_W\nLow,12,90\nMedium,18,145\nHigh,24,230\n')
    ref = {'unit_id':source['units'][0]['id'], 'quote':source['units'][0]['text']}
    raw = {'title':'Illustrative operating measurements', 'audience':'Engineering students',
           'takeaway':'Higher settings increase measured flow and electrical power; heat removal was not measured.',
           'understanding':'Display the actual measurements as the quantity under discussion changes.',
           'concepts':[]}
    for title, aliases, column, question in [
        ('Flow rate', ['flow rate','litres per minute','pumping flow'], 'Flow_L_min', 'How much liquid circulates?'),
        ('Electrical power', ['electrical power','power consumption','watts consumed'], 'Electrical_power_W', 'How much electrical power is consumed?')]:
        raw['concepts'].append({'title':title,'summary':title+' in the supplied illustrative measurements.',
            'aliases':aliases,'source_refs':[ref], 'explanation':{'goal':'quantity','question':question,
            'rationale':'Show the measured quantities on a common zero-based scale.'},
            'visuals':[{'kind':'chart','dataset_id':source['id'],'x':'Setting','y':column}]})
    class Planner:
        def prepare(self, project):
            return validate_plan(raw, project)
    store = Store(root)
    studio = Studio(store, planner=Planner(), dwell_s=0)
    p = store.create(title=raw['title'], brief=brief or raw['takeaway'], audience=raw['audience'], sources=[source])
    p = studio.prepare(p['id'], background=False)
    p = studio.approve(p['id'], p['revision'], True)
    studio.control(p['id'], 'start')
    return store, studio, p['id']
