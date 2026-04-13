import redis.exceptions
import os
import httpx
import json
import unicodedata

ZEFIRON_USERNAME = os.getenv("ZEFIRON_USERNAME")
ZEFIRON_PASSWORD = os.getenv("ZEFIRON_PASSWORD")
AUTH_URL = "https://apitest.zefiron.com/auth/login/"
API_URL  = "https://apitest.zefiron.com/project/"
LOT_URL  = "https://apitest.zefiron.com/project/lot/general/?paginated=false"
UNITY_URL = "https://apitest.zefiron.com/project/unity/general/?paginated=false"

class CRMUseCase():
    def __init__(self,crm_port, cache_adapter):
       self.crm_port=crm_port
       self.cache_adapter=cache_adapter
       self.api_token = None

    def _normalize_string(self, s: str | None) -> str | None:
        """
        Normalizes a string by stripping whitespace, converting to uppercase,
        and removing accents. Returns None if input is None.
        """
        if s is None:
            return None
        if not isinstance(s, str):
            s = str(s) # Convert to string if it's not already
        s = s.strip().upper()
        return str(unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8'))

    def _get_auth_token(self):
        """Authenticates with Zefiron API and returns a token."""
        if self.api_token:
            return self.api_token

        try:
            with httpx.Client() as client:
                data = {
                    'username': ZEFIRON_USERNAME,
                    'password': ZEFIRON_PASSWORD
                }
                headers = {
                    'accept': 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
                response = client.post(AUTH_URL, data=data, headers=headers)
                response.raise_for_status()
                self.api_token = response.json().get("access_token")
                print("Successfully authenticated with Zefiron API.")
                return self.api_token
        except httpx.HTTPStatusError as e:
            print(f"Error during Zefiron authentication: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during authentication: {e}")
            return None

    def warm_up_projects_cache(self):
        """
        Fetches all projects from the Zefiron API and populates the Redis cache
        with a structured, indexed format.
        """
        print("Starting project cache warm-up...")
        token = self._get_auth_token()
        if not token:
            print("Could not warm up cache: failed to get auth token.")
            return

        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        try:
            with httpx.Client() as client:
                response = client.get(API_URL, headers=headers)
                response.raise_for_status()
                projects = response.json()

            if not isinstance(projects, list):
                print("Warm-up failed: API did not return a list of projects.")
                return

            self.cache_adapter.delete_keys_by_pattern("project:*")
            self.cache_adapter.delete_keys_by_pattern("projects:*")
            self.cache_adapter.delete_keys_by_pattern("projects:summary_list")

            processed_count = 0
            projects_summary = []
            for project in projects:
                # Filtrar proyectos eliminados o deshabilitados
                if project.get("deleted") is True or project.get("status") == "disabled":
                    continue

                if name := project.get("name"):
                    projects_summary.append({
                        "name": name,
                        "department": project.get("department"),
                        "project_type": project.get("type"),
                        "selling_price": project.get("selling_price"),
                    })

                if project_id := project.get("id"): # Asegurarse de que el proyecto tiene un ID
                    # Crear una copia para modificar y eliminar campos
                    project_to_cache = project.copy()

                    # Normalize department and type before caching in the hash
                    if 'department' in project_to_cache and project_to_cache['department'] is not None:
                        project_to_cache['department'] = self._normalize_string(project_to_cache['department'])
                    '''if 'type' in project_to_cache and project_to_cache['type'] is not None:
                        project_to_cache['type'] = self._normalize_string(project_to_cache['type'])'''


                    project_to_cache.pop("deleted", None) # Eliminar el campo 'deleted'
                    project_to_cache.pop("status", None)  # Eliminar el campo 'status'
                    project_to_cache.pop("code", None)
                    project_to_cache.pop("coin_symbol", None)
                    project_to_cache.pop("logo", None)
                    project_to_cache.pop("commercial_image", None)
                    project_to_cache.pop("max_discount_amount", None)
                    project_to_cache.pop("max_discount_percentage", None)
                    project_to_cache.pop("profitable amount", None)
                    project_to_cache.pop("urban_planning_type", None)
                    project_to_cache.pop("coin", None)
                    project_to_cache.pop("finantial", None)
                    project_to_cache.pop("proprietary", None)
                    project_to_cache.pop("social_reason", None)
                    project_to_cache.pop("created_at", None)
                    project_to_cache.pop("updated_at", None)
                    project_to_cache.pop("location", None)

                    self.cache_adapter.save_hash(f"project:{project_id}", project_to_cache)
                    self.cache_adapter.add_to_set("projects:all", project_id) # Añadir a un set de todos los IDs
                    if project_type := project_to_cache.get("type"): self.cache_adapter.add_to_set(f'projects:type:{project_type}', project_id)
                    if department := project_to_cache.get("department"): self.cache_adapter.add_to_set(f'projects:department:{department}', project_id)
                    processed_count += 1
            
            self.cache_adapter.save("projects:summary_list", projects_summary)
            print(f"Cache warm-up completo. {processed_count} proyectos indexados. Lista de resumen con {len(projects_summary)} proyectos creada.")
        except (redis.exceptions.ConnectionError, httpx.HTTPStatusError, Exception) as e:
            print(f"ERROR during cache warm-up: {e}")

    def save_lead_with_cache(self, lead_data: dict):
        phone = lead_data.get("phone")
        if not phone:
            # El teléfono es esencial para usarlo como ID de sesión.
            return "Falta el teléfono, que es clave para guardar el lead en caché."

        lead_key = f"lead:{phone}"
        session_key = f"session_timer:{phone}"
        session_ttl_seconds = 1800  # 30 minutos de inactividad

        try:
            existing_data = self.cache_adapter.get(lead_key) or {}
            existing_data.setdefault('sourceChannel', 'Digital')
            existing_data.setdefault('method', 'Chatbot')
            existing_data.setdefault('agent', 'Navia Chatbot')

            if lead_data.get("documentNumber"):
                if len(lead_data["documentNumber"]) == 8    : lead_data["documentType"] = "DNI"
                elif len(lead_data["documentNumber"]) == 9  : lead_data["documentType"] = "PASSPORT/CE"
                elif len(lead_data["documentNumber"]) == 11 : lead_data["documentType"] = "RUC"
                else                                        : lead_data["documentType"] = "UNKNOWN"
            # Filtrar valores vacíos de los nuevos datos para no sobreescribir data existente.
            clean_lead_data = {k: v for k, v in lead_data.items() if v}
            if lead_data.get("pending_handoff_prereq") is False:
                existing_data.pop("pending_handoff_prereq", None)
                clean_lead_data.pop("pending_handoff_prereq", None)
            existing_data.update(clean_lead_data)

            # 1. Guardar/actualizar los datos del lead sin TTL (persistente en Redis hasta el job)
            self.cache_adapter.save(lead_key, existing_data, ttl=None)
            # 2. Crear/refrescar el temporizador de sesión con TTL
            self.cache_adapter.save(session_key, "active", ttl=session_ttl_seconds)

            message = f"Datos del lead {existing_data.get('name')} actualizados en caché correctamente."
            print(message)
            #self.crm_port.save_lead(**existing_data)
            return message
        except redis.exceptions.ConnectionError as e:
            print(f"ERROR DE CACHÉ: No se pudo conectar a Redis. {e}")
            # En este nuevo modelo, si Redis falla, no podemos continuar.
            return "No se pudo actualizar la información en caché debido a un problema de conexión."

    def save_summary_with_cache(self, summary_data, id):
        self.cache_adapter.save(f"summary{id}", summary_data)

    def get_projects(self, args: dict):
        """
        Obtiene datos de proyectos desde la caché de Redis, usando filtros. Prioritiza
        una lista de resumen ligera si no se usan filtros complejos.
        """
        args = args or {}
        print(f"Getting projects with filters: {args}")
        try:
            # Intenta usar la lista de resumen primero, ya que es más ligera.
            summary_data = self.cache_adapter.get("projects:summary_list")
            if summary_data and not args.get("name"):
                print("Usando lista de resumen para obtener proyectos.")
                projects_summary = summary_data

                if department := args.get("department"):
                    normalized_department = self._normalize_string(department)
                    projects_summary = [p for p in projects_summary if self._normalize_string(p.get("department")) == normalized_department]

                if project_type := args.get("project_type"):
                    projects_summary = [p for p in projects_summary if p.get("project_type") == project_type]

                if (min_price := args.get("min_price")) is not None or (max_price := args.get("max_price")) is not None:
                    filtered_by_price = []
                    for project in projects_summary:
                        # Asegurarse de que el precio de venta no sea None antes de convertirlo a float
                        selling_price = float(project.get("selling_price") or 0)
                        if (min_price is None or selling_price >= float(min_price)) and \
                           (max_price is None or selling_price <= float(max_price)):
                            filtered_by_price.append(project)
                    projects_summary = filtered_by_price

                print(f"Se encontraron {len(projects_summary)} proyectos en la lista de resumen.")
                if projects_summary:
                    llm_hint = f"Se encontraron {len(projects_summary)} proyectos. Enuméralos para el usuario, mencionando que la lista coincide con sus filtros si los hubo. Menciónalos con comas(párrafo), no con 1. o bullets"
                    return {"projects": projects_summary, "llm_hint": llm_hint}
                else:
                    llm_hint = "No se encontraron proyectos que coincidan con la búsqueda. Informa al usuario y sugiérele intentar con otros filtros o ver todos los proyectos."
                    return {"projects": [], "llm_hint": llm_hint}

            print("Lista de resumen no encontrada en caché. Usando búsqueda completa.")
            # Lógica de búsqueda completa (si no se usó el resumen o no se encontró)
            filter_keys = []
            if project_type := args.get("project_type"): filter_keys.append(f'projects:type:{project_type}')
            if department := args.get("department"):
                normalized_department = self._normalize_string(department)
                if normalized_department: filter_keys.append(f'projects:department:{normalized_department}')

            project_ids = self.cache_adapter.get_set_intersection(filter_keys) if filter_keys else self.cache_adapter.get_all_project_ids()
            projects = [self.cache_adapter.get_hash(f"project:{pid}") for pid in project_ids]
            projects = [p for p in projects if p] # Filtrar nulos si un ID no tiene hash

            if (min_price := args.get("min_price")) is not None or (max_price := args.get("max_price")) is not None:
                projects = [p for p in projects if (min_price is None or float(p.get("selling_price", 0)) >= float(min_price)) and (max_price is None or float(p.get("selling_price", 0)) <= float(max_price))]

            '''if name_filter := args.get("name"):
                projects = [p for p in projects if name_filter.lower() in p.get("name", "").lower()]'''

            print(f"Se encontraron {len(projects)} proyectos que coinciden con los criterios.")
            if projects:
                llm_hint = f"Se encontraron {len(projects)} proyectos. Enuméralos para el usuario, mencionando que la lista coincide con sus filtros si los hubo."
                return {"projects": projects, "llm_hint": llm_hint}
            else:
                llm_hint = "No se encontraron proyectos que coincidan con la búsqueda. Informa al usuario y sugiérele intentar con otros filtros o ver todos los proyectos. Menciónalos con comas(párrafo), no con 1. o bullets"
                return {"projects": [], "llm_hint": llm_hint}
        except redis.exceptions.ConnectionError as e:
            print(f"ERROR DE CACHÉ: No se pudo conectar a Redis. {e}")
            return {"error": "No se pudieron obtener los proyectos debido a un problema con la caché."}
        except Exception as e:
            print(f"Ocurrió un error inesperado: {e}")
            return {"error": "Ocurrió un error inesperado al buscar los proyectos."}

    def get_project_details(self, args: dict):
        """
        Obtiene los detalles de un proyecto específico por su nombre,
        y agrega un resumen de sus lotes o unidades disponibles.
        """
        args = args or {}
        project_name = args.get("name")
        if not project_name:
            return {"error": "El nombre del proyecto es requerido para obtener detalles."}

        try:
            project_id = self.cache_adapter.get_project_id_by_name(project_name)
            if not project_id:
                return {"project": None, "error": f"No se encontró ningún proyecto que coincida con '{project_name}'."}

            project_details = self.cache_adapter.get_hash(f"project:{project_id}")
            if not project_details:
                return {"project": None, "error": f"Se encontró el ID del proyecto pero no sus detalles en caché para '{project_name}'."}

            project_type = project_details.get("type")
            sub_units, sub_unit_type_plural = [], None
            if project_type == 'urbanPlanning':
                sub_unit_type_plural = "lotes"
                sub_units_data = self.get_lots({"project_id": project_id, "lot_status": "enabled"})
                sub_units = sub_units_data.get("lots", [])
            elif project_type == 'building':
                sub_unit_type_plural = "unidades"
                sub_units_data = self.get_unities({"project_id": project_id, "unity_status": "enabled"})
                sub_units = sub_units_data.get("unities", [])

            if sub_units:
                prices = [float(u["selling_price"]) for u in sub_units if u.get("selling_price") is not None]
                areas = [float(u["lot_area"]) for u in sub_units if u.get("lot_area") is not None] if project_type == 'urbanPlanning' else [float(u["unity_area"]) for u in sub_units if u.get("unity_area") is not None]
                phase_indexes = sorted(list(set(u.get("phase_index") for u in sub_units if u.get("phase_index") is not None)))

                summary_data = {
                    "available_units_count": len(sub_units),
                    "units_average_price": round(sum(prices) / len(prices), 2) if prices else 0,
                    "units_average_area": round(sum(areas) / len(areas), 2) if areas else 0,
                    "units_phase_indexes": phase_indexes,
                    "units_type": sub_unit_type_plural
                }
                project_details.update(summary_data)
                project_details["llm_hint"] = f"Si el usuario quiere más detalles de los que tienens aquí o estás repitiendo los mismos datos varias veces, indícale que para más detalles agende una cita o se comunique con un asesor al número 986532564."
            else:
                project_details.update({ "available_units_count": 0, "units_message": f"No se encontraron {sub_unit_type_plural or 'unidades/lotes'} disponibles para este proyecto." })
                project_details["llm_hint"] = f"Informa al usuario que por el momento no se encontraron unidades o lotes disponibles para el proyecto '{project_details.get('name', 'este proyecto')}', pero que puede consultar por otros proyectos."
            print("DETAILS PROJECT", project_details)
            return {"project": project_details}
        except redis.exceptions.ConnectionError as e:
            print(f"ERROR DE CACHÉ en get_project_details: {e}")
            return {"error": "No se pudieron obtener los detalles del proyecto debido a un problema con la caché."}
        except Exception as e:
            print(f"Ocurrió un error inesperado en get_project_details: {e}")
            return {"error": "Ocurrió un error inesperado al buscar los detalles del proyecto."}

    def get_projectId_from_name(self, args: dict):
        """
        Obtiene el ID de un proyecto por su nombre.
        """
        args = args or {}
        print(f"Getting project ID from name: {args}")
        try:
            project_name = args.get("name")
            if not project_name:
                return {"error": "El nombre del proyecto es requerido."}
            project_id = self.cache_adapter.get_project_id_by_name(project_name)
            if not project_id:
                return {"error": "No se encontró un proyecto con ese nombre."}
            return {"project_id": project_id}
        except Exception as e:
            print(f"ERROR during project ID fetch: {e}")
            return {"error": "Ocurrió un error inesperado al obtener el ID del proyecto."}

    def get_lots(self, args: dict):
        """
        Fetches lots from the Zefiron API using filters.
        """
        args = args or {}
        print(f"Fetching lots from API with filters: {args}")
        token = self._get_auth_token()
        if not token:
            return {"error": "No se pudo obtener el token de autenticación."}
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        params = {'paginated': 'false'}
        if 'project_id' not in args:
            return {"error": "El 'project_id' es requerido para buscar lotes."}
        params.update(args)
        try:
            with httpx.Client() as client:
                response = client.get(LOT_URL, headers=headers, params=params)
                response.raise_for_status()
                lots = response.json()
                print(f"Found {len(lots)} lots from API.")
                return {"lots": lots}
        except httpx.HTTPStatusError as e:
            print(f"ERROR during lot fetch: {e.response.status_code} - {e.response.text}")
            return {"error": f"Error al obtener los lotes de la API: {e.response.text}"}
        except Exception as e:
            print(f"ERROR during lot fetch: {e}")
            return {"error": "Ocurrió un error inesperado al buscar los lotes."}

    def get_unities(self, args: dict):
        """
        Fetches unities from the Zefiron API using filters.
        """
        args = args or {}
        print(f"Fetching unities from API with filters: {args}")
        token = self._get_auth_token()
        if not token:
            return {"error": "No se pudo obtener el token de autenticación."}
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        params = {'paginated': 'false'}
        if 'project_id' not in args:
            return {"error": "El 'project_id' es requerido para buscar unidades."}
        params.update(args)
        try:
            with httpx.Client() as client:
                response = client.get(UNITY_URL, headers=headers, params=params)
                response.raise_for_status()
                unities = response.json()
                print(f"Found {len(unities)} unities from API.")
                return {"unities": unities}
        except httpx.HTTPStatusError as e:
            print(f"ERROR during unity fetch: {e.response.status_code} - {e.response.text}")
            return {"error": f"Error al obtener las unidades de la API: {e.response.text}"}
        except Exception as e:
            print(f"ERROR during unity fetch: {e}")
            return {"error": "Ocurrió un error inesperado al buscar las unidades."}
