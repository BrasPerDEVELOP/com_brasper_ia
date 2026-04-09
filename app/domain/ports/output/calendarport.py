from abc import abstractmethod,ABC

class CalendarPort(ABC):
    @abstractmethod
    def call_calendar(self)->str:
        pass
    
    def get_calendar(self)->str:
        pass