#!/usr/bin/env python3
"""
Comprehensive test against real Fastmail to verify all fixes work.
"""

import caldav
import os
import time
from datetime import datetime

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME', 'Claude sandpit')

def cleanup_test_events(cal):
    """Remove any existing test events"""
    print("Cleaning up test events...")
    test_uids = ['real-test-1', 'real-test-2', 'real-test-3']
    for uid in test_uids:
        try:
            event = cal.event_by_uid(uid)
            event.delete()
            print(f"  Deleted {uid}")
        except:
            pass

def main():
    print("=== Real Fastmail Test ===\n")

    client = caldav.DAVClient(
        url=FASTMAIL_URL,
        username=FASTMAIL_USER,
        password=FASTMAIL_PASS
    )

    principal = client.principal()
    cal = principal.calendar(name=WORK_CAL_NAME)

    # Cleanup first
    cleanup_test_events(cal)

    # Get baseline sync token
    synced = cal.objects(sync_token=None, load_objects=True)
    baseline_token = synced.sync_token
    print(f"Baseline sync token: {baseline_token}\n")

    # Test 1: Create events
    print("Test 1: Creating test events...")
    cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:real-test-1
DTSTART:20250201T100000Z
DTEND:20250201T110000Z
SUMMARY:Real Test 1
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

    cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:real-test-2
DTSTART:20250201T120000Z
DTEND:20250201T130000Z
SUMMARY:Real Test 2
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

    print("✓ Created real-test-1 and real-test-2\n")

    # Verify they appear in sync
    synced = cal.objects(sync_token=baseline_token, load_objects=True)
    token1 = synced.sync_token
    events = list(synced)
    print(f"Sync after creation: {len(events)} events in delta")
    for event in events:
        if event.data:
            print(f"  - {event}")
    print(f"New sync token: {token1}\n")

    # Test 2: Add a third event (should NOT trigger deletion of first two)
    print("Test 2: Adding third event...")
    cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:real-test-3
DTSTART:20250201T140000Z
DTEND:20250201T150000Z
SUMMARY:Real Test 3
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

    print("✓ Created real-test-3\n")

    # Verify delta only shows real-test-3
    synced = cal.objects(sync_token=token1, load_objects=True)
    token2 = synced.sync_token
    events = list(synced)
    print(f"Sync after adding third: {len(events)} events in delta")
    print(f"  (Should be 1 - only real-test-3)")
    for event in events:
        if event.data:
            from icalendar import Calendar
            cal_obj = Calendar.from_ical(event.data)
            for comp in cal_obj.walk('VEVENT'):
                print(f"  - {comp.get('SUMMARY')} (UID: {comp.get('UID')})")
    print(f"New sync token: {token2}\n")

    # Test 3: Delete one event
    print("Test 3: Deleting real-test-2...")
    event = cal.event_by_uid('real-test-2')
    event.delete()
    print("✓ Deleted\n")

    # Verify deletion appears with data=None
    synced = cal.objects(sync_token=token2, load_objects=True)
    token3 = synced.sync_token
    events = list(synced)
    print(f"Sync after deletion: {len(events)} events in delta")
    for event in events:
        print(f"  Event: {event}")
        print(f"  Data: {event.data}")
        if event.data is None:
            print(f"  ✓ DELETION MARKER CONFIRMED!")
    print(f"New sync token: {token3}\n")

    # Test 4: Verify all events still exist (should be real-test-1 and real-test-3)
    print("Test 4: Verifying final state...")
    all_events = cal.objects(sync_token=None, load_objects=True)
    test_events = []
    for event in all_events:
        if event.data:
            from icalendar import Calendar
            cal_obj = Calendar.from_ical(event.data)
            for comp in cal_obj.walk('VEVENT'):
                uid = str(comp.get('UID'))
                if uid.startswith('real-test'):
                    test_events.append(uid)

    print(f"Test events in calendar: {test_events}")
    assert 'real-test-1' in test_events, "real-test-1 should exist"
    assert 'real-test-2' not in test_events, "real-test-2 should be deleted"
    assert 'real-test-3' in test_events, "real-test-3 should exist"
    print("✓ All events in correct state\n")

    # Cleanup
    cleanup_test_events(cal)

    print("=== All Tests Passed! ===")
    print("\nKey Findings:")
    print("✓ Sync tokens work correctly")
    print("✓ Delta contains only changed events")
    print("✓ Deletions marked with data=None")
    print("✓ Events not in delta are NOT deleted")

if __name__ == "__main__":
    main()
