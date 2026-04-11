from app.domain.ports.output.leadScoringport import LeadScoringPort
class LeadScoringAdapter(LeadScoringPort):
    def __init__(self):
        self.lead_score={
            "destination_currency":5,
            "send_amount":6,
            "origin_currency":4,
            "phone":4,
            "urgency":10,
            }
        self.intent={
                "greeting":0,
                "remittance_requirements":4,
                "collect_contact":6,
                "human_handoff":8,
                "remittance_quote":15,
                }

        super().__init__()
    # scoring automstico
    def calculate_scoring(self, lead:dict)->int:
        scoring=0
        intent_detect=lead.get("intent")
        print("lead completo",lead)
        print("INTECION",intent_detect)
        # recorrer datos potenciales
        for field,weight in self.lead_score.items():
            if lead.get(field):
                scoring+= weight
        # detectar intecion
        #for intent in intent_detect:
        #agendar cita solo si se tienen los campos
        if intent_detect == "remittance_quote" and (
            lead.get("origin_currency") or lead.get("send_amount")
        ):
            scoring += self.intent.get(intent_detect,0)
        
        #scoring+=self.intent.get(intent_detect,0)
                       
        return scoring
