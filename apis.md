# Carriage Dynamics — API Reference

All calls target the **Microsoft Dynamics 365 Web API**.

**Base URL:** `{DYNAMICS_API_URL}/api/data/v9.2`  
**Auth:** OAuth2 Client Credentials (MSAL) → `https://login.microsoftonline.com/{DYNAMICS_TENANT_ID}`  
**Headers (all requests):**
```
Authorization: Bearer <token>
OData-MaxVersion: 4.0
OData-Version: 4.0
```

> **Note:** All calls are gated behind the `DYNAMICS_ERP_BOOKING=true` env var. Disabled by default.

---

## Endpoints

### 1. Get Lead Details
**`GET /leads({lead_id})?$select=fullname,emailaddress1,_ownerid_value`**

Fetches the lead's name, email, and owner (assigned user GUID) at the start of a conversation.

| Field | Description |
|---|---|
| `fullname` | Lead's full name |
| `emailaddress1` | Lead's email address |
| `_ownerid_value` | GUID of the assigned systemuser (used as `calendar_id`) |

---

### 2. Get Lead Owner ID
**`GET /leads({lead_id})?$select=_ownerid_value`**

Fetches only the owner GUID for a lead. Used to resolve which calendar to query for availability.

---

### 3. Search Resource Availability *(Primary)*
**`POST /msdyn_SearchResourceAvailability`**

Calls the Field Service API to get open time slots for a resource. Falls back to endpoint #4 if unavailable.

**Body:**
```json
{
  "Version": "1",
  "Requirement": {
    "msdyn_fromdate": "<ISO datetime>",
    "msdyn_todate": "<ISO datetime>",
    "msdyn_remainingduration": <minutes>,
    "msdyn_duration": <minutes>
  },
  "Settings": {
    "ConsiderSlotsWithProposedBookings": false,
    "ConsiderTravelTime": false
  },
  "ResourceSpecification": {
    "ResourceIds": ["<calendar_id>"]
  }
}
```

**Response:** `TimeSlots[]` with `StartTime` per available slot.

---

### 4. Get Appointments *(Fallback for availability)*
**`GET /appointments?$select=scheduledstart,scheduledend&$filter=_ownerid_value eq {id} and scheduledstart ge {start} and scheduledend le {end}`**

Fetches existing appointments for an owner in a date range. Free slots are calculated locally from the busy intervals.

---

### 5. Create Appointment
**`POST /appointments`**

Books a new appointment in Dynamics 365.

**Body:**
```json
{
  "subject": "<subject>",
  "scheduledstart": "<ISO datetime>",
  "scheduledend": "<ISO datetime>",
  "ownerid@odata.bind": "/systemusers(<calendar_id>)"
}
```

**Success:** `204 No Content` — `OData-EntityId` header contains the new appointment URL/ID.  
**Conflict:** `400 Bad Request` → raises `SlotUnavailableError`.

---

### 6. Delete Appointment
**`DELETE /appointments({event_id})`**

Deletes an appointment by ID (used for cancellations/cleanup).

**Success:** `204 No Content`

---

## Source

All calls are implemented in [`src/zeta_voice/calendar/provider.py`](src/zeta_voice/calendar/provider.py) via `DynamicsCalendarProvider`.
