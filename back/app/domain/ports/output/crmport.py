from abc import ABC,abstractmethod

class CRMPort(ABC):
    @abstractmethod
    def save_lead(self,name:str,last:str,phone:str)->str:
        pass
    
    