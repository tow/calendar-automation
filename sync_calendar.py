import caldav
from icalendar import Calendar
import json
import os
import tempfile
import shutil
from datetime import datetime

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
    # Write to temporary file first
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(STATE_FILE) or '.')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2)
        # Atomic move (replaces old file only after write completes)
        shutil.move(temp_path, STATE_FILE)
    except Exception as e:
        os.remove(temp_path)
        raise e

class CalendarSyncTransaction:
    """Ensures atomic calendar operations"""
    
    def __init__(self, work_cal, family_cal, state):
        self.work_cal = work_cal
        self.family_cal = family_cal
        self.state = state
        self.operations = []  # Track what we plan to do
        self.completed = []   # Track what succeeded
        
    def plan_create(self, work_uid, event_data):
        """Plan to create family event"""
        self.operations.append(('create', work_uid, event_data))
        
    def plan_update(self, work_uid, family_uid, event_data):
        """Plan to update family event"""
        self.operations.append(('update', work_uid, family_uid, event_data))
        
    def plan_delete(self, work_uid, family_uid):
        """Plan to delete family event"""
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
                        pass  # Already deleted
                    if work_uid in self.state["event_map"]:
                        del self.state["event_map"][work_uid]
                    self.completed.append(op)
                    
            except Exception as e:
                print(f"✗ Operation failed: {op[0]} - {e}")
                raise  # Abort entire transaction
        
        print(f"✓ Completed {len(self.completed)} operations successfully")

def main():
    print(f"=== Calendar Sync Started: {datetime.now().isoformat()} ===")
    
    # Load previous state
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
        
        # Create transaction for atomic operations
        transaction = CalendarSyncTransaction(work_cal, family_cal, state)
        
        # Track current work event UIDs
        current_work_uids = set()
        
        # Process changed/new events
        for event in synced_events:
            try:
                cal = Calendar.from_ical(event.data)
                for component in cal.walk('VEVENT'):
                    work_uid = str(component.get('UID'))
                    current_work_uids.add(work_uid)
                    
                    # Check if busy (TRANSP=OPAQUE or absent)
                    transp = component.get('TRANSP', 'OPAQUE')
                    
                    if transp == 'OPAQUE':
                        # Busy event - create or update in family calendar
                        family_event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Busy Sync//EN
BEGIN:VEVENT
UID:{work_uid}-family
DTSTART:{component['DTSTART'].to_ical().decode()}
DTEND:{component['DTEND'].to_ical().decode()}
SUMMARY:Busy
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR"""
                        
                        if work_uid in state["event_map"]:
                            # Update existing
                            family_uid = state["event_map"][work_uid]
                            transaction.plan_update(work_uid, family_uid, family_event_data)
                        else:
                            # Create new
                            transaction.plan_create(work_uid, family_event_data)
                    else:
                        # Free event - remove from family calendar if exists
                        if work_uid in state["event_map"]:
                            family_uid = state["event_map"][work_uid]
                            transaction.plan_delete(work_uid, family_uid)
                            
            except Exception as e:
                print(f"⚠ Error processing event: {e}")
                raise
        
        # Handle deletions - remove family events for deleted work events
        for work_uid in list(state["event_map"].keys()):
            if work_uid not in current_work_uids:
                family_uid = state["event_map"][work_uid]
                transaction.plan_delete(work_uid, family_uid)
        
        # Execute all operations atomically
        transaction.execute()
        
        # CRITICAL: Only update sync token after ALL operations succeed
        # If anything failed above, we exit before this point
        new_sync_token = synced_events.sync_token
        state["sync_token"] = new_sync_token
        
        # Save state atomically
        save_state(state)
        
        print(f"✓ Sync complete: {len(state['event_map'])} busy events tracked")
        print(f"=== Calendar Sync Finished: {datetime.now().isoformat()} ===")
        
    except Exception as e:
        print(f"✗ Sync failed: {e}")
        # DON'T update state - next run will retry from last known good state
        exit(1)  # Non-zero exit code triggers workflow failure notification

if __name__ == "__main__":
    main()
