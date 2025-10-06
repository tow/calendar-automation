# Calendar Sync Automation

Automatically sync "busy" events from one calendar to another, keeping your availability up-to-date across multiple calendars.

## Overview

This tool syncs busy events from a work calendar to a family calendar, creating placeholder "Busy" entries so others can see when you're unavailable without revealing meeting details.

**Key Features:**
- ✅ Syncs only OPAQUE (busy) events, ignores TRANSPARENT (free) events
- ✅ Incremental sync using CalDAV sync tokens (efficient, fast)
- ✅ Atomic operations with automatic rollback on failure
- ✅ Handles all event types: recurring, all-day, multi-day, point events
- ✅ Idempotent operations - safe to re-run
- ✅ State corruption recovery

## Requirements

- Python 3.9+
- Fastmail account (or other CalDAV-compatible server)
- Two calendars: source (work) and destination (family)

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd calendar-automation
```

2. Install dependencies:
```bash
pip install caldav icalendar
```

## Configuration

Set the following environment variables:

```bash
export FASTMAIL_URL="https://caldav.fastmail.com/dav/"
export FASTMAIL_USER="your-email@example.com"
export FASTMAIL_PASS="your-app-password"  # Generate in Fastmail settings
export WORK_CAL_NAME="Work"
export FAMILY_CAL_NAME="Family"
```

**Security Note:** Use Fastmail app-specific passwords, not your main account password.

## Usage

### Stateful Mode (Default - Recommended for Frequent Syncs)

Uses sync tokens for efficient delta syncs and maintains a state file.

```bash
python sync_calendar.py
```

**Advantages:**
- ✅ Efficient - only fetches changed events
- ✅ Fast - minimal network requests
- ✅ Ideal for frequent syncs (every 5-15 minutes)

**Requirements:**
- Persistent storage for `calendar_sync_state.json`

### Stateless Mode (Ideal for Serverless/Containers)

No state file needed - compares full calendar state each time.

```bash
python sync_calendar.py --stateless
```

**Advantages:**
- ✅ No persistent storage required
- ✅ Self-healing - automatically fixes inconsistencies
- ✅ Perfect for Lambda, Docker, Kubernetes
- ✅ Uses CalDAV extended query (efficient UID filtering)

**Trade-offs:**
- ⚠️ Fetches all events each time (2 full calendar queries)
- ⚠️ Slower than stateful for large calendars

### Automated Sync (Recommended)

Set up a cron job to run every 15 minutes:

```bash
# Edit crontab
crontab -e

# Stateful mode:
*/15 * * * * /path/to/python /path/to/sync_calendar.py

# Or stateless mode:
*/15 * * * * /path/to/python /path/to/sync_calendar.py --stateless
```

Or use a systemd timer, GitHub Actions workflow, or other scheduler.

## How It Works

### Stateful Mode (Default)

1. **Connect** to source (work) and destination (family) calendars via CalDAV
2. **Fetch** changed events since last sync using sync tokens (delta sync)
3. **Filter** for OPAQUE (busy) events only
4. **Create/Update/Delete** corresponding "Busy" placeholder events in family calendar
5. **Save** sync state atomically to prevent corruption

### Stateless Mode (`--stateless`)

1. **Connect** to both calendars via CalDAV
2. **Fetch all busy events** from work calendar
3. **Fetch managed events** from family calendar (using `match-type="ends-with"` filter for UIDs ending in `-family`)
4. **Compare states** to determine what needs to be created/updated/deleted
5. **Execute operations** - no state file needed

### Event Handling

| Work Calendar Event | Action in Family Calendar |
|---------------------|---------------------------|
| New busy event | Create "Busy" placeholder |
| Busy event modified | Update placeholder times |
| Busy event deleted | Delete placeholder |
| Event changes to free (TRANSPARENT) | Delete placeholder |
| Event changes to busy (OPAQUE) | Create placeholder |

### Supported Event Types

- ✅ **Time formats:** DTEND, DURATION, point events (no end time)
- ✅ **Date types:** All-day, multi-day, timed events
- ✅ **Recurring events:** RRULE, EXDATE, RECURRENCE-ID
- ✅ **Timezones:** UTC, TZID, floating times

## State Management

The sync state is stored in `calendar_sync_state.json`:

```json
{
  "sync_token": "a1b2c3d4...",
  "event_map": {
    "work-event-uid": "family-event-uid",
    ...
  }
}
```

- **sync_token**: CalDAV sync token for incremental syncs
- **event_map**: Maps work event UIDs to family calendar UIDs

**Corruption Recovery:** If the state file is corrupted, the tool automatically resets to a fresh sync.

## Testing

The project includes a comprehensive test suite with 40 tests covering:
- Event parsing (all types and formats)
- Recurring events
- Deletion detection
- Atomicity and error handling
- Stateful and stateless sync modes
- Full sync workflow

### Run Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=sync_calendar --cov-report=term-missing

# Run specific test files
python -m pytest tests/test_recurring_events.py -v
python -m pytest tests/test_atomicity.py -v
python -m pytest tests/test_stateless_sync.py -v
```

**Test Coverage:** 60% (core logic 100%, untested code is mostly integration glue)

**Test Count:** 40 tests, 100% passing

See `tests/README.md` for detailed test documentation.

## Troubleshooting

### No events syncing

1. Check that TRANSP is set to OPAQUE (or absent) on work events
2. Verify calendar names match exactly
3. Check Fastmail credentials and app password

### State file corruption

**Stateful mode:** Delete `calendar_sync_state.json` to reset. Next sync will be a full sync.

**Stateless mode:** Not applicable - no state file used.

### Duplicate events

The sync is idempotent - safe to re-run. If you see duplicates, check for multiple sync processes running simultaneously.

### Stateless mode recommendations

- Use stateless mode for serverless/container deployments
- For calendars with 100+ events, stateful mode may be faster
- Stateless mode requires CalDAV extended query support (Fastmail ✅ supported)

## Architecture

```
┌─────────────┐          ┌──────────────┐
│   Work      │          │   Family     │
│  Calendar   │          │  Calendar    │
│  (Fastmail) │          │  (Fastmail)  │
└──────┬──────┘          └──────▲───────┘
       │                        │
       │ CalDAV                 │ CalDAV
       │ (sync token)           │ (save/delete)
       │                        │
       └────────┬───────────────┘
                │
        ┌───────▼────────┐
        │  sync_calendar │
        │      .py       │
        └───────┬────────┘
                │
        ┌───────▼────────┐
        │  state.json    │
        │  (sync token + │
        │   event map)   │
        └────────────────┘
```

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please ensure all tests pass before submitting:

```bash
python -m pytest tests/ -v
```

## Development

### Project Structure

```
calendar-automation/
├── sync_calendar.py           # Main sync application
├── LICENSE                    # GPL-3.0 license
├── README.md                  # This file
├── tests/
│   ├── README.md              # Test documentation
│   ├── mock_caldav.py         # Mock CalDAV server
│   ├── test_sync_calendar.py  # Unit tests
│   ├── test_recurring_events.py
│   ├── test_atomicity.py
│   ├── test_sync_integration.py
│   ├── test_fixed_code.py
│   ├── test_real_fastmail.py  # Real Fastmail validation
│   └── tools/                 # Development tools
│       ├── fastmail_study.py
│       └── create_test_events.py
└── calendar_sync_state.json   # Sync state (created on first run)
```

### Adding Tests

See `tests/README.md` for patterns and guidelines.

## Acknowledgments

- Built for Fastmail CalDAV compatibility
- Uses [caldav](https://github.com/python-caldav/caldav) Python library
- Uses [icalendar](https://github.com/collective/icalendar) for event parsing

## Support

For issues, questions, or feature requests, please open an issue on GitHub.
