"""
Optimisations de performance pour Orbi.
Index MongoDB, cache Redis avancé, connection pooling.
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

from beanie import Document, Indexed
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis

from src.core.config import get_settings
from src.core.redis import get_redis


class PerformanceOptimizer:
    """Optimiseur de performance pour Orbi."""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis = None  # Sera initialisé plus tard
    
    async def create_indexes(self) -> None:
        """Crée les index MongoDB optimisés."""
        from src.core.database import get_database
        
        db = get_database()
        
        # Index pour les utilisateurs
        await db.users.create_index([("telegram_id", 1)], unique=True)
        await db.users.create_index([("role", 1)])
        await db.users.create_index([("is_banned", 1)])
        await db.users.create_index([("created_at", -1)])
        
        # Index pour les tickets
        await db.tickets.create_index([("ticket_id", 1)], unique=True)
        await db.tickets.create_index([("user_telegram_id", 1)])
        await db.tickets.create_index([("status", 1)])
        await db.tickets.create_index([("priority", 1)])
        await db.tickets.create_index([("created_at", -1)])
        await db.tickets.create_index([("sla_deadline", 1)])
        await db.tickets.create_index([
            ("status", 1), 
            ("priority", 1), 
            ("sla_deadline", 1)
        ])
        
        # Index pour les commandes
        await db.orders.create_index([("order_id", 1)], unique=True)
        await db.orders.create_index([("user_telegram_id", 1)])
        await db.orders.create_index([("status", 1)])
        await db.orders.create_index([("created_at", -1)])
        await db.orders.create_index([("payment_provider", 1)])
        
        # Index pour les produits
        await db.products.create_index([("category", 1)])
        await db.products.create_index([("is_active", 1)])
        await db.products.create_index([("stock", 1)])
        await db.products.create_index([
            ("is_active", 1), 
            ("category", 1), 
            ("stock", 1)
        ])
        
        # Index pour les sondages
        await db.polls.create_index([("group_chat_id", 1)])
        await db.polls.create_index([("creator_telegram_id", 1)])
        await db.polls.create_index([("is_closed", 1)])
        await db.polls.create_index([("close_at", 1)])
        
        # Index pour les tâches
        await db.tasks.create_index([("user_telegram_id", 1)])
        await db.tasks.create_index([("status", 1)])
        await db.tasks.create_index([("due_date", 1)])
        await db.tasks.create_index([
            ("user_telegram_id", 1), 
            ("status", 1), 
            ("due_date", 1)
        ])
        
        # Index pour les logs
        await db.api_request_logs.create_index([("api_key_prefix", 1)])
        await db.api_request_logs.create_index([("created_at", -1)])
        await db.error_logs.create_index([("service", 1)])
        await db.error_logs.create_index([("is_resolved", 1)])
        await db.error_logs.create_index([("occurred_at", -1)])
    
    async def optimize_connection_pooling(self) -> None:
        """Optimise les connection pools MongoDB et Redis."""
        settings = get_settings()
        
        # MongoDB connection pooling optimisé
        self.mongo_client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            maxPoolSize=50,  # Augmenté pour plus de concurrence
            minPoolSize=5,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            retryWrites=True,
            w="majority"
        )
        
        # Redis connection pooling optimisé
        self.redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=50,  # Augmenté
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=True
        )


class CacheManager:
    """Gestionnaire de cache avancé avec Redis."""
    
    def __init__(self):
        self.redis = None  # Sera initialisé plus tard
        self.default_ttl = 300  # 5 minutes
    
    async def get_cached_user(self, telegram_id: int) -> Optional[Dict]:
        """Récupère un utilisateur depuis le cache."""
        key = f"user:{telegram_id}"
        cached = await self.redis.hgetall(key)
        return cached if cached else None
    
    async def cache_user(self, user_data: Dict, ttl: int = 300) -> None:
        """Met en cache un utilisateur."""
        key = f"user:{user_data['telegram_id']}"
        await self.redis.hset(key, mapping=user_data)
        await self.redis.expire(key, ttl)
    
    async def invalidate_user_cache(self, telegram_id: int) -> None:
        """Invalide le cache d'un utilisateur."""
        key = f"user:{telegram_id}"
        await self.redis.delete(key)
    
    async def get_cached_catalog(self, category: Optional[str] = None, page: int = 0) -> Optional[List]:
        """Récupère le catalogue depuis le cache."""
        key = f"catalog:{category or 'all'}:{page}"
        cached = await self.redis.get(key)
        return eval(cached) if cached else None
    
    async def cache_catalog(self, products: List, category: Optional[str] = None, page: int = 0, ttl: int = 300) -> None:
        """Met en cache le catalogue."""
        key = f"catalog:{category or 'all'}:{page}"
        await self.redis.set(key, str(products), ex=ttl)
    
    async def get_cached_stats(self, user_id: int) -> Optional[Dict]:
        """Récupère les statistiques utilisateur depuis le cache."""
        key = f"stats:{user_id}"
        cached = await self.redis.hgetall(key)
        return cached if cached else None
    
    async def cache_stats(self, user_id: int, stats: Dict, ttl: int = 600) -> None:
        """Met en cache les statistiques utilisateur."""
        key = f"stats:{user_id}"
        await self.redis.hset(key, mapping=stats)
        await self.redis.expire(key, ttl)
    
    async def rate_limit_check(self, user_id: int, limit: int = 30, window: int = 60) -> bool:
        """Vérifie le rate limiting avec sliding window."""
        key = f"rate_limit:{user_id}"
        current_time = datetime.now(timezone.utc).timestamp()
        
        # Nettoyer les anciennes entrées
        await self.redis.zremrangebyscore(key, 0, current_time - window)
        
        # Compter les requêtes dans la fenêtre
        request_count = await self.redis.zcard(key)
        
        if request_count >= limit:
            return False
        
        # Ajouter la requête actuelle
        await self.redis.zadd(key, {str(current_time): current_time})
        await self.redis.expire(key, window)
        
        return True
    
    async def cache_session_data(self, session_id: str, data: Dict, ttl: int = 1800) -> None:
        """Met en cache les données de session (panier, etc.)."""
        key = f"session:{session_id}"
        await self.redis.hset(key, mapping=data)
        await self.redis.expire(key, ttl)
    
    async def get_session_data(self, session_id: str) -> Optional[Dict]:
        """Récupère les données de session."""
        key = f"session:{session_id}"
        cached = await self.redis.hgetall(key)
        return cached if cached else None
    
    async def invalidate_session(self, session_id: str) -> None:
        """Invalide une session."""
        key = f"session:{session_id}"
        await self.redis.delete(key)


class QueryOptimizer:
    """Optimiseur de requêtes MongoDB."""
    
    @staticmethod
    def optimize_user_query(filters: Dict) -> Dict:
        """Optimise les requêtes utilisateur."""
        # Ajout de projections pour limiter les champs retournés
        projection = {
            "telegram_id": 1,
            "username": 1,
            "first_name": 1,
            "language": 1,
            "role": 1,
            "is_banned": 1,
            "created_at": 1
        }
        
        return {"filter": filters, "projection": projection}
    
    @staticmethod
    def optimize_ticket_query(user_id: int, status_filter: Optional[str] = None) -> Dict:
        """Optimise les requêtes tickets."""
        filters = {"user_telegram_id": user_id}
        
        if status_filter:
            filters["status"] = status_filter
        
        # Tri par date de création descendante
        sort = [("created_at", -1)]
        
        # Projection limitée
        projection = {
            "ticket_id": 1,
            "subject": 1,
            "status": 1,
            "priority": 1,
            "created_at": 1,
            "updated_at": 1
        }
        
        return {
            "filter": filters,
            "sort": sort,
            "projection": projection
        }
    
    @staticmethod
    def optimize_catalog_query(category: Optional[str] = None, search: Optional[str] = None) -> Dict:
        """Optimise les requêtes catalogue."""
        filters = {"is_active": True}
        
        if category:
            filters["category"] = category
        
        if search:
            # Pour la recherche texte, utiliser $text si disponible
            filters["$text"] = {"$search": search}
        
        # Tri par pertinence pour la recherche, par nom sinon
        sort = [("name_fr", 1)] if not search else [("score", {"$meta": "textScore"})]
        
        # Projection optimisée pour le catalogue
        projection = {
            "name_fr": 1,
            "name_en": 1,
            "name_ar": 1,
            "price": 1,
            "stock": 1,
            "category": 1,
            "image_file_id": 1
        }
        
        return {
            "filter": filters,
            "sort": sort,
            "projection": projection
        }


class BackgroundTaskManager:
    """Gestionnaire de tâches en arrière-plan optimisé."""
    
    def __init__(self):
        self.task_queue = asyncio.Queue()
        self.running = False
    
    async def start(self) -> None:
        """Démarre le gestionnaire de tâches."""
        self.running = True
        asyncio.create_task(self._process_tasks())
    
    async def stop(self) -> None:
        """Arrête le gestionnaire de tâches."""
        self.running = False
    
    async def add_task(self, task_func, *args, **kwargs) -> None:
        """Ajoute une tâche à la file."""
        await self.task_queue.put((task_func, args, kwargs))
    
    async def _process_tasks(self) -> None:
        """Traite les tâches en arrière-plan."""
        while self.running:
            try:
                task_func, args, kwargs = await asyncio.wait_for(
                    self.task_queue.get(), 
                    timeout=1.0
                )
                
                # Exécuter la tâche sans bloquer
                asyncio.create_task(task_func(*args, **kwargs))
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                # Logger l'erreur mais continuer
                print(f"Error processing background task: {e}")


# Instance globale de l'optimiseur
performance_optimizer = PerformanceOptimizer()
cache_manager = CacheManager()
query_optimizer = QueryOptimizer()
background_task_manager = BackgroundTaskManager()


async def init_performance_optimizations() -> None:
    """Initialise toutes les optimisations de performance."""
    # Initialiser Redis dans les gestionnaires
    performance_optimizer.redis = get_redis()
    cache_manager.redis = get_redis()
    
    # Créer les index
    await performance_optimizer.create_indexes()
    
    # Optimiser les connection pools
    await performance_optimizer.optimize_connection_pooling()
    
    # Démarrer le gestionnaire de tâches
    await background_task_manager.start()


async def cleanup_performance_optimizations() -> None:
    """Nettoie les ressources d'optimisation."""
    await background_task_manager.stop()
