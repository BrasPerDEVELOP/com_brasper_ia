import sys
import os
import redis
import time

from app.infrastructure.redis_connection import redis_from_env
from app.infrastructure.adapter.output.redis_cache_adapter import RedisCacheAdapter
from app.infrastructure.adapter.output.crm_adapter import CRMAdapter
from app.domain.ports.output.crmport import CRMPort

def main():
    """
    Job para persistir leads desde Redis a la base de datos final.
    Este script está diseñado para ser ejecutado periódicamente (e.g., cada 5 minutos vía cron).
    """
    print(f"[{time.ctime()}] Iniciando job de persistencia de leads...")

    try:
        # 1. Configurar conexiones
        redis_client = redis_from_env()
        cache_adapter = RedisCacheAdapter(redis_client)
        crm_adapter: CRMPort = CRMAdapter() # Usamos el puerto para desacoplar

        # 2. Obtener todos los leads en caché
        lead_keys = cache_adapter.get_keys_by_pattern("lead:*")
        print(f"Se encontraron {len(lead_keys)} leads potenciales en caché.")

        processed_leads = 0
        for lead_key in lead_keys:
            # Extraer el ID (número de teléfono) de la clave
            user_id = lead_key.split(':')[-1]
            session_key = f"session_timer:{user_id}"

            # 3. Comprobar si la sesión ha expirado (si la clave de sesión NO existe)
            if not cache_adapter.exists(session_key):
                print(f"Sesión expirada para el usuario {user_id}. Procesando para persistencia.")

                # 4. Obtener los datos del lead
                lead_data = cache_adapter.get(lead_key)

                if not lead_data or not isinstance(lead_data, dict):
                    print(f"  - ADVERTENCIA: No se encontraron datos válidos para la clave {lead_key}. Omitiendo y limpiando.")
                    cache_adapter.delete(lead_key)
                    continue

                try:
                    # 5. Persistir en la base de datos final
                    crm_adapter.save_lead(**lead_data)
                    print(f"  - ÉXITO: Lead para {user_id} (Nombre: {lead_data.get('name', 'N/A')}) guardado en el CRM final.")

                    # 6. Limpiar la clave del lead de Redis para no volver a procesarla
                    cache_adapter.delete(lead_key)
                    processed_leads += 1

                except Exception as e:
                    print(f"  - ERROR: Falló el guardado en el CRM final para el lead {user_id}. Error: {e}")

        print(f"[{time.ctime()}] Job finalizado. {processed_leads} leads fueron persistidos.")

    except redis.exceptions.ConnectionError as e:
        print(f"[{time.ctime()}] ERROR CRÍTICO: No se pudo conectar a Redis. Abortando job. Error: {e}")
    except Exception as e:
        print(f"[{time.ctime()}] ERROR INESPERADO en el job: {e}")

if __name__ == "__main__":
    main()
