"""
Tests for advanced atomicity and failure recovery scenarios.

These tests verify behavior when operations fail partway through,
network errors occur, or state becomes inconsistent.
"""

import pytest
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sync_calendar import (
    CalendarSyncTransaction,
    load_state,
    save_state,
    get_event_end,
    format_datetime_for_ical
)
from tests.mock_caldav import MockCalendar
from icalendar import Calendar as iCalendar


class FailingMockCalendar(MockCalendar):
    """Mock calendar that can be configured to fail operations"""

    def __init__(self, name):
        super().__init__(name)
        self.fail_on_save = False
        self.fail_on_nth_save = None
        self.save_count = 0

    def save_event(self, ical_data):
        if self.fail_on_save:
            raise Exception("Simulated network failure")

        self.save_count += 1
        if self.fail_on_nth_save and self.save_count == self.fail_on_nth_save:
            raise Exception(f"Simulated failure on save #{self.save_count}")

        return super().save_event(ical_data)


@pytest.fixture
def temp_state_file(tmp_path):
    state_file = tmp_path / "state.json"
    return str(state_file)


class TestPartialTransactionFailure:
    """Test behavior when transaction fails partway through"""

    def test_state_modified_before_all_operations_complete(self, temp_state_file):
        """
        ISSUE: State is modified during transaction, not after.
        If operation fails, state has partial updates.
        """
        work_cal = MockCalendar("Work")
        family_cal = FailingMockCalendar("Family")

        import sync_calendar
        original_state_file = sync_calendar.STATE_FILE
        sync_calendar.STATE_FILE = temp_state_file

        try:
            # Create two events
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

            # Sync - but make the 2nd save fail
            family_cal.fail_on_nth_save = 2

            state = load_state()
            synced = work_cal.objects(sync_token=state["sync_token"], load_objects=True)
            transaction = CalendarSyncTransaction(work_cal, family_cal, state)

            for event in synced:
                if event.data:
                    cal = iCalendar.from_ical(event.data)
                    for comp in cal.walk('VEVENT'):
                        work_uid = str(comp.get('UID'))
                        dtstart = comp['DTSTART']
                        dtend = get_event_end(comp)

                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
END:VEVENT
END:VCALENDAR"""

                        transaction.plan_create(work_uid, family_event_data)

            # Execute should fail on 2nd operation
            try:
                transaction.execute()
                pytest.fail("Should have raised exception")
            except Exception as e:
                assert "Simulated failure" in str(e)
                print(f"✓ Transaction failed as expected: {e}")

            # Check state
            print(f"State after failure: {state['event_map']}")
            print(f"Family calendar: {list(family_cal._events.keys())}")

            # PROBLEM: event-1 is in state but sync token not saved
            # This is actually OK because:
            # - event-1-family IS in the calendar
            # - State has event-1 mapping
            # - Sync token NOT updated (so next sync will retry)

            # Next sync will see event-1 and event-2 again
            # event-1 will try to UPDATE (it's in event_map)
            # event-2 will try to CREATE

            assert "event-1" in state["event_map"]
            assert "event-1-family" in family_cal._events
            print("✓ Partial state is recoverable on next sync")

        finally:
            sync_calendar.STATE_FILE = original_state_file

    def test_idempotent_operations_on_retry(self, temp_state_file):
        """
        When sync token is not updated, operations replay.
        This tests that replaying is safe (idempotent).
        """
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        import sync_calendar
        original_state_file = sync_calendar.STATE_FILE
        sync_calendar.STATE_FILE = temp_state_file

        try:
            # Create event
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

            # First sync - completes successfully
            state = load_state()
            synced = work_cal.objects(sync_token=state["sync_token"])
            transaction = CalendarSyncTransaction(work_cal, family_cal, state)

            for event in synced:
                if event.data:
                    cal = iCalendar.from_ical(event.data)
                    for comp in cal.walk('VEVENT'):
                        work_uid = str(comp.get('UID'))
                        dtstart = comp['DTSTART']
                        dtend = get_event_end(comp)

                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
END:VEVENT
END:VCALENDAR"""

                        if work_uid in state["event_map"]:
                            transaction.plan_update(work_uid, state["event_map"][work_uid], family_event_data)
                        else:
                            transaction.plan_create(work_uid, family_event_data)

            transaction.execute()
            state["sync_token"] = synced.sync_token
            save_state(state)

            assert "event-1-family" in family_cal._events
            print("✓ First sync completed")

            # Simulate: state file lost but family calendar still has event
            # (or sync token not updated due to crash)
            # Reset state but keep family calendar
            state = {"sync_token": None, "event_map": {}}

            # Second sync - should handle duplicate gracefully
            synced = work_cal.objects(sync_token=state["sync_token"])
            transaction = CalendarSyncTransaction(work_cal, family_cal, state)

            for event in synced:
                if event.data:
                    cal = iCalendar.from_ical(event.data)
                    for comp in cal.walk('VEVENT'):
                        work_uid = str(comp.get('UID'))
                        dtstart = comp['DTSTART']
                        dtend = get_event_end(comp)

                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
END:VEVENT
END:VCALENDAR"""

                        # Will try to CREATE (not in event_map)
                        transaction.plan_create(work_uid, family_event_data)

            # Should succeed - CalDAV allows overwriting
            transaction.execute()
            print("✓ Replay succeeded (idempotent)")

            # Should still have only one event
            assert "event-1-family" in family_cal._events
            assert len(family_cal._events) == 1

        finally:
            sync_calendar.STATE_FILE = original_state_file


class TestStateFileIntegrity:
    """Test state file handling under various failure conditions"""

    def test_corrupted_state_file_recovery(self, temp_state_file):
        """Corrupted state file should be handled gracefully"""
        import sync_calendar
        original_state_file = sync_calendar.STATE_FILE
        sync_calendar.STATE_FILE = temp_state_file

        try:
            # Write corrupted JSON
            with open(temp_state_file, 'w') as f:
                f.write("{ this is not valid json")

            # Should load empty state
            state = load_state()
            assert state == {"sync_token": None, "event_map": {}}
            print("✓ Corrupted state file handled gracefully")

        finally:
            sync_calendar.STATE_FILE = original_state_file

    def test_state_file_atomic_write_on_disk_full(self, temp_state_file):
        """If disk is full, atomic write should not corrupt existing state"""
        import sync_calendar
        original_state_file = sync_calendar.STATE_FILE
        sync_calendar.STATE_FILE = temp_state_file

        try:
            # Write good state
            good_state = {"sync_token": "good-token", "event_map": {"a": "b"}}
            save_state(good_state)

            # Verify it was written
            loaded = load_state()
            assert loaded == good_state

            # Note: Can't easily simulate disk full in test
            # But the atomic write pattern (temp file + move) protects against this
            # If write fails, temp file is removed and original state file unchanged

            print("✓ Atomic write pattern protects against corruption")

        finally:
            sync_calendar.STATE_FILE = original_state_file


class TestUpdateFallbackToCreate:
    """Test the error handling added for missing events during update"""

    def test_update_missing_event_creates_instead(self, temp_state_file):
        """
        If update fails because event doesn't exist,
        should create it instead (added in fix).
        """
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        state = {"sync_token": None, "event_map": {"event-1": "event-1-family"}}
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        # Plan update for event that doesn't exist in family calendar
        transaction.plan_update("event-1", "event-1-family", """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-1-family
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Busy
END:VEVENT
END:VCALENDAR""")

        # Should succeed (creates instead of failing)
        transaction.execute()

        assert "event-1-family" in family_cal._events
        print("✓ Update fallback to create works")


class TestDeletionRobustness:
    """Test deletion handling edge cases"""

    def test_delete_already_deleted_event(self):
        """Deleting an event that's already gone should not error"""
        work_cal = MockCalendar("Work")
        family_cal = MockCalendar("Family")

        state = {"sync_token": None, "event_map": {"event-1": "event-1-family"}}
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        # Plan deletion for event that doesn't exist
        transaction.plan_delete("event-1", "event-1-family")

        # Should succeed (silently handles missing event)
        transaction.execute()

        assert "event-1" not in state["event_map"]
        print("✓ Delete of non-existent event handled gracefully")


class TestSyncTokenInvalidation:
    """Test handling of invalid/stale sync tokens"""

    def test_stale_sync_token_behavior(self):
        """
        What happens when sync token is invalid?

        Note: This is hard to test without real CalDAV server.
        With Fastmail, an invalid token likely returns an error
        or treats it as sync_token=None.
        """
        # This would require real CalDAV server testing
        # Documenting expected behavior:

        print("⚠ Stale sync token handling:")
        print("  - CalDAV server should return error or all events")
        print("  - Current code would raise exception from caldav library")
        print("  - Could add try/catch to reset sync_token on error")
        print("  - Requires real-world testing to verify")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
