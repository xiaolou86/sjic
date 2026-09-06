"""
对象存储抽象：按 STORAGE_TYPE 分发到 Nginx 本地目录或 S3 兼容存储（MinIO / OBS）。
"""
from __future__ import annotations

import abc
import base64
import hashlib
import os
import shutil
import time
from typing import BinaryIO, Union

from flask import current_app

FileSource = Union[str, BinaryIO]


class BaseStorageBackend(abc.ABC):
    """存储后端基类。"""

    @abc.abstractmethod
    def get_download_url(self, filename: str, expires_in_seconds: int = 3600) -> str:
        """生成带鉴权的下载链接。"""

    @abc.abstractmethod
    def upload(self, filename: str, source: FileSource) -> None:
        """将本地路径或文件对象上传到存储。"""

    @abc.abstractmethod
    def delete(self, filename: str) -> None:
        """删除存储中的对象；对象不存在时忽略。"""


class NginxLocalStorage(BaseStorageBackend):
    """本地 MODEL_FOLDER + Nginx secure_link 下载。"""

    def _model_folder(self) -> str:
        return current_app.config.get('MODEL_FOLDER') or current_app.config.get('UPLOAD_FOLDER')

    def get_download_url(self, filename: str, expires_in_seconds: int = 3600) -> str:
        """
        返回相对路径下载链接（含 secure_link 参数）。
        完整可达 URL 由 Edge 根据自身 platform.models_base_url / api_base_url 拼接，
        避免 backend 配置局域网 IP。
        """
        secret = current_app.config['DOWNLOAD_SECURE_KEY']
        expire_time = int(time.time()) + expires_in_seconds

        # Nginx Secure Link: md5(secret + path + expire)，path 为 /static-models/{filename}
        raw_str = f"{secret}/static-models/{filename}{expire_time}"
        digest = hashlib.md5(raw_str.encode('utf-8')).digest()
        md5_b64 = base64.b64encode(digest).decode('utf-8')
        md5_b64 = md5_b64.replace('+', '-').replace('/', '_').rstrip('=')

        return f"/static-models/{filename}?md5={md5_b64}&expires={expire_time}"

    def upload(self, filename: str, source: FileSource) -> None:
        model_folder = self._model_folder()
        os.makedirs(model_folder, exist_ok=True)
        # 目录需对 nginx 工作进程（非 root）可遍历
        try:
            os.chmod(model_folder, 0o755)
        except OSError:
            pass

        dest = os.path.join(model_folder, filename)

        if isinstance(source, str):
            # 勿用 copy2：临时文件常为 0600，会导致 frontend nginx 读模型 Permission denied
            shutil.copyfile(source, dest)
        else:
            source.seek(0)
            with open(dest, 'wb') as out:
                shutil.copyfileobj(source, out)

        try:
            os.chmod(dest, 0o644)
        except OSError as e:
            current_app.logger.warning(f"Failed to chmod model file {dest}: {e}")

    def delete(self, filename: str) -> None:
        path = os.path.join(self._model_folder(), filename)
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except OSError as e:
            current_app.logger.warning(f"Failed to delete local model file {path}: {e}")


class S3CompatibleStorage(BaseStorageBackend):
    """S3 / MinIO / OBS 兼容存储。"""

    def _client(self):
        import boto3
        from botocore.client import Config

        return boto3.client(
            's3',
            endpoint_url=current_app.config['STORAGE_ENDPOINT'],
            aws_access_key_id=current_app.config['STORAGE_ACCESS_KEY'],
            aws_secret_access_key=current_app.config['STORAGE_SECRET_KEY'],
            config=Config(signature_version='s3v4'),
            region_name='us-east-1',
        )

    def _bucket_and_key(self, filename: str):
        """解析 STORAGE_BUCKET（可含虚拟目录前缀，如 sjic/models）。"""
        raw_bucket_path = current_app.config['STORAGE_BUCKET']
        if '/' in raw_bucket_path:
            parts = raw_bucket_path.strip('/').split('/', 1)
            real_bucket = parts[0]
            prefix = parts[1].strip('/')
            real_key = f"{prefix}/{filename}" if prefix else filename
        else:
            real_bucket = raw_bucket_path
            real_key = filename
        return real_bucket, real_key

    def get_download_url(self, filename: str, expires_in_seconds: int = 3600) -> str:
        try:
            s3_client = self._client()
            real_bucket, real_key = self._bucket_and_key(filename)
            return s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params={'Bucket': real_bucket, 'Key': real_key},
                ExpiresIn=expires_in_seconds,
            )
        except ImportError:
            current_app.logger.error("boto3 not installed. Cannot generate S3 URL.")
            return ""
        except Exception as e:
            current_app.logger.error(f"Error generating presigned url: {e}")
            return ""

    def upload(self, filename: str, source: FileSource) -> None:
        try:
            s3_client = self._client()
        except ImportError as e:
            raise RuntimeError("boto3 not installed. Cannot upload to S3 storage.") from e

        real_bucket, real_key = self._bucket_and_key(filename)
        if isinstance(source, str):
            s3_client.upload_file(source, real_bucket, real_key)
        else:
            source.seek(0)
            s3_client.upload_fileobj(source, real_bucket, real_key)

    def delete(self, filename: str) -> None:
        try:
            s3_client = self._client()
            real_bucket, real_key = self._bucket_and_key(filename)
            s3_client.delete_object(Bucket=real_bucket, Key=real_key)
        except ImportError:
            current_app.logger.error("boto3 not installed. Cannot delete S3 object.")
        except Exception as e:
            current_app.logger.warning(f"Failed to delete S3 object {filename}: {e}")


def get_storage() -> BaseStorageBackend:
    """按配置返回当前存储后端实例。"""
    storage_type = (current_app.config.get('STORAGE_TYPE') or 'NGINX').upper()
    if storage_type in ('MINIO', 'OBS'):
        return S3CompatibleStorage()
    if storage_type == 'NGINX':
        return NginxLocalStorage()
    raise ValueError(f"Unknown STORAGE_TYPE: {storage_type}")


class StorageService:
    """兼容门面：现有调用方继续使用 StorageService.get_download_url。"""

    @staticmethod
    def get_download_url(filename: str, expires_in_seconds: int = 3600) -> str:
        return get_storage().get_download_url(filename, expires_in_seconds)

    @staticmethod
    def upload(filename: str, source: FileSource) -> None:
        get_storage().upload(filename, source)

    @staticmethod
    def delete(filename: str) -> None:
        get_storage().delete(filename)
