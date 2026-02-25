from azure.identity import ClientSecretCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from loguru import logger


def get_main_service_url(
    container_app_name: str,
    subscription_id: str,
    resource_group: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> str | None:
    """Get URL of the main service.

    Returns:
        URL of the main service
    """
    try:
        fqdn = _get_container_app_fqdn(
            container_app_name, subscription_id, resource_group, tenant_id, client_id, client_secret
        )
        url = f"https://{fqdn}"
        logger.info(f"Main service URL: {url}")
    except Exception as e:
        logger.warning(f"Error getting main service URL: {e}")
        return None
    return url


def _get_container_app_fqdn(
    container_app_name: str,
    subscription_id: str,
    resource_group: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Get FQDN of a container app.

    Args:
        container_app_name: name of the container app
        subscription_id: Azure subscription ID
        resource_group: name of the resource group
        tenant_id: Azure tenant ID
        client_id: Azure client ID
        client_secret: Azure client secret

    Returns:
        FQDN of the main service
    """
    container_apps_manager = ContainerAppsAPIClient(
        _azure_client_credentials(tenant_id, client_id, client_secret), subscription_id
    )
    container_apps = container_apps_manager.container_apps.list_by_resource_group(resource_group)
    orchestrator_app = next(app for app in container_apps if app.name == container_app_name)
    return orchestrator_app.configuration.ingress.fqdn


def _azure_client_credentials(tenant_id: str, client_id: str, client_secret: str) -> ClientSecretCredential:
    """Returns Azure client credentials for the service principal."""
    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
