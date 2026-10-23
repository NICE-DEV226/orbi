"""
Orbi — Internationalisation (i18n).
Charge les traductions depuis les fichiers YAML (locales/) et fournit la fonction t().
Langues supportées : FR, EN, AR.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("orbi.i18n")

SUPPORTED_LANGUAGES = ("fr", "en", "ar")
DEFAULT_LANGUAGE = "fr"

_LOCALES_DIR = Path(__file__).parent.parent / "locales"
_translations: dict[str, dict[str, Any]] = {}


def load_translations() -> None:
    """Charge tous les fichiers YAML de traduction au démarrage."""
    global _translations
    _translations = {}

    for lang in SUPPORTED_LANGUAGES:
        filepath = _LOCALES_DIR / f"{lang}.yml"
        if not filepath.exists():
            logger.warning("Fichier de traduction manquant: %s", filepath)
            _translations[lang] = {}
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                _translations[lang] = data
                logger.info("Traductions chargées: %s (%d clés racines)", lang, len(data))
        except Exception as e:
            logger.error("Erreur critique lors du chargement de %s: %s", filepath, e)
            _translations[lang] = {}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """
    Retourne la traduction pour une clé donnée dans la langue spécifiée.

    Supporte les clés imbriquées avec notation point : "menu.welcome"
    Supporte le formatage avec des paramètres nommés : t("welcome", "fr", name="Alice")

    Fallback : si la clé n'existe pas dans la langue demandée, cherche en FR.
    Si toujours introuvable, retourne la clé elle-même.
    """
    if not _translations:
        load_translations()

    # Normalise la langue
    lang = lang.lower() if lang else DEFAULT_LANGUAGE
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    # Cherche dans la langue demandée, puis fallback FR
    value = _resolve_key(key, lang)
    if value is None and lang != DEFAULT_LANGUAGE:
        value = _resolve_key(key, DEFAULT_LANGUAGE)

    if value is None:
        logger.warning("Clé de traduction manquante: '%s' (lang=%s)", key, lang)
        return key

    # Formatage avec les paramètres
    if kwargs:
        try:
            return str(value).format(**kwargs)
        except (KeyError, IndexError, ValueError):
            logger.warning("Erreur de formatage pour '%s' (lang=%s): %s", key, lang, kwargs)
            return str(value)

    return str(value)


def _resolve_key(key: str, lang: str) -> str | None:
    """Résout une clé potentiellement imbriquée (ex: 'menu.main.title')."""
    data = _translations.get(lang, {})
    parts = key.split(".")

    for part in parts:
        if isinstance(data, dict):
            data = data.get(part)
        else:
            return None

        if data is None:
            return None

    return str(data) if data is not None else None


def detect_language(telegram_lang_code: str | None) -> str:
    """
    Détecte la langue à utiliser à partir du code langue Telegram.
    Retourne 'fr', 'en' ou 'ar'. Défaut: 'fr'.
    """
    if not telegram_lang_code:
        return DEFAULT_LANGUAGE

    code = telegram_lang_code.lower().strip()

    # Correspondances directes
    if code.startswith("fr"):
        return "fr"
    if code.startswith("en"):
        return "en"
    if code.startswith("ar"):
        return "ar"

    # Langue non supportée — on ne peut pas deviner, on laissera le sélecteur s'afficher
    return DEFAULT_LANGUAGE
