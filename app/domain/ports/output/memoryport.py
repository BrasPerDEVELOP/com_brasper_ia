from abc import ABC,abstractmethod

class MemoryPort(ABC):
    @abstractmethod
    def save_memory(self,user_id:str,memory:dict)->str:
        pass
    
    @abstractmethod
    def get_memory(self,user_id:str)->dict:
        pass
    
    @abstractmethod
    def get_memory_score(self,user_id)->dict:
        pass
    
    @abstractmethod
    def save_memory_score(self,user_id:str,memory:dict)->str:
        pass