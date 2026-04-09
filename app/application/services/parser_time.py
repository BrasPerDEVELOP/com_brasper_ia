from datetime import datetime,timedelta
import dateparser
class ParserTime():
    @staticmethod
    def build_datetime(date_str, time_str):

        date_time = f"{date_str} {time_str}"
        dt = dateparser.parse(date_time,languages=["es"])
        print("hora devolvida",dt)
        return dt
