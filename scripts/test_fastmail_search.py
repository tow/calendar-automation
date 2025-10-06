#!/usr/bin/env python3
"""
Test Fastmail's calendar.search() method (new API)
"""
import caldav
import os
from datetime import datetime, timedelta

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME', 'Claude sandpit')

client = caldav.DAVClient(
    url=FASTMAIL_URL,
    username=FASTMAIL_USER,
    password=FASTMAIL_PASS
)

principal = client.principal()
work_cal = principal.calendar(name=WORK_CAL_NAME)

print("=== Testing calendar.search() with time ranges ===\n")

# Test 1: Open-ended (start=now, no end)
print("Test 1: Open-ended search (from now onwards)")
try:
    start = datetime.now()
    events = work_cal.search(start=start, end=None, event=True, expand=False)
    count = len(list(events))
    print(f"✅ Works! Found {count} future events\n")
except Exception as e:
    print(f"❌ Failed: {e}\n")

# Test 2: With explicit end date
print("Test 2: With end date (next 30 days)")
try:
    start = datetime.now()
    end = start + timedelta(days=30)
    events = work_cal.search(start=start, end=end, event=True, expand=False)
    count = len(list(events))
    print(f"✅ Works! Found {count} events\n")
except Exception as e:
    print(f"❌ Failed: {e}\n")

# Test 3: Check if we can use a very far future date as "infinity"
print("Test 3: Using far future date as 'infinity'")
try:
    start = datetime.now()
    end = datetime(2100, 1, 1)  # Year 2100
    events = work_cal.search(start=start, end=end, event=True, expand=False)
    count = len(list(events))
    print(f"✅ Works! Found {count} events (same as open-ended should be)\n")
except Exception as e:
    print(f"❌ Failed: {e}\n")

print("=== Recommendation ===")
print("Use: calendar.search(start=datetime.now(), end=None)")
print("This gives us open-ended 'from now onwards' queries!")
