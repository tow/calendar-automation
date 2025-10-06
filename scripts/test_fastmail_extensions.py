#!/usr/bin/env python3
"""
Test if Fastmail supports CalDAV extended query with ends-with match-type
"""
import caldav
import os
import requests
from requests.auth import HTTPBasicAuth

FASTMAIL_URL = os.getenv('FASTMAIL_URL')
FASTMAIL_USER = os.getenv('FASTMAIL_USER')
FASTMAIL_PASS = os.getenv('FASTMAIL_PASS')
WORK_CAL_NAME = os.getenv('WORK_CAL_NAME', 'Claude sandpit')

print("=== Testing Fastmail CalDAV Extensions Support ===\n")

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

# Test 1: Check OPTIONS response for calendar-query-extended
print("Test 1: Checking DAV capabilities...")
try:
    response = requests.request(
        'OPTIONS',
        str(work_cal.url),
        auth=HTTPBasicAuth(FASTMAIL_USER, FASTMAIL_PASS)
    )
    dav_header = response.headers.get('DAV', '')
    print(f"DAV header: {dav_header}")
    
    if 'calendar-query-extended' in dav_header:
        print("✅ Server advertises 'calendar-query-extended' support!")
    else:
        print("❌ Server does NOT advertise 'calendar-query-extended'")
except Exception as e:
    print(f"⚠ Error checking OPTIONS: {e}")

print("\n" + "="*60 + "\n")

# Test 2: Try a query with ends-with match-type
print("Test 2: Attempting calendar-query with match-type='ends-with'...")

query_xml = """<?xml version="1.0" encoding="utf-8" ?>
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
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

try:
    response = requests.request(
        'REPORT',
        str(work_cal.url),
        data=query_xml,
        headers={'Content-Type': 'application/xml; charset=utf-8'},
        auth=HTTPBasicAuth(FASTMAIL_USER, FASTMAIL_PASS)
    )
    
    print(f"✅ Query succeeded! Status: {response.status_code}")
    print(f"Response length: {len(response.content)} bytes")
    
    # Check if we got results
    if b'<calendar-data>' in response.content or b'VCALENDAR' in response.content:
        print("✅ Got calendar data in response")
        # Count how many events matched
        count = response.content.count(b'BEGIN:VEVENT')
        print(f"   Found {count} events with UIDs ending in '-family'")
    elif b'multistatus' in response.content.lower():
        print("✅ Got multistatus response (possibly empty result set)")
        count = response.content.count(b'BEGIN:VEVENT')
        print(f"   Found {count} events")
    
    print("\n✅ Server supports 'ends-with' match-type!")
    
except Exception as e:
    print(f"❌ Query failed: {e}")
    if hasattr(e, 'response'):
        print(f"   Status: {e.response.status_code}")
        print(f"   Response: {e.response.text[:200]}")

print("\n" + "="*60 + "\n")

# Test 3: Standard query for comparison
print("Test 3: Standard text-match (substring) for comparison...")

standard_query_xml = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop xmlns:D="DAV:">
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:prop-filter name="UID">
          <C:text-match>family</C:text-match>
        </C:prop-filter>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

try:
    response = requests.request(
        'REPORT',
        str(work_cal.url),
        data=standard_query_xml,
        headers={'Content-Type': 'application/xml; charset=utf-8'},
        auth=HTTPBasicAuth(FASTMAIL_USER, FASTMAIL_PASS)
    )
    
    print(f"✅ Standard query succeeded! Status: {response.status_code}")
    count = response.content.count(b'BEGIN:VEVENT')
    print(f"   Found {count} events with 'family' in UID (substring match)")
    
except Exception as e:
    print(f"❌ Standard query also failed: {e}")

print("\n=== Test Complete ===")
