import caldav
from icalendar import Calendar
import json
import os
import tempfile
import shutil
from datetime import datetime, timedelta

# Configuration from environment
FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME')
FAMILY_CAL_NAME = os.getenv('FAMILY_CAL_NAME')
STATE_FILE = "calendar_sync_state.json"

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
                    family_event = self.family_cal.event_by_uid(family_uid)
                    family_event.data = event_data
                    family_event.save()
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

def main():
    print(f"=== Calendar Sync Started: {datetime.now().isoformat()} ===")
    
    state = load_state()
    
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
        
        # Get changes since last sync
        synced_events = work_cal.objects(
            sync_token=state["sync_token"], 
            load_objects=True
        )
        
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)
        current_work_uids = set()
        
        # Process changed/new events
        for event in synced_events:
            try:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    current_work_uids.add(work_uid)
                    
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
        
        # Handle deletions
        for work_uid in list(state["event_map"].keys()):
            if work_uid not in current_work_uids:
                family_uid = state["event_map"][work_uid]
                transaction.plan_delete(work_uid, family_uid)
                print(f"Deleted event {work_uid[:8]}... → Remove from family calendar")
        
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
    main()
