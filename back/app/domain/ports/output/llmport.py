from abc import ABC,abstractmethod

class LLMPort(ABC):
    @abstractmethod
    def generate_response(self,promp:str,memory:list=None)->str:
        pass

    @abstractmethod
    def extract(self,text:str)->dict:
        pass

    @abstractmethod
    def generate_summary(self,text:str)->str:
        pass

    @abstractmethod
    def extract_intent(self,messages:str)->dict:
        pass            

