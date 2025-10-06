#!/usr/bin/env python3
"""
Create diverse test events in Fastmail to study behavior.
"""

import caldav
import os
from datetime import datetime, timedelta, date

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME')

def create_event(cal, ical_data, description):
    """Create an event and print status"""
    try:
        cal.save_event(ical_data)
        print(f"✓ Created: {description}")
    except Exception as e:
        print(f"✗ Failed: {description} - {e}")

def main():
    print("=== Creating Test Events in Fastmail ===\n")

    client = caldav.DAVClient(
        url=FASTMAIL_URL,
        username=FASTMAIL_USER,
        password=FASTMAIL_PASS
    )

    principal = client.principal()
    cal = principal.calendar(name=WORK_CAL_NAME)

    # 1. Basic timed event with DTEND, OPAQUE
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-basic-timed-opaque
DTSTART:20250107T100000Z
DTEND:20250107T110000Z
SUMMARY:Basic Timed (OPAQUE)
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Basic timed event with DTEND and TRANSP:OPAQUE")

    # 2. Basic timed event with DTEND, TRANSPARENT
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-basic-timed-transparent
DTSTART:20250107T120000Z
DTEND:20250107T130000Z
SUMMARY:Basic Timed (TRANSPARENT)
TRANSP:TRANSPARENT
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Basic timed event with DTEND and TRANSP:TRANSPARENT")

    # 3. Event with no TRANSP (test default)
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-no-transp
DTSTART:20250107T140000Z
DTEND:20250107T150000Z
SUMMARY:No TRANSP Property
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Event with no TRANSP property")

    # 4. Event with DURATION instead of DTEND
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-duration
DTSTART:20250107T160000Z
DURATION:PT1H30M
SUMMARY:Event with DURATION
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Event with DURATION (PT1H30M)")

    # 5. Point event (only DTSTART, no DTEND or DURATION)
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-point-event
DTSTART:20250107T180000Z
SUMMARY:Point Event
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Point event (only DTSTART)")

    # 6. All-day event (DATE type)
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-allday
DTSTART;VALUE=DATE:20250108
DTEND;VALUE=DATE:20250109
SUMMARY:All-Day Event
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "All-day event (DATE type)")

    # 7. Multi-day all-day event
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-multiday-allday
DTSTART;VALUE=DATE:20250109
DTEND;VALUE=DATE:20250112
SUMMARY:Multi-Day All-Day
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Multi-day all-day event")

    # 8. Event with timezone (America/New_York)
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:STANDARD
DTSTART:20241103T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:20250309T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:test-timezone-est
DTSTART;TZID=America/New_York:20250110T100000
DTEND;TZID=America/New_York:20250110T110000
SUMMARY:Event in EST
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Event with America/New_York timezone")

    # 9. Floating time event (no timezone)
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-floating-time
DTSTART:20250110T140000
DTEND:20250110T150000
SUMMARY:Floating Time Event
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "Floating time event (no timezone)")

    # 10. All-day with DURATION
    create_event(cal, """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-allday-duration
DTSTART;VALUE=DATE:20250112
DURATION:P2D
SUMMARY:All-Day with DURATION
TRANSP:OPAQUE
DTSTAMP:20250106T120000Z
END:VEVENT
END:VCALENDAR""", "All-day event with DURATION")

    print(f"\n✓ Test event creation complete!")
    print("Run fastmail_study.py again to see how Fastmail represents these events")

if __name__ == "__main__":
    main()
