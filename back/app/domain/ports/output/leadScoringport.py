from abc import abstractmethod,ABC

class LeadScoringPort(ABC):
    @abstractmethod
    def calculate_scoring(self,lead:dict)->int:
        pass
    