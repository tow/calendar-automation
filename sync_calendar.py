import caldav
from icalendar import Calendar
import json
import os
import tempfile
import shutil
import argparse
from datetime import datetime, timedelta

# Configuration from environment
FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME')
FAMILY_CAL_NAME = os.getenv('FAMILY_CAL_NAME')
STATE_FILE = "calendar_sync_state.json"
STATELESS_MODE = False  # Set via command-line flag

# Time range for syncing (default: start from yesterday to avoid timezone issues)
# This allows cleanup of events that ended yesterday but are still "current"
SYNC_START_OFFSET_DAYS = int(os.getenv('SYNC_START_OFFSET_DAYS', '-1'))  # Days before today
# Set to None or empty string for "all future events"
SYNC_END_OFFSET_DAYS_STR = os.getenv('SYNC_END_OFFSET_DAYS', '365')
SYNC_END_OFFSET_DAYS = None if SYNC_END_OFFSET_DAYS_STR in ('', 'None', 'none') else int(SYNC_END_OFFSET_DAYS_STR)

def load_state():
    """Load sync state with corruption protection"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠ Warning: Corrupted state file, starting fresh")
            return {"sync_token": None, "event_map": {}}
    return {"sync_token": None, "event_map": {}}

def save_state(state):
    """Atomic write to prevent corruption"""
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(STATE_FILE) or '.')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2)
        shutil.move(temp_path, STATE_FILE)
    except Exception as e:
        os.remove(temp_path)
        raise e

def get_event_end(component):
    """Get event end time, handling DTEND, DURATION, or all-day events"""
    if 'DTEND' in component:
        return component['DTEND']
    elif 'DURATION' in component and 'DTSTART' in component:
        # Calculate end from start + duration
        start = component['DTSTART'].dt
        duration = component['DURATION'].dt
        if isinstance(start, datetime):
            end = start + duration
        else:
            # Date only (all-day event)
            end = start + duration
        # Return in same format as DTEND would be
        from icalendar import vDatetime, vDate
        if isinstance(start, datetime):
            return vDatetime(end)
        else:
            return vDate(end)
    elif 'DTSTART' in component:
        # No end or duration - assume 0 duration (point in time)
        return component['DTSTART']
    else:
        raise ValueError("Event has no DTSTART")

def format_datetime_for_ical(dt_prop):
    """Format datetime property for iCalendar output"""
    try:
        return dt_prop.to_ical().decode()
    except:
        # Fallback for different property types
        return str(dt_prop)

class CalendarSyncTransaction:
    """Ensures atomic calendar operations"""
    
    def __init__(self, work_cal, family_cal, state):
        self.work_cal = work_cal
        self.family_cal = family_cal
        self.state = state
        self.operations = []
        self.completed = []
        
    def plan_create(self, work_uid, event_data):
        self.operations.append(('create', work_uid, event_data))
        
    def plan_update(self, work_uid, family_uid, event_data):
        self.operations.append(('update', work_uid, family_uid, event_data))
        
    def plan_delete(self, work_uid, family_uid):
        self.operations.append(('delete', work_uid, family_uid))
    
    def execute(self):
        """Execute all operations atomically"""
        print(f"Executing {len(self.operations)} calendar operations...")
        
        for op in self.operations:
            try:
                if op[0] == 'create':
                    _, work_uid, event_data = op
                    self.family_cal.save_event(event_data)
                    self.state["event_map"][work_uid] = f"{work_uid}-family"
                    self.completed.append(op)
                    
                elif op[0] == 'update':
                    _, work_uid, family_uid, event_data = op
                    try:
                        family_event = self.family_cal.event_by_uid(family_uid)
                        family_event.data = event_data
                        family_event.save()
                        self.completed.append(op)
                    except:
                        # If event doesn't exist, create it instead
                        print(f"  ⚠ Event {family_uid} not found for update, creating instead")
                        self.family_cal.save_event(event_data)
                        self.state["event_map"][work_uid] = family_uid
                        self.completed.append(op)
                    
                elif op[0] == 'delete':
                    _, work_uid, family_uid = op
                    try:
                        family_event = self.family_cal.event_by_uid(family_uid)
                        family_event.delete()
                    except:
                        pass
                    if work_uid in self.state["event_map"]:
                        del self.state["event_map"][work_uid]
                    self.completed.append(op)
                    
            except Exception as e:
                print(f"✗ Operation failed: {op[0]} - {e}")
                raise
        
        print(f"✓ Completed {len(self.completed)} operations successfully")

def get_managed_family_events(family_cal, start_date=None, end_date=None):
    """
    Get all events in family calendar that we manage (UID ends with '-family').
    Uses CalDAV extended query with ends-with match-type for efficiency.
    Optionally filters by time range.

    Returns dict mapping family UID to work UID.
    """
    import requests
    from requests.auth import HTTPBasicAuth

    # Build time-range filter if dates provided
    time_range_filter = ""
    if start_date and end_date:
        # Convert dates to iCal format (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%dT000000Z")
        end_str = end_date.strftime("%Y%m%dT235959Z")
        time_range_filter = f"""
        <C:comp-filter name="VEVENT">
          <C:time-range start="{start_str}" end="{end_str}"/>
        </C:comp-filter>"""

    query_xml = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop xmlns:D="DAV:">
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:prop-filter name="UID">
          <C:text-match match-type="ends-with">-family</C:text-match>
        </C:prop-filter>
        {time_range_filter}
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

    family_uid_to_work_uid = {}

    try:
        response = requests.request(
            'REPORT',
            str(family_cal.url),
            data=query_xml,
            headers={'Content-Type': 'application/xml; charset=utf-8'},
            auth=HTTPBasicAuth(FASTMAIL_USER, FASTMAIL_PASS)
        )

        if response.status_code == 207:  # Multi-Status
            # Parse response to extract UIDs
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)

            # Find all calendar-data elements
            for calendar_data in root.iter('{urn:ietf:params:xml:ns:caldav}calendar-data'):
                if calendar_data.text:
                    try:
                        cal = Calendar.from_ical(calendar_data.text)
                        for component in cal.walk('VEVENT'):
                            family_uid = str(component.get('UID'))
                            if family_uid.endswith('-family'):
                                work_uid = family_uid[:-7]  # Remove '-family' suffix
                                family_uid_to_work_uid[family_uid] = work_uid
                    except:
                        continue
    except Exception as e:
        print(f"⚠ Warning: Could not query family calendar for managed events: {e}")
        print(f"  Falling back to fetching all events...")
        # Fallback: fetch all events
        try:
            for event in family_cal.objects():
                if event.data:
                    cal = Calendar.from_ical(event.data)
                    for component in cal.walk('VEVENT'):
                        family_uid = str(component.get('UID'))
                        if family_uid.endswith('-family'):
                            work_uid = family_uid[:-7]
                            family_uid_to_work_uid[family_uid] = work_uid
        except Exception as e2:
            print(f"⚠ Error in fallback: {e2}")

    return family_uid_to_work_uid

def sync_stateless(work_cal, family_cal):
    """
    Stateless sync: no state file, no sync tokens.
    Determines what to do by comparing full state of both calendars.
    Only syncs events within the configured time range.
    """
    print("Running in STATELESS mode")

    # Calculate time range
    start_date = datetime.now().date() + timedelta(days=SYNC_START_OFFSET_DAYS)
    end_date = datetime.now().date() + timedelta(days=SYNC_END_OFFSET_DAYS) if SYNC_END_OFFSET_DAYS is not None else None
    end_str = end_date if end_date else "infinity (all future)"
    print(f"Syncing events from {start_date} to {end_str}")

    # Step 1: Get all busy events from work calendar within time range
    work_busy_events = {}  # work_uid -> event_data

    print("Fetching events from work calendar...")
    # Use CalDAV time-range query for efficiency
    try:
        # Try modern search() API first (preferred)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time()) if end_date else None
        events = work_cal.search(
            start=start_dt,
            end=end_dt,
            event=True,
            expand=False
        )
    except (AttributeError, TypeError):
        # Fallback if search not supported (e.g., in tests or old caldav)
        try:
            # Try deprecated date_search
            events = work_cal.date_search(start=start_date, end=end_date, expand=False)
        except:
            # Final fallback: fetch all
            events = work_cal.objects(load_objects=True)

    for event in events:
        if event.data:
            try:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    transp = component.get('TRANSP', 'OPAQUE')

                    # Filter by date (in case search didn't work or for recurring events)
                    dtstart = component.get('DTSTART')
                    if dtstart:
                        event_date = dtstart.dt
                        if isinstance(event_date, datetime):
                            event_date = event_date.date()

                        # Skip events outside our time range
                        if event_date < start_date:
                            continue
                        if end_date is not None and event_date > end_date:
                            continue

                    if transp == 'OPAQUE':
                        work_busy_events[work_uid] = component
            except Exception as e:
                print(f"⚠ Error parsing work event: {e}")
                continue

    print(f"Found {len(work_busy_events)} busy events in work calendar (within time range)")

    # Step 2: Get all managed events from family calendar (ends with '-family')
    print("Fetching managed events from family calendar...")
    family_managed = get_managed_family_events(family_cal, start_date, end_date)
    print(f"Found {len(family_managed)} managed events in family calendar (within time range)")

    # Step 3: Determine operations
    transaction = CalendarSyncTransaction(work_cal, family_cal, {"event_map": {}})

    # Create/Update: for each busy work event
    for work_uid, component in work_busy_events.items():
        family_uid = f"{work_uid}-family"

        try:
            dtstart = component['DTSTART']
            dtend = get_event_end(component)

            family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Busy Sync//EN
BEGIN:VEVENT
UID:{family_uid}
DTSTART:{format_datetime_for_ical(dtstart)}
DTEND:{format_datetime_for_ical(dtend)}
SUMMARY:Busy
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""

            if family_uid in family_managed:
                # Already exists - will be updated (or same if no changes)
                transaction.plan_create(work_uid, family_event_data)
                print(f"Update: {work_uid[:8]}...")
            else:
                # New event
                transaction.plan_create(work_uid, family_event_data)
                print(f"Create: {work_uid[:8]}...")
        except Exception as e:
            print(f"⚠ Skipping {work_uid}: {e}")
            continue

    # Delete: family events that no longer exist in work calendar
    for family_uid, work_uid in family_managed.items():
        if work_uid not in work_busy_events:
            transaction.plan_delete(work_uid, family_uid)
            print(f"Delete: {work_uid[:8]}... (no longer busy in work calendar)")

    # Step 4: Execute
    print(f"\nExecuting {len(transaction.operations)} operations...")
    transaction.execute()

    print(f"✓ Stateless sync complete")

def main(stateless=False):
    print(f"=== Calendar Sync Started: {datetime.now().isoformat()} ===")

    try:
        # Connect to Fastmail
        client = caldav.DAVClient(
            url=FASTMAIL_URL,
            username=FASTMAIL_USER,
            password=FASTMAIL_PASS
        )

        principal = client.principal()
        work_cal = principal.calendar(name=WORK_CAL_NAME)
        family_cal = principal.calendar(name=FAMILY_CAL_NAME)

        # Choose sync mode
        if stateless:
            sync_stateless(work_cal, family_cal)
            print(f"=== Calendar Sync Finished: {datetime.now().isoformat()} ===")
            return

        # Stateful mode (original implementation)
        state = load_state()

        # Get changes since last sync
        synced_events = work_cal.objects(
            sync_token=state["sync_token"],
            load_objects=True
        )
        
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)

        # Process changed/new events
        for event in synced_events:
            try:
                # Check for deletion marker (event.data is None when event is deleted)
                if event.data is None:
                    # Extract UID from URL (e.g., .../event-uid.ics)
                    # Try to get UID from the event object or parse from URL
                    work_uid = None
                    if hasattr(event, '_uid') and event._uid:
                        work_uid = event._uid
                    else:
                        # Parse from URL as fallback
                        url_str = str(event.url) if hasattr(event, 'url') else str(event)
                        if '.ics' in url_str:
                            work_uid = url_str.split('/')[-1].replace('.ics', '')

                    if work_uid and work_uid in state["event_map"]:
                        family_uid = state["event_map"][work_uid]
                        transaction.plan_delete(work_uid, family_uid)
                        print(f"Deleted event {work_uid[:8]}... → Remove from family calendar")
                    continue

                # Process normal events (created or modified)
                cal = Calendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))

                    # Filter by time range
                    dtstart = component.get('DTSTART')
                    if dtstart:
                        event_date = dtstart.dt
                        if isinstance(event_date, datetime):
                            event_date = event_date.date()

                        # Calculate time range
                        start_date = datetime.now().date() + timedelta(days=SYNC_START_OFFSET_DAYS)
                        end_date = datetime.now().date() + timedelta(days=SYNC_END_OFFSET_DAYS) if SYNC_END_OFFSET_DAYS is not None else None

                        # Skip events outside our time range
                        if event_date < start_date or (end_date is not None and event_date > end_date):
                            # If event exists in family calendar, delete it (it's now in the past)
                            if work_uid in state["event_map"]:
                                family_uid = state["event_map"][work_uid]
                                transaction.plan_delete(work_uid, family_uid)
                                print(f"Event {work_uid[:8]}... is outside time range → Remove from family calendar")
                            continue

                    # Debug: print event details
                    summary = component.get('SUMMARY', 'No title')
                    print(f"Processing: {summary} (UID: {work_uid[:8]}...)")

                    # Check if busy (TRANSP=OPAQUE or absent)
                    transp = component.get('TRANSP', 'OPAQUE')

                    if transp == 'OPAQUE':
                        # Busy event - create or update in family calendar
                        try:
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
                                # Update existing
                                family_uid = state["event_map"][work_uid]
                                transaction.plan_update(work_uid, family_uid, family_event_data)
                                print(f"  → Update in family calendar")
                            else:
                                # Create new
                                transaction.plan_create(work_uid, family_event_data)
                                print(f"  → Create in family calendar")
                        except Exception as e:
                            print(f"  ⚠ Skipping event - couldn't parse dates: {e}")
                            continue
                    else:
                        # Free event - remove from family calendar if exists
                        print(f"  → Free event (ignoring)")
                        if work_uid in state["event_map"]:
                            family_uid = state["event_map"][work_uid]
                            transaction.plan_delete(work_uid, family_uid)
                            print(f"  → Delete from family calendar")

            except Exception as e:
                print(f"⚠ Error processing event: {e}")
                # Continue with other events rather than failing completely
                continue
        
        # Execute all operations atomically
        transaction.execute()
        
        # Update sync token only after ALL operations succeed
        new_sync_token = synced_events.sync_token
        state["sync_token"] = new_sync_token
        
        # Save state atomically
        save_state(state)
        
        print(f"✓ Sync complete: {len(state['event_map'])} busy events tracked")
        print(f"=== Calendar Sync Finished: {datetime.now().isoformat()} ===")
        
    except Exception as e:
        print(f"✗ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Sync busy events from work calendar to family calendar'
    )
    parser.add_argument(
        '--stateless',
        action='store_true',
        help='Run in stateless mode (no state file, full sync each time)'
    )
    args = parser.parse_args()

    main(stateless=args.stateless)
