"""Orbi Dev — Registre des connecteurs disponibles."""

from src.core.config import get_settings
from src.orbi_dev.connectors.base import AgentConnectorType, Capability, ConnectorError, ErrorCategory
from src.orbi_dev.connectors.cursor import CursorCloudAgentsConnector
from src.orbi_dev.connectors.devin import DevinConnector
from src.orbi_dev.connectors.fake import FakeConnector
from src.orbi_dev.connectors.jules import JulesConnector

# Classes des connecteurs : source des capacités déclarées (`provider_capabilities`),
# indépendamment des factories éventuellement substituées dans `_PROVIDERS` (tests).
_PROVIDER_CLASSES: dict[str, type[AgentConnectorType]] = {
    CursorCloudAgentsConnector.provider: CursorCloudAgentsConnector,
    DevinConnector.provider: DevinConnector,
    JulesConnector.provider: JulesConnector,
    FakeConnector.provider: FakeConnector,
}

_PROVIDERS: dict[str, type[AgentConnectorType]] = dict(_PROVIDER_CLASSES)


def available_providers() -> list[str]:
    """Le fournisseur factice n'existe jamais en production."""
    providers = list(_PROVIDERS)
    if get_settings().is_production:
        providers.remove(FakeConnector.provider)
    return providers


def provider_capabilities(provider: str) -> frozenset[Capability]:
    """Capacités déclarées par le connecteur du fournisseur, sans instancier (indice d'interface, ADR-0010)."""
    cls = _PROVIDER_CLASSES.get(provider) or _PROVIDERS.get(provider)
    return getattr(cls, "capabilities", frozenset()) if cls is not None else frozenset()


def build_connector(provider: str, secret: str) -> AgentConnectorType:
    if provider not in available_providers():
        raise ConnectorError(ErrorCategory.INVALID_REQUEST, "Fournisseur inconnu ou indisponible")
    return _PROVIDERS[provider](secret)
