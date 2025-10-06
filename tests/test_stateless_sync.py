"""
Tests for stateless sync mode.

Stateless mode doesn't use state files or sync tokens - it compares
the full state of both calendars to determine what operations to perform.
"""

import pytest
import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_calendar import (
    sync_stateless,
    get_managed_family_events,
)
from tests.mock_caldav import MockCalendar
from unittest.mock import patch, MagicMock

# Helper to generate future dates for tests
def get_test_date(days_from_now=1):
    """Get a date in the future for testing (within sync range)"""
    future_date = datetime.now() + timedelta(days=days_from_now)
    return future_date.strftime("%Y%m%dT%H%M%SZ")


@pytest.fixture
def wide_time_range():
    """Temporarily set wide time range to include test dates"""
    import sync_calendar
    orig_start = sync_calendar.SYNC_START_OFFSET_DAYS
    orig_end = sync_calendar.SYNC_END_OFFSET_DAYS
    sync_calendar.SYNC_START_OFFSET_DAYS = -365  # 1 year in past
    sync_calendar.SYNC_END_OFFSET_DAYS = 365      # 1 year in future
    yield
    sync_calendar.SYNC_START_OFFSET_DAYS = orig_start
    sync_calendar.SYNC_END_OFFSET_DAYS = orig_end


class TestGetManagedFamilyEvents:
    """Test the efficient family event retrieval using ends-with query"""

    def test_get_managed_family_events_fallback(self):
        """Test fallback when extended query fails"""
        family_cal = MockCalendar("Family")

        # Add some events
        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:other-event
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:Not managed
END:VEVENT
END:VCALENDAR""")

        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-2-family
DTSTART:20250107T140000Z
DTEND:20250107T150000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        # Mock requests to simulate server not supporting extended query
        import requests
        with patch('requests.request') as mock_request:
            # Simulate error that triggers fallback
            mock_request.side_effect = Exception("Extended query not supported")

            import sync_calendar
            orig_user = sync_calendar.FASTMAIL_USER
            orig_pass = sync_calendar.FASTMAIL_PASS
            sync_calendar.FASTMAIL_USER = "test@example.com"
            sync_calendar.FASTMAIL_PASS = "test"

            try:
                result = get_managed_family_events(family_cal)

                # Should find only the -family events via fallback
                assert "event-1-family" in result
                assert "event-2-family" in result
                assert "other-event" not in result

                # Should map family UID to work UID
                assert result["event-1-family"] == "event-1"
                assert result["event-2-family"] == "event-2"
            finally:
                sync_calendar.FASTMAIL_USER = orig_user
                sync_calendar.FASTMAIL_PASS = orig_pass


class TestStatelessSync:
    """Test complete stateless sync workflow"""

    def test_stateless_sync_creates_new_events(self, wide_time_range):
        """Stateless sync should create family events for busy work events"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Add busy event to work calendar
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:work-event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Work Meeting
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        # Mock the extended query to return empty (no managed events yet)
        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {}

            sync_stateless(work_cal, family_cal)

        # Should have created family event
        assert "work-event-1-family" in family_cal._events

    def test_stateless_sync_deletes_orphaned_events(self, wide_time_range):
        """Stateless sync should delete family events when work event is gone"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Family calendar has an event, but work calendar doesn't
        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:old-event-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        # Mock the extended query to return the orphaned event
        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {"old-event-family": "old-event"}

            sync_stateless(work_cal, family_cal)

        # Should have deleted the orphaned event
        assert "old-event-family" not in family_cal._events

    def test_stateless_sync_ignores_free_events(self, wide_time_range):
        """Stateless sync should not sync TRANSPARENT events"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Add free (TRANSPARENT) event to work calendar
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:free-event
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Free Time
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR""")

        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {}

            sync_stateless(work_cal, family_cal)

        # Should NOT have created family event
        assert "free-event-family" not in family_cal._events

    def test_stateless_sync_updates_existing_events(self, wide_time_range):
        """Stateless sync should update family events (via UID overwrite)"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Work event
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T140000Z
DTEND:20250107T150000Z
SUMMARY:Updated Meeting
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        # Old family event (different time)
        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {"event-1-family": "event-1"}

            sync_stateless(work_cal, family_cal)

        # Should still exist
        assert "event-1-family" in family_cal._events

        # Should have new time
        event = family_cal.event_by_uid("event-1-family")
        assert b"20250107T140000Z" in event.data  # New start time

    def test_stateless_sync_handles_transp_change_to_free(self, wide_time_range):
        """When work event becomes free, family event should be deleted"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Work event changed to TRANSPARENT
        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Now Free
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR""")

        # Family event still exists
        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {"event-1-family": "event-1"}

            sync_stateless(work_cal, family_cal)

        # Should have been deleted (event is now free)
        assert "event-1-family" not in family_cal._events

    def test_stateless_sync_full_workflow(self, wide_time_range):
        """Test complete stateless sync with multiple operations"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        # Work calendar state:
        # - event-1: busy (should create)
        # - event-2: busy (should update existing)
        # - event-3: free (should ignore)
        # - event-4: deleted (not present)

        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:New Event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-2
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:Updated Event
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-3
DTSTART:20250107T140000Z
DTEND:20250107T150000Z
SUMMARY:Free Event
TRANSP:TRANSPARENT
END:VEVENT
END:VCALENDAR""")

        # Family calendar state:
        # - event-2-family: exists (should update)
        # - event-4-family: orphaned (should delete)

        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-2-family
DTSTART:20250107T110000Z
DTEND:20250107T120000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        family_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-4-family
DTSTART:20250107T160000Z
DTEND:20250107T170000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        with patch('sync_calendar.get_managed_family_events') as mock_get:
            mock_get.return_value = {
                "event-2-family": "event-2",
                "event-4-family": "event-4"
            }

            sync_stateless(work_cal, family_cal)

        # Verify results
        assert "event-1-family" in family_cal._events  # Created
        assert "event-2-family" in family_cal._events  # Updated
        assert "event-3-family" not in family_cal._events  # Not created (free)
        assert "event-4-family" not in family_cal._events  # Deleted (orphaned)

    def test_stateless_sync_is_idempotent(self, wide_time_range):
        """Running stateless sync multiple times should be safe"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        work_cal.save_event("""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Meeting
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""")

        with patch('sync_calendar.get_managed_family_events') as mock_get:
            # First sync - no managed events
            mock_get.return_value = {}
            sync_stateless(work_cal, family_cal)

            assert "event-1-family" in family_cal._events
            first_event = family_cal.event_by_uid("event-1-family")

            # Second sync - event exists
            mock_get.return_value = {"event-1-family": "event-1"}
            sync_stateless(work_cal, family_cal)

            # Still exists, no duplicates
            assert "event-1-family" in family_cal._events
            assert len(family_cal._events) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
