from azure.storage.blob import BlobServiceClient, ContentSettings, PublicAccess
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient
from loguru import logger

from carriage_services.settings import settings


class AzureBlobStorage:
    """Azure Blob Storage class for storing and retrieving files."""

    def __init__(self) -> None:
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                settings.storage.AZURE_STORAGE_CONNECTION_STRING
            )
            self.async_blob_service_client = AsyncBlobServiceClient.from_connection_string(
                settings.storage.AZURE_STORAGE_CONNECTION_STRING
            )
        except Exception as e:
            logger.error(f"Failed to connect to Azure Blob Storage: {e}")
            raise

        self.azurite_public_url = settings.storage.AZURITE_PUBLIC_URL

    def get_public_url(self, container_name: str, blob_name: str) -> str:
        """Constructs a public URL for a blob."""
        if self.azurite_public_url:
            # For local development with Azurite
            account_name = self.blob_service_client.account_name
            return f"{self.azurite_public_url}/{account_name}/{container_name}/{blob_name}"

        # For production Azure Blob Storage
        blob_client = self.blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        return blob_client.url

    async def async_upload_to_blob(self, bytes_: bytes, container_name: str, blob_name: str, content_type: str) -> str:
        """Uploads bytes to the blob and returns the constructed public URL (async version)."""
        async with self.async_blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        ) as blob_client:
            content_settings = ContentSettings(content_type=content_type)
            await blob_client.upload_blob(bytes_, overwrite=True, content_settings=content_settings)

        public_url = self.get_public_url(container_name, blob_name)
        logger.info(f"Uploaded file to: {public_url}")

        return public_url

    async def async_upload_to_blob_audio(self, audio_bytes: bytes, container_name: str, blob_name: str) -> str:
        """Uploads audio bytes and returns the constructed public URL (async version)."""
        content_type = "audio/mpeg"
        return await self.async_upload_to_blob(audio_bytes, container_name, blob_name, content_type)

    def upload_to_blob(self, bytes_: bytes, container_name: str, blob_name: str, content_type: str) -> str:
        """Uploads bytes and returns the constructed public URL."""
        blob_client = self.blob_service_client.get_blob_client(container=container_name, blob=blob_name)

        content_settings = ContentSettings(content_type=content_type)
        blob_client.upload_blob(bytes_, overwrite=True, content_settings=content_settings)

        public_url = self.get_public_url(container_name, blob_name)
        logger.info(f"Uploaded file to: {public_url}")

        return public_url

    def upload_to_blob_audio(self, audio_bytes: bytes, container_name: str, blob_name: str) -> str:
        """Uploads audio bytes and returns the constructed public URL."""
        content_type = "audio/mpeg"
        return self.upload_to_blob(audio_bytes, container_name, blob_name, content_type)

    def create_container(self, container_name: str, public_access: bool = False) -> bool:
        """Create a blob container in Azure Storage.

        Args:
            container_name: Name of the container to create
            public_access: Whether to set public access level to 'blob'

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create container with optional public access
            public_access_level = PublicAccess.Blob if public_access else None
            self.blob_service_client.create_container(container_name, public_access=public_access_level)
            logger.info(f"Container '{container_name}' created successfully")
            if public_access:
                logger.info(f"Container '{container_name}' set to public blob access")
            return True
        except Exception as e:
            if "ContainerAlreadyExists" in str(e):
                logger.info(f"Container '{container_name}' already exists")
                # Try to set public access if requested and container exists
                if public_access:
                    try:
                        container_client = self.blob_service_client.get_container_client(container_name)
                        container_client.set_container_access_policy(
                            signed_identifiers={}, public_access=PublicAccess.Blob
                        )
                        logger.info(f"Container '{container_name}' access level set to public blob access")
                    except Exception as access_error:
                        if "PublicAccessNotPermitted" in str(access_error):
                            logger.warning(
                                f"Public access not permitted on this storage account for container '{container_name}'"
                            )
                        else:
                            logger.warning(
                                f"Failed to set public access for container '{container_name}': {access_error}"
                            )
                return True
            elif "PublicAccessNotPermitted" in str(e) and public_access:
                # Container creation failed due to public access restriction, try without public access
                logger.warning("Public access not permitted, creating private container instead")
                try:
                    self.blob_service_client.create_container(container_name)
                    logger.info(f"Container '{container_name}' created successfully (private)")
                    return True
                except Exception as retry_error:
                    logger.error(f"Error creating container: {retry_error}")
                    return False
            logger.error(f"Error creating container: {e}")
            return False

    def delete_container(self, container_name: str) -> bool:
        """Delete a blob container from Azure Storage.

        Args:
            container_name: Name of the container to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.blob_service_client.delete_container(container_name)
            logger.info(f"Container '{container_name}' deleted successfully")
            return True
        except Exception as e:
            if "ContainerNotFound" in str(e):
                logger.warning(f"Container '{container_name}' does not exist")
                return False
            logger.error(f"Error deleting container: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up resources, particularly the blob service client."""
        if hasattr(self, "blob_service_client"):
            self.blob_service_client.close()
        if hasattr(self, "async_blob_service_client"):
            await self.async_blob_service_client.close()
        logger.debug("Blob service client closed")
