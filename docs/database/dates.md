# Dates and time-like values

Scope: observed DB29, with semantic evidence P-DATE/P-RECURRENCE/P-STATUS. **INTEGER, REAL and a name ending in Date do not identify an epoch or timezone.** No user date values were sampled.

## Packed calendar days

The source-reviewed scoped task-date helper encodes a calendar day as:

```python
packed = (year << 16) | (month << 12) | (day << 7)
year = packed >> 16
month = (packed >> 12) & 15
day = (packed >> 7) & 31
```

The inspected helper requires a valid calendar date. Synthetic leap-day/year-boundary roundtrips of the extracted pure helper were executed for this documentation; no native helper was loaded. The formula is not epoch seconds. Incrementing a packed number is not a calendar operation; add days to a validated calendar date and repack. Reserved/unused low bits, invalid dates, sentinels and cross-version encodings need explicit handling rather than silent coercion.

| Field(s) | Evidence / confidence |
| --- | --- |
| TMTask.startDate, todayIndexReferenceDate | Observed/source-reviewed packed days in scoped rescheduling validator and test, P-DATE |
| rt1_instanceCreationStartDate, rt1_nextInstanceStartDate | Observed/source-reviewed packed days in narrow recurrence generation/creation checks, P-RECURRENCE |
| deadline, deadlineSuppressionDate, rt1_afterCompletionReferenceDate | Hypothesized calendar-day roles; DDL records integer conversions, but independent field-specific edge cases were not exercised |
| reminderTime | INTEGER declaration verified; encoding/zone/sentinel contract unknown here; do not decode with the day formula |
| t2_deadlineOffset | INTEGER declaration verified; unit, sign and inheritance rules unknown |

A null day is not the same as zero, an invalid packed day or a hidden/someday state. A scheduled task's UI visibility also depends on other state; a calendar value alone does not determine Today.

## Time-like REAL columns

Task/checklist creation, modification and stop fields are REAL. Reviewed private validators require finite positive values and relative temporal consistency in their supported operation scopes. That does **not** independently prove a Unix-versus-reference epoch for every REAL field. Native conversion/epoch verification was not performed here. Preserve the raw value until a field-specific contract is established. P-DATE, P-STATUS.

`lastReminderInteractionDate`, `repeaterMigrationDate`, tag `usedDate`, settings `manualLogDate`, and tombstone `deletionDate` are physically cataloged but have no verified conversion contract in this documentation. Recurrence plist values may encode their own time representation; do not apply the SQL packed-day decoder to every plist number.

## Timezone boundary

Do not derive a user's local calendar day by blindly truncating a UTC instant. Future date APIs need explicit timezone policy, DST/month/year/leap-boundary tests, and separate handling of calendar days, time-of-day reminders and absolute instants. The catalog does not certify such an API.
