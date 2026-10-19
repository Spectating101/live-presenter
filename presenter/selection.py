"""Pick an approved view within a supported idea; explicit presenter defaults win."""


def choose_scene(package, concept_id, preferred=None, advised=None):
    scenes = [s for s in package['scenes'] if s['concept_id'] == concept_id]
    if not scenes:
        return None
    if preferred:
        match = next((s for s in scenes if s['kind'] == preferred), None)
        if match:
            return match
    concept = next(c for c in package['concepts'] if c['id'] == concept_id)
    default = next((s for s in scenes if s['id'] == concept.get('default_scene_id')), None)
    if default:
        return default
    # A classifier saying "evidence" is not a request to replace the current
    # explanation with quotation cards. Explicit requests use preferred above.
    return next((s for s in scenes if advised != 'evidence' and s['kind'] == advised), scenes[0])
