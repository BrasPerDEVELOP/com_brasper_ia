from app.application.chat_models import FeatureResult


class ResponseBuilder:
    def build(self, result: FeatureResult) -> str:
        message = (result.message or "").strip()
        if message:
            return message
        return "Puedo ayudarte con cotizaciones Brasper, cupones activos y derivación con un asesor."
