"""
Integration tests using direct function calls instead of mocking.
"""

import pytest
import os
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_calendar import (
    get_event_end,
    format_datetime_for_ical,
    CalendarSyncTransaction,
    load_state,
    save_state
)
from tests.mock_caldav import MockCalendar
from icalendar import Calendar as iCalendar


@pytest.fixture
def temp_state_file(tmp_path):
    state_file = tmp_path / "state.json"
    return str(state_file)


@pytest.fixture
def mock_calendars():
    work_cal = MockCalendar("Work")
    family_cal = MockCalendar("Family")
    return work_cal, family_cal


def test_transaction_create_event(mock_calendars, temp_state_file):
    """Test creating an event through transaction"""
    work_cal, family_cal = mock_calendars

    state = {"sync_token": None, "event_map": {}}
    transaction = CalendarSyncTransaction(work_cal, family_cal, state)

    event_data = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Busy Sync//EN
BEGIN:VEVENT
UID:test-event-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

    transaction.plan_create("test-event", event_data)
    transaction.execute()

    # Verify event created
    assert "test-event-family" in family_cal._events
    assert "test-event" in state["event_map"]
    assert state["event_map"]["test-event"] == "test-event-family"


def test_transaction_update_event(mock_calendars, temp_state_file):
    """Test successfully updating an existing event through transaction"""
    work_cal, family_cal = mock_calendars

    # Pre-create an event in family calendar
    family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Old Summary
END:VEVENT
END:VCALENDAR""")

    state = {"sync_token": None, "event_map": {"event-1": "event-1-family"}}
    transaction = CalendarSyncTransaction(work_cal, family_cal, state)

    # Plan update with new data
    new_event_data = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:New Summary
END:VEVENT
END:VCALENDAR"""

    transaction.plan_update("event-1", "event-1-family", new_event_data)
    transaction.execute()

    # Verify update happened
    assert "event-1-family" in family_cal._events
    event = family_cal.event_by_uid("event-1-family")
    assert b"New Summary" in event.data


def test_transaction_delete_event(mock_calendars, temp_state_file):
    """Test deleting an event through transaction"""
    work_cal, family_cal = mock_calendars

    # Pre-create an event in family calendar
    family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:to-delete-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:To Delete
END:VEVENT
END:VCALENDAR""")

    state = {"sync_token": None, "event_map": {"to-delete": "to-delete-family"}}
    transaction = CalendarSyncTransaction(work_cal, family_cal, state)

    transaction.plan_delete("to-delete", "to-delete-family")
    transaction.execute()

    # Verify event deleted
    assert "to-delete-family" not in family_cal._events
    assert "to-delete" not in state["event_map"]


def test_sync_token_behavior(mock_calendars):
    """Test that sync tokens work correctly"""
    work_cal, family_cal = mock_calendars

    # Initial sync (sync_token=None)
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

    synced = work_cal.objects(sync_token=None, load_objects=True)
    token1 = synced.sync_token
    events = list(synced)

    assert len(events) == 1
    assert events[0].uid == "event-1"

    # Sync again with same token - should return nothing
    synced = work_cal.objects(sync_token=token1, load_objects=True)
    events = list(synced)
    assert len(events) == 0

    # Add another event
    work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-2
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:Event 2
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

    # Sync with old token - should return only event-2
    synced = work_cal.objects(sync_token=token1, load_objects=True)
    token2 = synced.sync_token
    events = list(synced)

    assert len(events) == 1
    assert events[0].uid == "event-2"
    assert token2 != token1


def test_deletion_in_sync_results(mock_calendars):
    """Test that deletions appear in sync results with data=None"""
    work_cal, family_cal = mock_calendars

    # Create event
    work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:to-delete
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:To Delete
END:VEVENT
END:VCALENDAR""")

    synced = work_cal.objects(sync_token=None)
    token1 = synced.sync_token

    # Delete event
    event = work_cal.event_by_uid("to-delete")
    event.delete()

    # Sync should show deletion
    synced = work_cal.objects(sync_token=token1)
    events = list(synced)

    assert len(events) == 1
    assert events[0].data is None  # Deletion marker
    assert events[0]._uid == "to-delete"


def test_full_sync_workflow(mock_calendars, temp_state_file):
    """Test a complete sync workflow"""
    work_cal, family_cal = mock_calendars

    import sync_calendar
    original_state_file = sync_calendar.STATE_FILE
    sync_calendar.STATE_FILE = temp_state_file

    try:
        # Create initial event
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:work-event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Work Event 1
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

        # Manual sync process
        state = load_state()
        synced_events = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)
        current_work_uids = set()

        for event in synced_events:
            if event.data:
                cal = iCalendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    current_work_uids.add(work_uid)

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

        # Verify
        assert "work-event-1-family" in family_cal._events
        assert "work-event-1" in state["event_map"]

    finally:
        sync_calendar.STATE_FILE = original_state_file


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
