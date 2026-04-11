from app.domain.ports.output.crmport import CRMPort

class CRMAdapter(CRMPort):
    def __init__(self):
        super().__init__()
    
    def save_lead(self, **lead_data):
        print (f"CRM FINAL: Se guardó/actualizó el lead con los siguientes datos: {lead_data}")