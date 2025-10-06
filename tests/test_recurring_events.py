"""
Tests for recurring event handling.

Recurring events use RRULE to define repetition patterns.
"""

import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_calendar import get_event_end, format_datetime_for_ical
from icalendar import Calendar as iCalendar
from datetime import datetime


class TestRecurringEventParsing:
    """Test that we can parse recurring events without errors"""

    def test_daily_recurring_event(self):
        """Daily recurring event with RRULE"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-daily
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Daily Standup
RRULE:FREQ=DAILY;COUNT=10
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        # Should be able to get end time
        end = get_event_end(event)
        assert end.to_ical() == b'20250107T110000Z'

        # Should have RRULE
        assert 'RRULE' in event
        rrule = event['RRULE']
        assert rrule['FREQ'][0] == 'DAILY'
        print(f"✓ Daily recurring event parsed: {rrule}")

    def test_weekly_recurring_event(self):
        """Weekly recurring event"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-weekly
DTSTART:20250107T140000Z
DTEND:20250107T150000Z
SUMMARY:Weekly Meeting
RRULE:FREQ=WEEKLY;BYDAY=TU;COUNT=8
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = get_event_end(event)
        assert end is not None

        assert 'RRULE' in event
        rrule = event['RRULE']
        assert rrule['FREQ'][0] == 'WEEKLY'
        assert rrule['BYDAY'][0] == 'TU'
        print(f"✓ Weekly recurring event parsed: {rrule}")

    def test_recurring_with_until(self):
        """Recurring event with UNTIL instead of COUNT"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-until
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Limited Event
RRULE:FREQ=DAILY;UNTIL=20250131T235959Z
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = get_event_end(event)
        assert end is not None

        assert 'RRULE' in event
        rrule = event['RRULE']
        assert 'UNTIL' in rrule
        print(f"✓ Recurring with UNTIL parsed: {rrule}")

    def test_recurring_all_day(self):
        """Recurring all-day event"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-allday
DTSTART;VALUE=DATE:20250107
DTEND;VALUE=DATE:20250108
SUMMARY:Daily Reminder
RRULE:FREQ=DAILY;COUNT=30
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = get_event_end(event)
        assert end.to_ical() == b'20250108'

        assert 'RRULE' in event
        print("✓ Recurring all-day event parsed")

    def test_recurring_with_exdate(self):
        """Recurring event with exception dates (EXDATE)"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-exdate
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Daily Except Holidays
RRULE:FREQ=DAILY;COUNT=20
EXDATE:20250110T100000Z,20250117T100000Z
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = get_event_end(event)
        assert end is not None

        assert 'RRULE' in event
        assert 'EXDATE' in event
        exdates = event['EXDATE']
        print(f"✓ Recurring with EXDATE parsed: {exdates}")


class TestRecurringEventSync:
    """Test syncing recurring events through the system"""

    def test_recurring_event_syncs_to_family_calendar(self):
        """A recurring event should sync like a normal event"""
        from tests.mock_caldav import MockCalendar
        from sync_calendar import CalendarSyncTransaction, load_state, save_state

        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Create recurring event in work calendar
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Daily Meeting
RRULE:FREQ=DAILY;COUNT=10
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""")

        # Simulate sync
        state = {"sync_token": None, "event_map": {}}
        synced = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        for event in synced:
            if event.data is None:
                continue

            cal = iCalendar.from_ical(event.data)
            for comp in cal.walk('VEVENT'):
                work_uid = str(comp.get('UID'))
                transp = comp.get('TRANSP', 'OPAQUE')

                if transp == 'OPAQUE':
                    dtstart = comp['DTSTART']
                    dtend = get_event_end(comp)

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

                    transaction.plan_create(work_uid, family_event_data)

        transaction.execute()

        # Verify created in family calendar
        assert "recurring-1-family" in family_cal._events
        print("✓ Recurring event synced to family calendar")

        # Verify the synced event is a simple busy block (RRULE stripped)
        family_event_ical = family_cal._events["recurring-1-family"]
        assert "RRULE" not in family_event_ical
        assert "SUMMARY:Busy" in family_event_ical
        print("✓ Synced event is simplified (no RRULE)")

    def test_recurring_event_modification_detected(self):
        """Modifying a recurring event should be detected"""
        from tests.mock_caldav import MockCalendar

        work_cal = MockCalendar("Work")

        # Create recurring event
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-2
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Original
RRULE:FREQ=DAILY;COUNT=5
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        synced = work_cal.objects(sync_token=None)
        token1 = synced.sync_token

        # Modify the recurring event
        event = work_cal.event_by_uid("recurring-2")
        modified = event.data.replace(b"Original", b"Modified")
        event.data = modified
        event.save()

        # Check delta
        synced = work_cal.objects(sync_token=token1)
        events = list(synced)

        assert len(events) == 1
        assert events[0].data is not None
        assert b"Modified" in events[0].data
        print("✓ Recurring event modification detected in delta")

    def test_recurring_event_deletion_detected(self):
        """Deleting a recurring event should be detected"""
        from tests.mock_caldav import MockCalendar

        work_cal = MockCalendar("Work")

        # Create and sync
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-3
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:To Delete
RRULE:FREQ=DAILY;COUNT=5
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        synced = work_cal.objects(sync_token=None)
        token1 = synced.sync_token

        # Delete
        event = work_cal.event_by_uid("recurring-3")
        event.delete()

        # Check delta
        synced = work_cal.objects(sync_token=token1)
        events = list(synced)

        assert len(events) == 1
        assert events[0].data is None  # Deletion marker
        print("✓ Recurring event deletion detected")


class TestRecurringModifiedInstances:
    """Test recurring events with modified individual instances"""

    def test_modified_instance_with_recurrence_id(self):
        """Event with RECURRENCE-ID (modified instance of recurring event)"""
        # This is how CalDAV represents a modified instance
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:recurring-base
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Daily Meeting
RRULE:FREQ=DAILY;COUNT=10
TRANSP:OPAQUE
END:VEVENT
BEGIN:VEVENT
UID:recurring-base
RECURRENCE-ID:20250110T100000Z
DTSTART:20250110T140000Z
DTEND:20250110T150000Z
SUMMARY:Daily Meeting (Moved)
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

        cal = iCalendar.from_ical(ical)
        events = cal.walk('VEVENT')

        assert len(events) == 2

        # Base recurring event
        base = events[0]
        assert 'RRULE' in base
        assert 'RECURRENCE-ID' not in base

        # Modified instance
        modified = events[1]
        assert 'RECURRENCE-ID' in modified
        assert modified.get('SUMMARY') == 'Daily Meeting (Moved)'

        print("✓ Modified instance with RECURRENCE-ID parsed")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
