import time
import hashlib
from flask import current_app

class StorageService:
    @staticmethod
    def get_download_url(filename: str, expires_in_seconds: int = 3600) -> str:
        """
        根据不同的存储后备生成带有鉴权(Auth/Key)的安全下载链接。
        """
        storage_type = current_app.config.get('STORAGE_TYPE', 'NGINX')
        
        if storage_type in ['MINIO', 'OBS']:
            return StorageService._get_s3_presigned_url(filename, expires_in_seconds)
        elif storage_type == 'NGINX':
            return StorageService._get_nginx_secure_link(filename, expires_in_seconds)
        else:
            raise ValueError(f"Unknown STORAGE_TYPE: {storage_type}")

    @staticmethod
    def _get_s3_presigned_url(filename: str, expires_in_seconds: int) -> str:
        """
        生成 S3 / MinIO / OBS 兼容的 Presigned URL。
        边缘节点可以直接 HTTP GET 这个 URL，不需要传任何 Header，链接会在设定时间后失效。
        （使用 boto3 库，如果未安装，在 requirements.txt 增加 boto3）
        """
        try:
            import boto3
            from botocore.client import Config
            
            s3_client = boto3.client(
                's3',
                endpoint_url=current_app.config['STORAGE_ENDPOINT'],
                aws_access_key_id=current_app.config['STORAGE_ACCESS_KEY'],
                aws_secret_access_key=current_app.config['STORAGE_SECRET_KEY'],
                config=Config(signature_version='s3v4'),
                region_name='us-east-1' # 标准的 fallback
            )
            raw_bucket_path = current_app.config['STORAGE_BUCKET']
            
            # 智能解析: 如果用户填入了类似 dev/sjic/models 的包含虚拟目录的路径
            if '/' in raw_bucket_path:
                parts = raw_bucket_path.strip('/').split('/', 1)
                real_bucket = parts[0]
                # 拼接目录前缀和文件名
                prefix = parts[1].strip('/')
                real_key = f"{prefix}/{filename}" if prefix else filename
            else:
                real_bucket = raw_bucket_path
                real_key = filename
                
            url = s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': real_bucket,
                    'Key': real_key
                },
                ExpiresIn=expires_in_seconds
            )
            return url
        except ImportError:
            current_app.logger.error("boto3 not installed. Cannot generate S3 URL.")
            return ""
        except Exception as e:
            current_app.logger.error(f"Error generating presigned url: {e}")
            return ""

    @staticmethod
    def _get_nginx_secure_link(filename: str, expires_in_seconds: int) -> str:
        """
        基于 Nginx secure_link_module 生成鉴权下载链接。
        不仅能利用 Nginx 极高的静态大文件下发性能，还能防止恶意盗刷下载。
        """
        base_url = current_app.config['NGINX_STATIC_BASE_URL'].rstrip('/')
        secret = current_app.config['DOWNLOAD_SECURE_KEY']
        
        # 过期时间 Unix Timestamp
        expire_time = int(time.time()) + expires_in_seconds
        
        # Nginx Secure Link 签名算法 (MD5): 格式为 `md5(secret+path+expire_time)` 
        # 此处要求 path 为相对 URI，例如 `/static-models/belt_v8.onnx`
        # 但我们此处仅做简单的 token HMAC：
        raw_str = f"{secret}/static-models/{filename}{expire_time}"
        
        # 这里演示生成标准的 md5 hash (转为 Nginx 支持的 Base64URL 格式)
        m = hashlib.md5()
        m.update(raw_str.encode('utf-8'))
        import base64
        # Nginx 需要将 '=' 去掉，并且 '+' 变 '-'，'/' 变 '_'
        md5_b64 = base64.b64encode(m.digest()).decode('utf-8')
        md5_b64 = md5_b64.replace('+', '-').replace('/', '_').rstrip('=')
        
        # 完整的下载 URL (包含防盗链参数)
        return f"{base_url}/{filename}?md5={md5_b64}&expires={expire_time}"
