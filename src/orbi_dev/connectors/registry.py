"""Orbi Dev — Registre des connecteurs disponibles."""

from src.core.config import get_settings
from src.orbi_dev.connectors.base import AgentConnectorType, ConnectorError, ErrorCategory
from src.orbi_dev.connectors.cursor import CursorCloudAgentsConnector
from src.orbi_dev.connectors.fake import FakeConnector

_PROVIDERS: dict[str, type[AgentConnectorType]] = {
    CursorCloudAgentsConnector.provider: CursorCloudAgentsConnector,
    FakeConnector.provider: FakeConnector,
}


def available_providers() -> list[str]:
    """Le fournisseur factice n'existe jamais en production."""
    providers = list(_PROVIDERS)
    if get_settings().is_production:
        providers.remove(FakeConnector.provider)
    return providers


def build_connector(provider: str, secret: str) -> AgentConnectorType:
    if provider not in available_providers():
        raise ConnectorError(ErrorCategory.INVALID_REQUEST, "Fournisseur inconnu ou indisponible")
    return _PROVIDERS[provider](secret)
