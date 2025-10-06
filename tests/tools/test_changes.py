#!/usr/bin/env python3
"""
Test event modifications and deletions to understand sync token behavior.
"""

import caldav
import os
import json

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
    print("=== Testing Event Changes ===\n")

    client = caldav.DAVClient(
        url=FASTMAIL_URL,
        username=FASTMAIL_USER,
        password=FASTMAIL_PASS
    )

    principal = client.principal()
    cal = principal.calendar(name=WORK_CAL_NAME)

    # Get current sync token
    synced = cal.objects(sync_token=None, load_objects=True)
    initial_token = synced.sync_token
    print(f"Initial sync token: {initial_token}")
    print(f"Events in calendar: {len(list(synced))}\n")

    # Test 1: Delete an event
    print("Test 1: Deleting event 'test-basic-timed-transparent'...")
    try:
        event = cal.event_by_uid('test-basic-timed-transparent')
        event.delete()
        print("✓ Event deleted")
    except Exception as e:
        print(f"✗ Failed to delete: {e}")

    # Check what sync shows after deletion
    synced = cal.objects(sync_token=initial_token, load_objects=True)
    new_token = synced.sync_token
    changes = list(synced)
    print(f"Sync token after delete: {new_token}")
    print(f"Changes returned: {len(changes)}")

    result = {
        'test': 'deletion',
        'old_token': initial_token,
        'new_token': new_token,
        'changes_count': len(changes),
        'changes': []
    }

    for change in changes:
        print(f"  Change: {change}")
        if change.data is None:
            print(f"  Data: None (DELETED EVENT)")
            result['changes'].append({
                'url': str(change.url),
                'data': None,
                'status': 'DELETED'
            })
        else:
            print(f"  Data: {change.data[:200]}")
            result['changes'].append({
                'url': str(change.url),
                'data': change.data.decode() if isinstance(change.data, bytes) else change.data,
                'status': 'MODIFIED'
            })

    save_results('03_deletion_test.json', result)

    # Test 2: Modify an event (change TRANSP)
    print("\nTest 2: Changing event from OPAQUE to TRANSPARENT...")
    try:
        event = cal.event_by_uid('test-no-transp')
        # Modify to add TRANSPARENT
        modified_data = event.data.decode().replace('END:VEVENT', 'TRANSP:TRANSPARENT\nEND:VEVENT')
        event.data = modified_data
        event.save()
        print("✓ Event modified (added TRANSP:TRANSPARENT)")
    except Exception as e:
        print(f"✗ Failed to modify: {e}")

    # Check sync after modification
    synced = cal.objects(sync_token=new_token, load_objects=True)
    mod_token = synced.sync_token
    changes = list(synced)
    print(f"Sync token after modify: {mod_token}")
    print(f"Changes returned: {len(changes)}")

    result2 = {
        'test': 'modification',
        'old_token': new_token,
        'new_token': mod_token,
        'changes_count': len(changes),
        'changes': []
    }

    for change in changes:
        from icalendar import Calendar
        cal_obj = Calendar.from_ical(change.data)
        for comp in cal_obj.walk('VEVENT'):
            print(f"  Modified event: {comp.get('SUMMARY')}")
            print(f"    TRANSP: {comp.get('TRANSP', 'NOT SET')}")
            result2['changes'].append({
                'uid': str(comp.get('UID')),
                'summary': str(comp.get('SUMMARY')),
                'transp': str(comp.get('TRANSP', 'NOT SET'))
            })

    save_results('04_modification_test.json', result2)

    print("\n✓ Change testing complete!")

if __name__ == "__main__":
    main()
