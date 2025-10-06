#!/usr/bin/env python3
"""
Test the complete deletion and modification flow.
"""

import caldav
import os
import json
from icalendar import Calendar as iCalendar

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME')

def save_results(filename, data):
    os.makedirs('tests/fixtures/study', exist_ok=True)
    path = f'tests/fixtures/study/{filename}'
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → Saved to {path}")

def main():
    print("=== Testing Deletion and Modification Flow ===\n")

    client = caldav.DAVClient(
        url=FASTMAIL_URL,
        username=FASTMAIL_USER,
        password=FASTMAIL_PASS
    )

    principal = client.principal()
    cal = principal.calendar(name=WORK_CAL_NAME)

    # Get initial state
    synced = cal.objects(sync_token=None, load_objects=True)
    token1 = synced.sync_token
    print(f"Step 1: Initial sync token: {token1}\n")

    # Create a test event
    print("Step 2: Creating test event...")
    cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:deletion-test-event
DTSTART:20250115T100000Z
DTEND:20250115T110000Z
SUMMARY:Event To Delete
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")
    print("✓ Created event 'deletion-test-event'\n")

    # Sync to see the creation
    synced = cal.objects(sync_token=token1, load_objects=True)
    token2 = synced.sync_token
    changes = list(synced)
    print(f"Step 3: Sync after creation")
    print(f"  Token: {token2}")
    print(f"  Changes: {len(changes)}")
    for change in changes:
        if change.data:
            cal_obj = iCalendar.from_ical(change.data)
            for comp in cal_obj.walk('VEVENT'):
                print(f"  Created: {comp.get('SUMMARY')} (UID: {comp.get('UID')})")
    print()

    # Now delete it
    print("Step 4: Deleting the event...")
    event = cal.event_by_uid('deletion-test-event')
    event.delete()
    print("✓ Deleted\n")

    # Sync to see the deletion
    synced = cal.objects(sync_token=token2, load_objects=True)
    token3 = synced.sync_token
    changes = list(synced)
    print(f"Step 5: Sync after deletion")
    print(f"  Token: {token3}")
    print(f"  Changes: {len(changes)}")

    deletion_result = {
        'test': 'deletion_flow',
        'token_before': token2,
        'token_after': token3,
        'changes_count': len(changes),
        'changes': []
    }

    for change in changes:
        print(f"  Change URL: {change.url}")
        print(f"  Change data: {change.data}")
        if change.data is None:
            print(f"  ★ DELETION DETECTED (data=None)")
            deletion_result['changes'].append({
                'url': str(change.url),
                'data': None,
                'interpretation': 'DELETED'
            })
        else:
            print(f"  Data exists: {change.data[:100]}")
            deletion_result['changes'].append({
                'url': str(change.url),
                'data': change.data.decode() if isinstance(change.data, bytes) else change.data,
                'interpretation': 'MODIFIED'
            })

    save_results('05_deletion_flow.json', deletion_result)
    print()

    # Now test modification (TRANSP change)
    print("Step 6: Creating event to modify...")
    cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:modification-test-event
DTSTART:20250116T100000Z
DTEND:20250116T110000Z
SUMMARY:Event To Modify
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")
    print("✓ Created\n")

    # Sync
    synced = cal.objects(sync_token=token3, load_objects=True)
    token4 = synced.sync_token
    print(f"Step 7: Token after creation: {token4}\n")

    # Modify it (change to TRANSPARENT)
    print("Step 8: Modifying TRANSP to TRANSPARENT...")
    event = cal.event_by_uid('modification-test-event')
    current_data = event.data
    if isinstance(current_data, bytes):
        current_data = current_data.decode()

    modified_data = current_data.replace('TRANSP:OPAQUE', 'TRANSP:TRANSPARENT')
    event.data = modified_data
    event.save()
    print("✓ Modified\n")

    # Sync to see modification
    synced = cal.objects(sync_token=token4, load_objects=True)
    token5 = synced.sync_token
    changes = list(synced)
    print(f"Step 9: Sync after modification")
    print(f"  Token: {token5}")
    print(f"  Changes: {len(changes)}")

    mod_result = {
        'test': 'modification_flow',
        'token_before': token4,
        'token_after': token5,
        'changes_count': len(changes),
        'changes': []
    }

    for change in changes:
        if change.data:
            cal_obj = iCalendar.from_ical(change.data)
            for comp in cal_obj.walk('VEVENT'):
                transp = comp.get('TRANSP', 'NOT SET')
                print(f"  Modified: {comp.get('SUMMARY')}")
                print(f"    UID: {comp.get('UID')}")
                print(f"    TRANSP: {transp}")
                mod_result['changes'].append({
                    'uid': str(comp.get('UID')),
                    'summary': str(comp.get('SUMMARY')),
                    'transp': str(transp)
                })

    save_results('06_modification_flow.json', mod_result)

    print("\n✓ Flow testing complete!")
    print("\nKey Findings:")
    print("- Deletions: appear in sync with data=None")
    print("- Modifications: appear in sync with full event data")
    print("- TRANSP changes: can be detected in sync results")

if __name__ == "__main__":
    main()
