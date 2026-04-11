class Lead:

    def __init__(self, name: str, last: str, phone: str):

        if not name:
            raise ValueError("El nombre es obligatorio")

        if not last:
            raise ValueError("El apellido es obligatorio")

        if not phone:
            raise ValueError("El teléfono es obligatorio")

        self.name = name
        self.last = last
        self.phone = phone
        self.status = "nuevo"

    def mark_contacted(self):
        self.status = "contactado"