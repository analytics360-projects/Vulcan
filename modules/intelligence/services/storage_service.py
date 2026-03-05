"""
MinIO Object Storage Service

Handles upload, download, and deletion of evidence files (photos, videos) to MinIO.
"""
import io
import structlog
from typing import Optional, BinaryIO
from minio import Minio
from minio.error import S3Error
from config import settings

logger = structlog.get_logger()


class StorageService:
    """Service for managing evidence files in MinIO object storage"""

    def __init__(self):
        """Initialize MinIO client"""
        self.client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key_id,
            secret_key=settings.minio_secret_access_key,
            secure=settings.minio_secure,
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        logger.info(
            "StorageService initialized",
            endpoint=settings.minio_endpoint,
            bucket=self.bucket_name,
        )

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("Bucket created", bucket=self.bucket_name)
            else:
                logger.info("Bucket already exists", bucket=self.bucket_name)
        except S3Error as e:
            logger.error("Failed to ensure bucket exists", error=str(e))
            raise

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Upload a file to MinIO

        Args:
            object_name: Name/path of the object in the bucket (e.g., "evidence/photo_123.jpg")
            data: File content as bytes
            content_type: MIME type (e.g., "image/jpeg")
            metadata: Optional metadata dict

        Returns:
            Object URL (MinIO path)
        """
        try:
            data_stream = io.BytesIO(data)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=content_type,
                metadata=metadata or {},
            )
            object_url = f"minio://{self.bucket_name}/{object_name}"
            logger.info(
                "File uploaded to MinIO",
                object_name=object_name,
                size=len(data),
                url=object_url,
            )
            return object_url
        except S3Error as e:
            logger.error("Failed to upload file to MinIO", object_name=object_name, error=str(e))
            raise

    def download_file(self, object_name: str) -> bytes:
        """
        Download a file from MinIO

        Args:
            object_name: Name/path of the object in the bucket

        Returns:
            File content as bytes
        """
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            logger.info("File downloaded from MinIO", object_name=object_name, size=len(data))
            return data
        except S3Error as e:
            logger.error("Failed to download file from MinIO", object_name=object_name, error=str(e))
            raise

    def download_file_to_path(self, object_name: str, file_path: str):
        """
        Download a file from MinIO to a local path

        Args:
            object_name: Name/path of the object in the bucket
            file_path: Local file path to save to
        """
        try:
            self.client.fget_object(self.bucket_name, object_name, file_path)
            logger.info(
                "File downloaded to path",
                object_name=object_name,
                file_path=file_path,
            )
        except S3Error as e:
            logger.error(
                "Failed to download file to path",
                object_name=object_name,
                file_path=file_path,
                error=str(e),
            )
            raise

    def delete_file(self, object_name: str):
        """
        Delete a file from MinIO

        Args:
            object_name: Name/path of the object in the bucket
        """
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info("File deleted from MinIO", object_name=object_name)
        except S3Error as e:
            logger.error("Failed to delete file from MinIO", object_name=object_name, error=str(e))
            raise

    def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        """
        Generate a presigned URL for temporary access to a file

        Args:
            object_name: Name/path of the object in the bucket
            expires_seconds: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        try:
            from datetime import timedelta

            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expires_seconds),
            )
            logger.info("Presigned URL generated", object_name=object_name, expires=expires_seconds)
            return url
        except S3Error as e:
            logger.error("Failed to generate presigned URL", object_name=object_name, error=str(e))
            raise

    def object_exists(self, object_name: str) -> bool:
        """
        Check if an object exists in MinIO

        Args:
            object_name: Name/path of the object in the bucket

        Returns:
            True if object exists, False otherwise
        """
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
