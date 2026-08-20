import os.path
import datetime
import asyncio
import os
from backend.config.settings import business_today, get_app_timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarAuthError(RuntimeError):
    """Authentication failure that must be visible to the caller/UI."""


class GoogleCalendarService:
    def __init__(self):
        self.creds = None
        self.service = None
        secrets_dir = os.getenv("GOOGLE_CALENDAR_SECRETS_DIR", "google-secrets")
        self.credentials_path = os.path.join(secrets_dir, "credentials.json")
        self.token_path = os.path.join(secrets_dir, "token.json")

    def authenticate(self):
        """Authenticates the user and sets self.service. This handles the OAuth flow."""
        logger.info("Starting Google Calendar Authentication...")
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                logger.info("Loaded credentials from token.json")
            except Exception as e:
                logger.error(f"Failed to load token.json: {e}")
        
        if not creds or not creds.valid:
            logger.info("Credentials invalid or expired.")
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Attempting to refresh token...")
                    creds.refresh(Request())
                    logger.success("Token refreshed successfully.")
                except Exception as e:
                    logger.error(f"Error refreshing token: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    logger.error(f"File {self.credentials_path} not found.")
                    raise FileNotFoundError(
                        f"File {self.credentials_path} not found. "
                        "Place the Google OAuth client file in the configured secrets directory."
                    )
                
                logger.warning("Initiating local server for OAuth flow. Check browser!")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                # run_local_server opens a browser window for the user to log in
                creds = flow.run_local_server(port=0)
                logger.success("OAuth flow completed.")
            
            # Save the credentials for the next run
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())
            logger.info("Saved new credentials to token.json")

        self.creds = creds
        self.service = build("calendar", "v3", credentials=creds)
        logger.success("Google Calendar Service built successfully.")

    async def create_event(self, summary, start_time_iso, duration_minutes=60, description="", color_id=None, reminders=None, all_day=False):
        """Creates an event in the primary calendar. Thread-safe."""
        if not self.service:
            try:
                await asyncio.to_thread(self.authenticate)
            except Exception as error:
                logger.error(f"Authentication failed before event creation: {error}")
                raise GoogleCalendarAuthError(
                    f"Authentification Google Calendar échouée : {error}"
                ) from error

        # Handle start time
        if isinstance(start_time_iso, str):
            start = datetime.datetime.fromisoformat(start_time_iso)
        else:
            start = start_time_iso

        if all_day:
            start_date = start.date() if isinstance(start, datetime.datetime) else start
            end_date = start_date + datetime.timedelta(days=1)
            event = {
                "summary": summary,
                "description": description,
                "start": {"date": start_date.isoformat()},
                "end": {"date": end_date.isoformat()},
            }
        else:
            end = start + datetime.timedelta(minutes=duration_minutes)
            event = {
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": get_app_timezone().key,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": get_app_timezone().key,
                },
            }

        if color_id:
            event["colorId"] = color_id
            
        if reminders:
            event["reminders"] = reminders

        try:
            event_result = await asyncio.to_thread(
                lambda: self.service.events().insert(calendarId="primary", body=event).execute()
            )
            return event_result
        except HttpError as error:
            logger.error(f"Google Calendar HTTP error: {error}")
            return None
        except Exception as e:
            logger.error(f"Google Calendar unexpected error: {e}")
            return None
    
    async def get_events_for_day(self, date_obj: datetime.date = None):
        """Fetch events for a specific day from multiple calendars (Local Time 00:00-23:59)."""
        logger.info(f"Fetching calendar events for {date_obj}...")
        if not self.service:
            logger.info("Service not initialized, authenticating...")
            try:
                await asyncio.to_thread(self.authenticate)
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise GoogleCalendarAuthError(f"Authentification Google Calendar échouée : {e}") from e
            
        if date_obj is None:
            date_obj = business_today()

        # Time range: Start of day to End of day in the selected app timezone.
        app_timezone = get_app_timezone()
        start_dt = datetime.datetime.combine(date_obj, datetime.time.min, tzinfo=app_timezone)
        end_dt = datetime.datetime.combine(date_obj, datetime.time.max, tzinfo=app_timezone)
        
        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()
        
        # Calendriers à interroger : primary + IDs configurés (.env) + IDs configurés (Paramètres)
        from backend.config.settings import settings as _cfg
        from backend.state.store import data_store as _store
        from backend.core.planning.calendar_sources import (
            FAC_CALENDAR_ID,
            FAC_CALENDAR_LABEL,
            list_calendar_sources as _list_calendar_sources,
        )

        configured_ids = _cfg.get_calendar_ids()
        preference_sources = _list_calendar_sources(_store.preferences)
        source_labels: dict[str, str] = {FAC_CALENDAR_ID: FAC_CALENDAR_LABEL}
        source_labels.update({s["id"]: s["label"] for s in preference_sources if s["label"]})

        seen_ids: set[str] = set()
        calendar_ids: list[str] = []
        for cid in ["primary", FAC_CALENDAR_ID] + configured_ids + [s["id"] for s in preference_sources]:
            if cid not in seen_ids:
                seen_ids.add(cid)
                calendar_ids.append(cid)
        
        all_events = []
        
        async def fetch_calendar(cal_id):
            try:
                events_result = await asyncio.to_thread(
                    lambda: self.service.events().list(
                        calendarId=cal_id, 
                        timeMin=time_min, 
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                )
                items = events_result.get('items', [])

                label = source_labels.get(cal_id, "")
                for event in items:
                    event["_synapse_source_label"] = label
                    event["_synapse_calendar_id"] = cal_id

                # FIX: Apply +4h offset for "Agenda FAC" (User reported 4h early events)
                # ID: dm1rlvvim8vemcspm4momjq8f7qfqc3g@import.calendar.google.com
                if cal_id == 'dm1rlvvim8vemcspm4momjq8f7qfqc3g@import.calendar.google.com':
                    for event in items:
                        try:
                            # Start Time
                            if 'dateTime' in event.get('start', {}):
                                start_dt = datetime.datetime.fromisoformat(event['start']['dateTime'])
                                start_dt += datetime.timedelta(hours=4)
                                event['start']['dateTime'] = start_dt.isoformat()
                            
                            # End Time
                            if 'dateTime' in event.get('end', {}):
                                end_dt = datetime.datetime.fromisoformat(event['end']['dateTime'])
                                end_dt += datetime.timedelta(hours=4)
                                event['end']['dateTime'] = end_dt.isoformat()
                        except Exception as e:
                            logger.error(f"Error adjusting time for event {event.get('summary')}: {e}")
                            
                return items
            except Exception as e:
                logger.error(f"Error fetching calendar {cal_id}: {e}")
                return []

        # Fetch sequentially to avoid thread-safety issues with Google API client
        for cid in calendar_ids:
            res = await fetch_calendar(cid)
            all_events.extend(res)
            
        # Re-sort combined list by start time
        all_events.sort(key=lambda x: x['start'].get('dateTime', x['start'].get('date')))

        return all_events

    async def get_events_for_range(self, start_date: datetime.date, end_date: datetime.date) -> dict:
        """Comme get_events_for_day, mais sur toute une plage en un seul passage par
        calendrier (au lieu d'un appel par jour) — évite N requêtes réseau séquentielles
        quand l'appelant a besoin d'une semaine entière (cf. planning_cockpit.py)."""
        logger.info(f"Fetching calendar events for {start_date}..{end_date}...")
        if not self.service:
            logger.info("Service not initialized, authenticating...")
            try:
                await asyncio.to_thread(self.authenticate)
            except Exception as e:
                logger.error(f"Authentication failed: {e}")
                raise GoogleCalendarAuthError(f"Authentification Google Calendar échouée : {e}") from e

        app_timezone = get_app_timezone()
        start_dt = datetime.datetime.combine(start_date, datetime.time.min, tzinfo=app_timezone)
        end_dt = datetime.datetime.combine(end_date, datetime.time.max, tzinfo=app_timezone)
        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()

        from backend.config.settings import settings as _cfg
        from backend.state.store import data_store as _store
        from backend.core.planning.calendar_sources import (
            FAC_CALENDAR_ID,
            FAC_CALENDAR_LABEL,
            list_calendar_sources as _list_calendar_sources,
        )

        configured_ids = _cfg.get_calendar_ids()
        preference_sources = _list_calendar_sources(_store.preferences)
        source_labels: dict[str, str] = {FAC_CALENDAR_ID: FAC_CALENDAR_LABEL}
        source_labels.update({s["id"]: s["label"] for s in preference_sources if s["label"]})

        seen_ids: set[str] = set()
        calendar_ids: list[str] = []
        for cid in ["primary", FAC_CALENDAR_ID] + configured_ids + [s["id"] for s in preference_sources]:
            if cid not in seen_ids:
                seen_ids.add(cid)
                calendar_ids.append(cid)

        all_events: list[dict] = []

        async def fetch_calendar(cal_id):
            try:
                events_result = await asyncio.to_thread(
                    lambda: self.service.events().list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        singleEvents=True,
                        orderBy='startTime',
                    ).execute()
                )
                items = events_result.get('items', [])
                label = source_labels.get(cal_id, "")
                for event in items:
                    event["_synapse_source_label"] = label
                    event["_synapse_calendar_id"] = cal_id
                return items
            except Exception as e:
                logger.error(f"Error fetching calendar {cal_id}: {e}")
                return []

        # Même contrainte que get_events_for_day : séquentiel entre calendriers.
        for cid in calendar_ids:
            all_events.extend(await fetch_calendar(cid))

        from backend.core.prep.calendar_parser import event_start_date

        events_by_day: dict[datetime.date, list[dict]] = {
            start_date + datetime.timedelta(days=i): []
            for i in range((end_date - start_date).days + 1)
        }
        for event in all_events:
            day = event_start_date(event, app_timezone)
            if day in events_by_day:
                events_by_day[day].append(event)

        return events_by_day

calendar_service = GoogleCalendarService()
