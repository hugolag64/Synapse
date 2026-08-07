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
        self.credentials_path = "credentials.json"
        self.token_path = "token.json"

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
                    raise FileNotFoundError(f"File {self.credentials_path} not found. Please place it in the project root.")
                
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

    async def create_event(self, summary, start_time_iso, duration_minutes=60, description="", color_id=None, reminders=None):
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
        
        # Calendriers à interroger : primary + IDs configurés dans les paramètres
        from backend.config.settings import settings as _cfg
        configured_ids = _cfg.get_calendar_ids()
        seen_ids: set[str] = set()
        calendar_ids: list[str] = []
        for cid in ["primary"] + configured_ids:
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

calendar_service = GoogleCalendarService()
