"""TEST ONLY - a small break-area style domain that exercises every merge rule of the sync engine
(counters, max / rank / follow resolvers, parent-child rows, deletes and restores).

The engine (journal, replica, sync) is domain-free; its tests need entities with counters and resolvers, which the
trip domain does not use. `register()` adds these entities to `store` inside the test process only. Nothing here is
shipped: the installer and the server never import this file.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import store  # noqa: E402
from store import B, I, J, R, T  # noqa: E402,F401

LEGACY = {
        'itemTypes': ('item_types', 'Item Types', [
        ('name', 'name', T, 'Name'), ('short', 'short_name', T, 'Singular'), ('icon', 'icon', T, 'Icon')]),
    'areas': ('areas', 'Break Areas', [
        ('name', 'name', T, 'Break Area'), ('location', 'location', T, 'Location'), ('building', 'building', T, 'Building'),
        ('floor', 'floor', T, 'Floor'), ('startDate', 'start_date', T, 'Start Date'), ('size', 'size_m2', R, 'Area Size (m2)'),
        ('capacity', 'capacity', I, 'Capacity'), ('responsible', 'responsible', T, 'Responsible'), ('status', 'status', T, 'Status'),
        ('active', 'active', B, 'Operational'), ('description', 'description', T, 'Description'),
        ('lastInspection', 'last_inspection', T, 'Last Inspection'), ('nextInspection', 'next_inspection', T, 'Next Inspection'),
        ('inspectedBy', 'inspected_by', T, 'Inspected By')]),
    'inventory': ('inventory', 'Inventory', [
        ('areaId', 'area_id', T, 'Area ID'), ('item', 'item', T, 'Item'), ('qty', 'qty', I, 'Quantity'),
        ('condition', 'condition', T, 'Condition'), ('note', 'note', T, 'Notes')]),
    'surveys': ('surveys', 'Satisfaction Surveys', [
        ('areaId', 'area_id', T, 'Area ID'), ('month', 'month', T, 'Month'), ('department', 'department', T, 'Department'),
        ('percentage', 'percentage', R, 'Satisfaction %'), ('respondents', 'respondents', I, 'Respondents'),
        ('notes', 'notes', T, 'Notes'), ('by', 'entered_by', T, 'Entered By')]),
    'photos': ('photos', 'Photos', [
        ('areaId', 'area_id', T, 'Area ID'), ('caption', 'caption', T, 'Caption'), ('category', 'category', T, 'Category'),
        ('date', 'date', T, 'Date'), ('main', 'is_main', B, 'Main Photo'), ('src', 'src', T, 'File'), ('thumb', 'thumb', T, 'Thumbnail'),
        ('variant', 'variant', T, 'Placeholder'), ('seed', 'seed', T, 'Placeholder Seed')]),
    'docs': ('documents', 'Documents', [
        ('areaId', 'area_id', T, 'Area ID'), ('name', 'name', T, 'File Name'), ('caption', 'caption', T, 'Title'),
        ('size', 'size_bytes', I, 'Size (bytes)'), ('type', 'mime_type', T, 'Type'), ('date', 'date', T, 'Date'), ('src', 'src', T, 'File')]),
    'issues': ('issues', 'Issues', [
        ('areaId', 'area_id', T, 'Area ID'), ('date', 'date', T, 'Reported'), ('title', 'title', T, 'Issue'), ('item', 'item', T, 'Item'),
        ('priority', 'priority', T, 'Priority'), ('status', 'status', T, 'Status'), ('closedDate', 'closed_date', T, 'Closed'),
        ('reportedBy', 'reported_by', T, 'Reported By'), ('details', 'details', T, 'Details')]),
    'issueLog': ('issue_log', 'Issue Follow-ups', [
        ('issueId', 'issue_id', T, 'Issue ID'), ('date', 'date', T, 'Date'), ('by', 'by_user', T, 'By'), ('text', 'text', T, 'Note')]),
    'maintenance': ('maintenance', 'Maintenance', [
        ('areaId', 'area_id', T, 'Area ID'), ('date', 'date', T, 'Planned Date'), ('item', 'item', T, 'Item'),
        ('assignedTo', 'assigned_to', T, 'Assigned To'), ('details', 'details', T, 'Work'), ('status', 'status', T, 'Status'),
        ('doneDate', 'done_date', T, 'Done Date'), ('notes', 'notes', T, 'Notes')]),
    'inspections': ('inspections', 'Inspections', [
        ('areaId', 'area_id', T, 'Area ID'), ('date', 'date', T, 'Date'), ('by', 'by_user', T, 'Inspected By'),
        ('result', 'result', T, 'Result'), ('notes', 'notes', T, 'Notes')]),
    'history': ('history', 'Transactions', [
        ('seq', 'seq', I, 'Seq'), ('areaId', 'area_id', T, 'Area ID'), ('date', 'date', T, 'Date'), ('item', 'item', T, 'Item'),
        ('action', 'action', T, 'Action'), ('prev', 'prev_qty', I, 'Previous Qty'), ('next', 'new_qty', I, 'New Qty'),
        ('details', 'details', T, 'Details'), ('by', 'by_user', T, 'Updated By')]),
}
AREA_CHILDREN = ['inventory', 'photos', 'docs', 'issues', 'maintenance', 'inspections', 'surveys']

LEGACY_COUNTERS = {'inventory': {'qty'}}
LEGACY_RESOLVERS = {
    'areas': {'lastInspection': 'max', 'nextInspection': 'max', 'inspectedBy': 'follow:lastInspection'},
    'maintenance': {'status': 'rank:Scheduled,In Progress,Done', 'doneDate': 'follow:status', 'notes': 'follow:status'},
}
AREA_CHILDREN = ['inventory', 'photos', 'docs', 'issues', 'maintenance', 'inspections', 'surveys']


def register():
    for e, (t, title, f) in LEGACY.items():
        if e in store.ENTITIES:
            continue
        store.ENTITIES[e] = (t, title, f)
        store.COUNTERS[e] = LEGACY_COUNTERS.get(e, set())
        store.RESOLVERS[e] = LEGACY_RESOLVERS.get(e, {})
        store.SPECS[e] = {'table': t, 'fields': [(js, col, kind) for js, col, kind, _ in f], 'counters': store.COUNTERS[e],
                          'resolvers': store.RESOLVERS[e]}
        store.REPLICATED.add(e)


def nested_state(st):
    """The shape the old tests expect: break areas with their children, built from the raw rows of a Store."""
    with st.lock:
        rows = {e: [st._row_js(e, r) for r in st.conn.execute(f'SELECT * FROM {t} WHERE deleted=0 ORDER BY rowid')]
                for e, (t, _, _) in store.ENTITIES.items() if e in LEGACY}
    areas = sorted(rows['areas'], key=lambda a: (a.get('name') or '').lower())
    by_id = {}
    for a in areas:
        for c in AREA_CHILDREN:
            a[c] = []
        by_id[a['id']] = a
    logs = {}
    for lg in rows['issueLog']:
        logs.setdefault(lg.pop('issueId', None), []).append(lg)
    for c in AREA_CHILDREN:
        for r in rows[c]:
            a = by_id.get(r.pop('areaId', None))
            if a is None:
                continue
            if c == 'issues':
                r['log'] = logs.get(r['id'], [])
            a[c].append(r)
    return {'itemTypes': rows['itemTypes'], 'areas': areas, 'history': [h for h in rows['history'] if h.get('areaId') in by_id]}
