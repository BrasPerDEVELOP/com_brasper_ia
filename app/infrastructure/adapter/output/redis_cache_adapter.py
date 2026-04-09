import redis
import json

class RedisCacheAdapter:
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    def get(self, key: str):
        value = self._redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value # Return as is if not json
        return None

    def save(self, key: str, data, ttl: int = 3600):
        if isinstance(data, dict) or isinstance(data, list):
            self._redis.set(key, json.dumps(data), ex=ttl)
        else:
            self._redis.set(key, data, ex=ttl)

    def save_hash(self, key: str, data: dict):
        cleaned_data = {k: v for k, v in data.items() if v is not None}
        if cleaned_data:
            self._redis.hset(key, mapping=cleaned_data)

    def get_hash(self, key: str) -> dict:
        return self._redis.hgetall(key)

    def add_to_set(self, set_key: str, value: str):
        self._redis.sadd(set_key, value)

    def get_set_intersection(self, set_keys: list[str]) -> set:
        if not set_keys:
            return set()
        return self._redis.sinter(set_keys)

    #mal planteada
    def get_all_project_ids(self) -> set:
        return self._redis.smembers("projects:all")

    def delete_keys_by_pattern(self, pattern: str):
        keys = self._redis.keys(pattern)
        if keys:
            self._redis.delete(*keys)

    def get_keys_by_pattern(self, pattern: str) -> list[str]:
        """Devuelve una lista de claves que coinciden con un patrón."""
        return self._redis.keys(pattern)

    def exists(self, key: str) -> bool:
        return self._redis.exists(key) > 0

    def delete(self, key: str):
        self._redis.delete(key)

    def get_project_id_by_name(self, project_name: str) -> str | None:
        """
        Finds a project ID by its name using a case-insensitive, partial match.

        This method iterates through all project IDs stored in the 'projects:all' set,
        fetches the hash for each project, and compares its 'name' field.

        Returns:
            The project ID if a match is found, otherwise None.
        """
        project_ids = self.get_all_project_ids()
        search_name_lower = project_name.strip().lower()
        for project_id in project_ids:
            project_data = self.get_hash(f"project:{project_id}")
            if project_data and search_name_lower in project_data.get("name", "").lower():
                return project_id
        return None
