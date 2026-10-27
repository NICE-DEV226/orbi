"""
Orbi Dev — Qui peut l'utiliser.

Une seule règle, partagée par le bot et le web : aujourd'hui, les administrateurs. Chaque donnée Orbi Dev appartient
à un `owner_id` (identité Telegram) et n'est jamais lue sans ce filtre ; ouvrir l'accès à d'autres personnes ne
demande donc que de changer cette fonction.
"""

from src.models.user import User


def can_use_orbi_dev(user: User | None) -> bool:
    return user is not None and not user.is_banned and user.is_admin
