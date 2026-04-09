from app.domain.ports.output.memoryport import MemoryPort
class MemoryAdapter(MemoryPort):
    def __init__(self):
        self._storage={}
        self.score_storage={}
        self.lead_profile_storage={}
        super().__init__()
    #memoria conversacional
    def save_memory(self,user_id:str,memory:list)->str:
        print(f"Se guardo la memoria {memory}")
        if user_id not in self._storage:
            self._storage[user_id]=[]
            print("Se creo el storage")
            print(self._storage)
        #  guardar nuevos mensajes
        self._storage[user_id].extend(memory)

        #  limitar memoria 10 mensajes     
        self._storage[user_id] = self._storage[user_id][-10:]
        #print("Memoria actualizada: ",self._storage[user_id])
        #print("Memoria completa")
        #print("Memoria completa")
        #print("Memoria completa")
        #print(self._storage)
        return "okay"
     #obtener memoria conversacional
    def get_memory(self,user_id:str):
        return self._storage.get(user_id,[])
    # memoria score
    def save_memory_score(self, user_id:str, memory:dict):
        print(f"Se guardo la memoria del score {memory}")
        #Busca si existe una coincidencia
        if user_id not in self.score_storage:
            self.score_storage[user_id]={"score":0}
        #prev_score= self.score_storage[user_id]["score"]
        #new_score= prev_score + memory["score"]
        
        #print("Memoria score",new_score)
        
        self.score_storage[user_id]={
            "score":memory["score"]
        }
        #print("Memoria score adapter",self.score_storage)
        return {"status":"ok"}
    #obtener memoria score
    def get_memory_score(self, user_id:str):
        return self.score_storage.get(user_id,{"score":0})
    # obtener memoria bullets
    def get_memory_lead(self,user_id:str):
        return self.lead_profile_storage.get(user_id,
               {"language":None,
                "destination_currency":None,
                "send_amount":None,
                "origin_currency":None,
                "urgency":None})
    # memoria bullets importantes
    def save_memory_lead(self,user_id:str,memory:dict):
        if user_id not in self.lead_profile_storage:
            self.lead_profile_storage[user_id]={
                "language":None,
                "destination_currency":None,
                "send_amount":None,
                "origin_currency":None,
                "urgency":None}
            print("Memoria Lead",self.lead_profile_storage)
        
        profile=self.lead_profile_storage[user_id]
        for key in["language","destination_currency","send_amount","origin_currency","urgency"]:
            if memory.get(key) is not None:
                profile[key]=memory[key]
        print("Memoria lead profile",profile)
        return {"status":"ok"}
