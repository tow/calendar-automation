#!/usr/bin/env python3
"""
Test if Fastmail supports CalDAV time-range queries
"""
import caldav
import os
from datetime import datetime, timedelta

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME', 'Claude sandpit')

print("=== Testing Fastmail Time-Range Query Support ===\n")

# Connect to Fastmail
client = caldav.DAVClient(
    url=FASTMAIL_URL,
    username=FASTMAIL_USER,
    password=FASTMAIL_PASS
)

principal = client.principal()
work_cal = principal.calendar(name=WORK_CAL_NAME)

print(f"Calendar: {WORK_CAL_NAME}")
print(f"Calendar URL: {work_cal.url}\n")

# Test 1: Basic date_search
print("Test 1: Basic date_search (today to +30 days)")
try:
    start = datetime.now().date()
    end = start + timedelta(days=30)
    print(f"Range: {start} to {end}")
    
    events = work_cal.date_search(start=start, end=end, expand=False)
    count = len(list(events))
    print(f"✅ date_search works! Found {count} events\n")
except Exception as e:
    print(f"❌ date_search failed: {e}\n")

# Test 2: Open-ended query (no end date)
print("Test 2: Open-ended query (start=today, no end)")
try:
    start = datetime.now().date()
    print(f"Range: {start} to infinity")
    
    events = work_cal.date_search(start=start, end=None, expand=False)
    count = len(list(events))
    print(f"✅ Open-ended query works! Found {count} events\n")
except Exception as e:
    print(f"❌ Open-ended query failed: {e}\n")

# Test 3: Check what date_search actually does
print("Test 3: Inspecting date_search behavior")
import inspect
try:
    source = inspect.getsource(work_cal.date_search)
    print("date_search source (first 500 chars):")
    print(source[:500])
except:
    print("Could not inspect source")

print("\n=== Tests Complete ===")
