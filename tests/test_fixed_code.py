"""
Test that the fixes work correctly.
"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_calendar import load_state, save_state, CalendarSyncTransaction, get_event_end, format_datetime_for_ical
from tests.mock_caldav import MockCalendar
from icalendar import Calendar as iCalendar


@pytest.fixture
def temp_state_file(tmp_path):
    state_file = tmp_path / "state.json"
    return str(state_file)


def test_FIXED_deletion_detection_now_works(temp_state_file):
    """
    Test that the fixed code correctly handles deletions using data=None marker.
    """

    work_cal = MockCalendar("Work")
    family_cal = MockCalendar("Family")

    import sync_calendar
    original_state_file = sync_calendar.STATE_FILE
    sync_calendar.STATE_FILE = temp_state_file

    try:
        # Step 1: Create event-1 and sync it
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Event 1
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

        # Simulate sync using FIXED code
        state = load_state()
        synced_events = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        for event in synced_events:
            # Check for deletion marker
            if event.data is None:
                work_uid = event._uid if hasattr(event, '_uid') and event._uid else None
                if work_uid and work_uid in state["event_map"]:
                    family_uid = state["event_map"][work_uid]
                    transaction.plan_delete(work_uid, family_uid)
                continue

            # Normal processing
            if event.data:
                cal = iCalendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    transp = component.get('TRANSP', 'OPAQUE')

                    if transp == 'OPAQUE':
                        dtstart = component['DTSTART']
                        dtend = get_event_end(component)

                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Busy Sync//EN
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

                        if work_uid in state["event_map"]:
                            family_uid = state["event_map"][work_uid]
                            transaction.plan_update(work_uid, family_uid, family_event_data)
                        else:
                            transaction.plan_create(work_uid, family_event_data)

        transaction.execute()
        state["sync_token"] = synced_events.sync_token
        save_state(state)

        assert "event-1-family" in family_cal._events
        print("✓ Step 1: event-1 created in family calendar")

        # Step 2: Create event-2 (event-1 unchanged)
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-2
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:Event 2
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

        # Sync again using FIXED code
        state = load_state()
        synced_events = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        for event in synced_events:
            # Check for deletion marker
            if event.data is None:
                work_uid = event._uid if hasattr(event, '_uid') and event._uid else None
                if work_uid and work_uid in state["event_map"]:
                    family_uid = state["event_map"][work_uid]
                    transaction.plan_delete(work_uid, family_uid)
                continue

            # Normal processing
            if event.data:
                cal = iCalendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    transp = component.get('TRANSP', 'OPAQUE')

                    if transp == 'OPAQUE':
                        dtstart = component['DTSTART']
                        dtend = get_event_end(component)

                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Busy Sync//EN
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

                        if work_uid in state["event_map"]:
                            family_uid = state["event_map"][work_uid]
                            transaction.plan_update(work_uid, family_uid, family_event_data)
                        else:
                            transaction.plan_create(work_uid, family_event_data)

        transaction.execute()
        state["sync_token"] = synced_events.sync_token
        save_state(state)

        # Check results with FIXED code
        print(f"\nResults with FIXED code:")
        print(f"   Work calendar: {list(work_cal._events.keys())}")
        print(f"   Family calendar: {list(family_cal._events.keys())}")

        # Both events should still exist!
        assert "event-1" in work_cal._events, "event-1 should still be in work calendar"
        assert "event-2" in work_cal._events, "event-2 should be in work calendar"
        assert "event-1-family" in family_cal._events, "event-1-family should NOT be deleted!"
        assert "event-2-family" in family_cal._events, "event-2-family should be created"

        print("\n✓ FIX VERIFIED: event-1-family was correctly preserved!")

    finally:
        sync_calendar.STATE_FILE = original_state_file


def test_FIXED_actual_deletion_works(temp_state_file):
    """
    Test that actual deletions (data=None) are handled correctly.
    """

    work_cal = MockCalendar("Work")
    family_cal = MockCalendar("Family")

    import sync_calendar
    original_state_file = sync_calendar.STATE_FILE
    sync_calendar.STATE_FILE = temp_state_file

    try:
        # Create and sync event-1
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Event 1
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        # Initial sync
        state = load_state()
        synced = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        for event in synced:
            if event.data is None:
                continue
            if event.data:
                cal = iCalendar.from_ical(event.data)
                for comp in cal.walk('VEVENT'):
                    uid = str(comp.get('UID'))
                    transp = comp.get('TRANSP', 'OPAQUE')
                    if transp == 'OPAQUE':
                        data = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{uid}-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR"""
                        transaction.plan_create(uid, data)

        transaction.execute()
        state["sync_token"] = synced.sync_token
        save_state(state)

        assert "event-1-family" in family_cal._events
        print("✓ Event-1 created in family calendar")

        # Delete event-1 from work calendar
        work_event = work_cal.event_by_uid("event-1")
        work_event.delete()

        # Sync - should detect deletion via data=None
        state = load_state()
        synced = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        for event in synced:
            if event.data is None:
                # DELETION MARKER
                work_uid = event._uid if hasattr(event, '_uid') and event._uid else None
                if work_uid and work_uid in state["event_map"]:
                    family_uid = state["event_map"][work_uid]
                    transaction.plan_delete(work_uid, family_uid)
                    print(f"✓ Detected deletion of {work_uid} via data=None")

        transaction.execute()
        state["sync_token"] = synced.sync_token
        save_state(state)

        # Verify deletion worked
        assert "event-1" not in work_cal._events
        assert "event-1-family" not in family_cal._events
        print("✓ Deletion handled correctly")

    finally:
        sync_calendar.STATE_FILE = original_state_file


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
