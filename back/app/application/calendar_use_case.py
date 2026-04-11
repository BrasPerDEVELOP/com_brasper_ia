from app.application.services.parser_time import ParserTime
from datetime import timedelta
class CalendarUseCase:
    def __init__(self,calendarport):
        self.calendarport=calendarport
        
    #def execute(self, date, time,email):
#
    #    start = ParserTime.build_datetime(date, time)
    #    end = start + timedelta(hours=1)
    #    summary = "Visita a proyecto inmobiliario"
    #    
    #    return self.calendarport.call_calendar(
    #        summary,
    #        start.isoformat(),
    #        end.isoformat(),
    #        email
    #    )
    def execute(self, args):
        summary = args.get("summary")
        start = args.get("start")
        end = args.get("end")

        attendees = args.get("attendees", [])
        email = attendees[0].get("email") if attendees else None

        if not email:
            raise ValueError("No se encontró email para el evento")
        return self.calendarport.call_calendar(
            summary,
            start,
            end,
            email
        )

    
    def execute_date(self)->str:
        response=self.calendarport.get_calendar()
        return response