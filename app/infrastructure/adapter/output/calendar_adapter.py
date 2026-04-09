from app.domain.ports.output.calendarport import CalendarPort
#lib para google calendar
import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]
#SCOPES_REONLY ["https://www.googleapis.com/auth/calendar.readonly"]
class CalendarAdapter(CalendarPort):
    def __init__(self):
        super().__init__()
        
    def call_calendar(self,summary,start,end,email):
        
        path_token=os.path.exists("token.json")
        
        creds=None
        if path_token:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())

                # GUARDAR TOKEN REFRESCADO
                with open("token.json", "w") as token:
                    token.write(creds.to_json())

            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=65451)

                with open("token.json", "w") as token:
                    token.write(creds.to_json())
        try:
            #return f"Se guardo la cita Cita: {summary} Fecha Inicio {start} Fecha salida {end}"
            event={
                "summary":summary,
                'start':{
                    "dateTime":start,
                    'timeZone':"America/Lima"
                },
                'end':{
                    "dateTime":end,
                    "timeZone":"America/Lima"
                },
                "attendees": [
                    {"email": email}
                ]
                
            }
            service = build("calendar", "v3", credentials=creds)

            # Call the Calendar API
            now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            
            event=service.events().insert(calendarId="primary",body=event,sendUpdates="all").execute()
            print("Google Calendar",event.get('htmlLink'))           
            print("ORGANIZER:", event.get("organizer"))
            return {"status": "created"}
        except HttpError as error:
            print(f"A ocurrido un error: {error}")
            return f"Error al crear el evento en Google Calendar: {error}. Es posible que el formato de fecha y hora sea incorrecto. Por favor, usa el formato YYYY-MM-DDTHH:MM:SS."

    def get_calendar(self):
        path_token=os.path.exists("token.json")
        if not path_token:
           return {"error": "No se encontró token.json para acceder a Google Calendar."}
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if path_token:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', "w") as token:
                token.write(creds.to_json())

        try:
            service = build("calendar", "v3", credentials=creds)

            # Call the Calendar API
            now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            #print("Getting the upcoming 10 events")
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                print("No se encontraron eventos.")
                return []
            #almacenar eventos disponibles
            all_event=[]
            # recorrer todos los eventos
            for event in events:
                start_data = event.get("start", {})
                start = start_data.get("dateTime", start_data.get("date"))
                all_event.append({
                    "summary": event.get("summary", "Evento sin titulo"),
                    "start": start,
                })
            #print(start, event["summary"])
            #retornar todos los eventos disponibles
            return all_event
        except HttpError as error:
            print(f"An error occurred: {error}")
            return {"error": f"Error al consultar Google Calendar: {error}"}

        
