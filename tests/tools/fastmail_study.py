#!/usr/bin/env python3
"""
Empirical study of Fastmail CalDAV behavior.
This script helps understand how Fastmail represents events and sync tokens.
"""

import caldav
import os
import json
from datetime import datetime
from icalendar import Calendar

# Use same config as main script
FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME')

def save_study_results(filename, data):
    """Save study results to tests/fixtures/"""
    os.makedirs('tests/fixtures/study', exist_ok=True)
    path = f'tests/fixtures/study/{filename}'
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  → Saved to {path}")

def analyze_event(event_data):
    """Analyze an event's iCalendar structure"""
    try:
        cal = Calendar.from_ical(event_data)
        analysis = {
            'raw_ical': event_data.decode() if isinstance(event_data, bytes) else event_data,
            'components': []
        }

        for component in cal.walk():
            if component.name == 'VEVENT':
                comp_info = {
                    'type': 'VEVENT',
                    'uid': str(component.get('UID', 'NO UID')),
                    'summary': str(component.get('SUMMARY', 'NO SUMMARY')),
                    'has_dtstart': 'DTSTART' in component,
                    'has_dtend': 'DTEND' in component,
                    'has_duration': 'DURATION' in component,
                    'has_transp': 'TRANSP' in component,
                    'transp_value': str(component.get('TRANSP', 'NOT SET')),
                    'has_rrule': 'RRULE' in component,
                    'has_recurrence_id': 'RECURRENCE-ID' in component,
                    'properties': {}
                }

                # Capture datetime properties in detail
                if 'DTSTART' in component:
                    dtstart = component['DTSTART']
                    comp_info['properties']['DTSTART'] = {
                        'value': str(dtstart.to_ical()),
                        'params': dict(dtstart.params) if hasattr(dtstart, 'params') else {},
                        'dt_type': type(dtstart.dt).__name__,
                    }

                if 'DTEND' in component:
                    dtend = component['DTEND']
                    comp_info['properties']['DTEND'] = {
                        'value': str(dtend.to_ical()),
                        'params': dict(dtend.params) if hasattr(dtend, 'params') else {},
                        'dt_type': type(dtend.dt).__name__,
                    }

                if 'DURATION' in component:
                    comp_info['properties']['DURATION'] = {
                        'value': str(component['DURATION'].to_ical()),
                    }

                analysis['components'].append(comp_info)

        return analysis
    except Exception as e:
        return {'error': str(e), 'raw_data': str(event_data)[:500]}

def study_sync_behavior(work_cal, test_name, sync_token=None):
    """Study what a sync operation returns"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Sync token: {sync_token}")
    print('='*60)

    try:
        synced_events = work_cal.objects(
            sync_token=sync_token,
            load_objects=True
        )

        new_sync_token = synced_events.sync_token
        events_list = list(synced_events)

        print(f"New sync token: {new_sync_token}")
        print(f"Events returned: {len(events_list)}")

        results = {
            'test_name': test_name,
            'old_sync_token': sync_token,
            'new_sync_token': new_sync_token,
            'event_count': len(events_list),
            'events': []
        }

        for event in events_list:
            event_analysis = analyze_event(event.data)
            results['events'].append(event_analysis)

            # Print summary
            for comp in event_analysis.get('components', []):
                if comp.get('type') == 'VEVENT':
                    print(f"\n  Event: {comp['summary']}")
                    print(f"    UID: {comp['uid']}")
                    print(f"    DTSTART: {comp['has_dtstart']}")
                    print(f"    DTEND: {comp['has_dtend']}")
                    print(f"    DURATION: {comp['has_duration']}")
                    print(f"    TRANSP: {comp['transp_value']}")
                    if comp['has_dtstart']:
                        print(f"    DTSTART details: {comp['properties'].get('DTSTART')}")

        return results, new_sync_token

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}, None

def main():
    print("=== Fastmail CalDAV Behavior Study ===\n")

    if not all([FASTMAIL_URL, FASTMAIL_USER, FASTMAIL_PASS, WORK_CAL_NAME]):
        print("ERROR: Missing environment variables")
        print("Need: FASTMAIL_URL, FASTMAIL_USER, FASTMAIL_PASS, WORK_CAL_NAME")
        return

    # Connect
    print(f"Connecting to: {FASTMAIL_URL}")
    print(f"User: {FASTMAIL_USER}")
    print(f"Calendar: {WORK_CAL_NAME}\n")

    client = caldav.DAVClient(
        url=FASTMAIL_URL,
        username=FASTMAIL_USER,
        password=FASTMAIL_PASS
    )

    principal = client.principal()
    work_cal = principal.calendar(name=WORK_CAL_NAME)

    # Test 1: Initial sync with sync_token=None
    results1, token1 = study_sync_behavior(work_cal, "Initial sync (sync_token=None)", sync_token=None)
    save_study_results('01_initial_sync.json', results1)

    # Test 2: Immediate re-sync (should show no changes)
    if token1:
        results2, token2 = study_sync_behavior(work_cal, "Re-sync immediately (no changes)", sync_token=token1)
        save_study_results('02_resync_no_changes.json', results2)

        print("\n" + "="*60)
        print("STUDY COMPLETE")
        print("="*60)
        print("\nNext steps:")
        print("1. Review files in tests/fixtures/study/")
        print("2. Manually create/modify/delete events in Fastmail web UI")
        print("3. Re-run this script to capture how changes appear")
        print("4. Pay special attention to:")
        print("   - How deletions are represented")
        print("   - How TRANSP changes appear")
        print("   - Timezone representation")
        print("   - Events with DURATION vs DTEND")

if __name__ == "__main__":
    main()
