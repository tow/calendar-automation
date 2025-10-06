"""
Comprehensive test suite for calendar sync functionality.
"""

import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from icalendar import Calendar as iCalendar

# Import the code under test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import sync_calendar
from tests.mock_caldav import MockDAVClient, MockCalendar


@pytest.fixture
def temp_state_file(tmp_path):
    """Provide a temporary state file"""
    state_file = tmp_path / "test_state.json"
    original = sync_calendar.STATE_FILE
    sync_calendar.STATE_FILE = str(state_file)
    yield str(state_file)
    sync_calendar.STATE_FILE = original


@pytest.fixture
def mock_calendars():
    """Provide mock work and family calendars"""
    client = MockDAVClient(
        url="https://test.example.com",
        username="test@example.com",
        password="test"
    )
    principal = client.principal()
    work_cal = principal.calendar("Work")
    family_cal = principal.calendar("Family")
    return work_cal, family_cal


class TestGetEventEnd:
    """Test get_event_end() function with various event types"""

    def test_event_with_dtend(self):
        """Event with DTEND should return DTEND"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR"""
        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = sync_calendar.get_event_end(event)
        assert end.to_ical() == b'20250107T110000Z'

    def test_event_with_duration_timed(self):
        """Event with DURATION should calculate end time"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test
DTSTART:20250107T100000Z
DURATION:PT1H30M
SUMMARY:Test
END:VEVENT
END:VCALENDAR"""
        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = sync_calendar.get_event_end(event)
        # Should be start + 1.5 hours
        assert end.to_ical() == b'20250107T113000Z'

    def test_event_with_duration_allday(self):
        """All-day event with DURATION"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test
DTSTART;VALUE=DATE:20250108
DURATION:P2D
SUMMARY:Test
END:VEVENT
END:VCALENDAR"""
        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = sync_calendar.get_event_end(event)
        assert end.to_ical() == b'20250110'

    def test_point_event(self):
        """Event with only DTSTART (no end or duration)"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test
DTSTART:20250107T100000Z
SUMMARY:Test
END:VEVENT
END:VCALENDAR"""
        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        end = sync_calendar.get_event_end(event)
        # Should return DTSTART (zero duration)
        assert end.to_ical() == b'20250107T100000Z'

    def test_event_missing_dtstart_raises(self):
        """Event without DTSTART should raise error"""
        ical = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:test
SUMMARY:Test
END:VEVENT
END:VCALENDAR"""
        cal = iCalendar.from_ical(ical)
        event = cal.walk('VEVENT')[0]

        with pytest.raises(ValueError, match="no DTSTART"):
            sync_calendar.get_event_end(event)


class TestFormatDatetime:
    """Test format_datetime_for_ical() function"""

    def test_format_datetime_fallback(self):
        """Test fallback for datetime formatting when to_ical() fails"""
        # Create a mock object without to_ical method
        dt_prop = MagicMock()
        # Make to_ical() raise an exception
        dt_prop.to_ical.side_effect = AttributeError("no to_ical method")
        dt_prop.__str__ = MagicMock(return_value="20250107T100000Z")

        result = sync_calendar.format_datetime_for_ical(dt_prop)
        assert result == "20250107T100000Z"


class TestStateManagement:
    """Test state file handling"""

    def test_atomic_state_write(self, tmp_path):
        """State file writes should be atomic"""
        state_file = tmp_path / "state.json"
        sync_calendar.STATE_FILE = str(state_file)

        state = {"sync_token": "test-token", "event_map": {"a": "b"}}
        sync_calendar.save_state(state)

        # File should exist
        assert state_file.exists()

        # Content should be valid JSON
        loaded = sync_calendar.load_state()
        assert loaded == state

    def test_corrupted_state_recovery(self, tmp_path):
        """Corrupted state file should start fresh"""
        state_file = tmp_path / "state.json"
        sync_calendar.STATE_FILE = str(state_file)

        # Write corrupted JSON
        with open(state_file, 'w') as f:
            f.write("{ invalid json")

        # Should load empty state
        state = sync_calendar.load_state()
        assert state == {"sync_token": None, "event_map": {}}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
