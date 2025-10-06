"""
Mock CalDAV server that mimics Fastmail's behavior based on empirical testing.

Key findings from Fastmail testing:
1. sync_token=None returns all events
2. Deletions appear in sync results with data=None
3. Modifications appear with full event data
4. Sync token increments with each change
5. TRANSP property can be present, absent, or set to OPAQUE/TRANSPARENT
"""

from icalendar import Calendar as iCalendar
from typing import Dict, Optional, List
import copy


class MockEvent:
    """Mimics caldav.Event"""

    def __init__(self, data: str, url: str, calendar):
        self.data = data.encode() if isinstance(data, str) else data
        self.url = url
        self._calendar = calendar
        self._uid = None

        # Extract UID
        if self.data:
            try:
                cal = iCalendar.from_ical(self.data)
                for component in cal.walk('VEVENT'):
                    self._uid = str(component.get('UID'))
                    break
            except:
                pass

    @property
    def uid(self):
        return self._uid

    def save(self):
        """Save modifications back to calendar"""
        if self._uid:
            self._calendar._update_event(self._uid, self.data)

    def delete(self):
        """Delete this event from calendar"""
        if self._uid:
            self._calendar._delete_event(self._uid)


class MockSyncResult:
    """Mimics the result of calendar.objects()"""

    def __init__(self, events: List[MockEvent], sync_token: str):
        self._events = events
        self.sync_token = sync_token

    def __iter__(self):
        return iter(self._events)

    def __len__(self):
        return len(self._events)


class MockCalendar:
    """
    Mock CalDAV calendar that behaves like Fastmail.

    Tracks events and sync history to support sync token operations.
    """

    def __init__(self, name: str):
        self.name = name
        self._events: Dict[str, str] = {}  # uid -> icalendar data
        self._sync_counter = 1000
        self._sync_history: List[tuple] = []  # (token, operation, uid, data)
        self._deleted_uids: set = set()  # Track deletions for current sync

    def _get_sync_token(self) -> str:
        """Generate a sync token"""
        return f"data:,1759734674-{self._sync_counter}"

    def _increment_sync_token(self):
        """Increment sync token after a change"""
        self._sync_counter += 1

    def _add_to_history(self, operation: str, uid: str, data: Optional[str] = None):
        """Record an operation in sync history"""
        token_before = self._get_sync_token()
        self._increment_sync_token()
        token_after = self._get_sync_token()
        self._sync_history.append((token_before, token_after, operation, uid, data))

    def save_event(self, ical_data: str):
        """Create or update an event"""
        # Parse to get UID
        if isinstance(ical_data, bytes):
            ical_data = ical_data.decode()

        cal = iCalendar.from_ical(ical_data)
        uid = None
        for component in cal.walk('VEVENT'):
            uid = str(component.get('UID'))
            break

        if not uid:
            raise ValueError("Event must have UID")

        operation = 'modify' if uid in self._events else 'create'
        self._events[uid] = ical_data
        self._add_to_history(operation, uid, ical_data)

    def _update_event(self, uid: str, data):
        """Internal: update existing event"""
        if isinstance(data, bytes):
            data = data.decode()
        self._events[uid] = data
        self._add_to_history('modify', uid, data)

    def _delete_event(self, uid: str):
        """Internal: delete event"""
        if uid in self._events:
            del self._events[uid]
            self._add_to_history('delete', uid, None)

    def event_by_uid(self, uid: str) -> MockEvent:
        """Get event by UID"""
        if uid not in self._events:
            raise Exception(f"NotFoundError at '{uid} not found on server', reason no reason")

        url = f"https://caldav.fastmail.com/dav/calendars/user/test/{uid}.ics"
        return MockEvent(self._events[uid], url, self)

    def objects(self, sync_token: Optional[str] = None, load_objects: bool = True) -> MockSyncResult:
        """
        Get events, optionally filtered by sync token.

        Based on Fastmail behavior:
        - sync_token=None: return all current events
        - sync_token=X: return events changed since that token
        """
        current_token = self._get_sync_token()

        if sync_token is None:
            # Return all current events
            events = []
            for uid, data in self._events.items():
                url = f"https://caldav.fastmail.com/dav/calendars/user/test/{uid}.ics"
                events.append(MockEvent(data, url, self))
            return MockSyncResult(events, current_token)

        # Find changes since sync_token
        changes = []
        seen_uids = set()

        for token_before, token_after, operation, uid, data in self._sync_history:
            # Include changes that happened after the given sync_token
            if token_before == sync_token or (sync_token and token_before > sync_token):
                if uid not in seen_uids:
                    seen_uids.add(uid)
                    url = f"https://caldav.fastmail.com/dav/calendars/user/test/{uid}.ics"

                    if operation == 'delete':
                        # Deletion: MockEvent with data=None
                        mock_event = MockEvent('', url, self)
                        mock_event.data = None
                        mock_event._uid = uid
                        changes.append(mock_event)
                    else:
                        # Create or modify: return current data if still exists
                        if uid in self._events:
                            changes.append(MockEvent(self._events[uid], url, self))

        return MockSyncResult(changes, current_token)

    def clear(self):
        """Clear all events (for testing)"""
        self._events.clear()
        self._sync_history.clear()
        self._sync_counter = 1000


class MockPrincipal:
    """Mimics caldav.Principal"""

    def __init__(self):
        self._calendars: Dict[str, MockCalendar] = {}

    def calendar(self, name: str) -> MockCalendar:
        """Get or create a calendar by name"""
        if name not in self._calendars:
            self._calendars[name] = MockCalendar(name)
        return self._calendars[name]


class MockDAVClient:
    """Mimics caldav.DAVClient"""

    def __init__(self, url: str, username: str, password: str):
        self.url = url
        self.username = username
        self.password = password
        self._principal = MockPrincipal()

    def principal(self) -> MockPrincipal:
        """Get the principal"""
        return self._principal
