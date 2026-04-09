class LeadUseCase():
    def __init__(self,lead_scoring_port):
        self.lead_scoring_port=lead_scoring_port
    def calculate(self,lead:dict)->int:
        score=self.lead_scoring_port.calculate_scoring(lead)
        level=self.get_level(score)
        
        return {"score":score,"level":level}
    
    def get_level(self,score:int)->str:
        if score>=15:
            return "Alto"
        elif score>=5:
            return "Medio"
        else:
            return "Bajo"
    