"""
DNA存储 - MaiBot的敏感信息加密存储系统
提供安全的密钥管理和加密存储机制
"""

import os
import json
import base64
import logging
import secrets
from typing import Dict, Optional
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class DNAStorage:
    """
    DNA存储 - 敏感信息加密存储系统

    用于安全存储API密钥、令牌和其他敏感信息。
    使用Fernet对称加密，提供安全的密钥管理。
    支持从环境变量或文件加载主密钥。
    """

    def __init__(
        self, storage_path: str = "data/dna_storage", env_key_name: str = "MAIBOT_DNA_KEY", salt: Optional[bytes] = None
    ):
        """
        初始化DNA存储系统

        Args:
            storage_path: 存储文件路径
            env_key_name: 环境变量中主密钥的名称
            salt: 自定义盐值（如果为None则自动生成）
        """
        self.logger = logging.getLogger("DNAStorage")
        self.storage_path = Path(storage_path)
        self.env_key_name = env_key_name

        # 存储数据
        self.data: Dict[str, str] = {}

        # 加密相关
        self.salt = salt or b"MaiBot-DNA-Storage-Salt"  # 默认盐值
        self.key: Optional[bytes] = None
        self.fernet: Optional[Fernet] = None

        # 初始化
        self._initialize()

    def _initialize(self) -> None:
        """初始化存储和密钥"""
        # 创建存储目录
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # 设置主密钥
        self._setup_master_key()

        # 加载存储数据
        self._load_data()

    def _setup_master_key(self) -> None:
        """设置主密钥"""
        # 尝试从环境变量获取密钥
        env_key = os.environ.get(self.env_key_name)

        if env_key:
            try:
                # 解码环境变量中的密钥
                key_bytes = base64.urlsafe_b64decode(env_key)
                if len(key_bytes) == 32:  # 有效的Fernet密钥长度
                    self.key = key_bytes
                    self.fernet = Fernet(base64.urlsafe_b64encode(self.key))
                    return
            except Exception as e:
                self.logger.warning(f"从环境变量加载密钥失败: {e}")

        # 如果没有环境变量或解码失败，尝试从密钥文件加载
        key_file = self.storage_path.with_suffix(".key")
        if key_file.exists():
            try:
                with open(key_file, "rb") as f:
                    key_data = f.read()
                    self.key = base64.urlsafe_b64decode(key_data)
                    self.fernet = Fernet(base64.urlsafe_b64encode(self.key))
                    return
            except Exception as e:
                self.logger.warning(f"从密钥文件加载密钥失败: {e}")

        # 如果无法加载密钥，则生成新密钥
        self._generate_new_key(key_file)

    def _generate_new_key(self, key_file: Path) -> None:
        """
        生成新的主密钥

        Args:
            key_file: 密钥文件路径
        """
        # 生成随机密码
        password = secrets.token_bytes(32)

        # 使用PBKDF2派生密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = kdf.derive(password)

        # 设置密钥
        self.key = key
        self.fernet = Fernet(base64.urlsafe_b64encode(key))

        # 保存密钥到文件
        try:
            with open(key_file, "wb") as f:
                f.write(base64.urlsafe_b64encode(key))
            self.logger.info(f"已生成并保存新的主密钥到 {key_file}")
        except Exception as e:
            self.logger.error(f"保存主密钥失败: {e}")

        # 输出环境变量设置提示
        encoded_key = base64.urlsafe_b64encode(key).decode("utf-8")
        self.logger.info(
            f"为了提高安全性，建议设置环境变量: {self.env_key_name}={encoded_key}\n然后删除密钥文件: {key_file}"
        )

    def _load_data(self) -> None:
        """从存储文件加载数据"""
        if not self.fernet:
            self.logger.error("未初始化加密器，无法加载数据")
            return

        storage_file = self.storage_path.with_suffix(".dna")
        if not storage_file.exists():
            self.data = {}
            return

        try:
            with open(storage_file, "rb") as f:
                encrypted_data = f.read()
                if not encrypted_data:
                    self.data = {}
                    return

                # 解密数据
                decrypted_data = self.fernet.decrypt(encrypted_data).decode("utf-8")
                self.data = json.loads(decrypted_data)

        except Exception as e:
            self.logger.error(f"加载数据失败: {e}")
            self.data = {}

    def _save_data(self) -> bool:
        """
        保存数据到存储文件

        Returns:
            是否成功保存
        """
        if not self.fernet:
            self.logger.error("未初始化加密器，无法保存数据")
            return False

        storage_file = self.storage_path.with_suffix(".dna")

        try:
            # 确保目录存在
            storage_file.parent.mkdir(parents=True, exist_ok=True)

            # 加密数据
            json_data = json.dumps(self.data)
            encrypted_data = self.fernet.encrypt(json_data.encode("utf-8"))

            # 写入文件
            with open(storage_file, "wb") as f:
                f.write(encrypted_data)

            return True

        except Exception as e:
            self.logger.error(f"保存数据失败: {e}")
            return False

    def store(self, key: str, value: str) -> bool:
        """
        加密存储敏感信息

        Args:
            key: 密钥名称
            value: 敏感值

        Returns:
            是否成功存储
        """
        if not self.fernet:
            self.logger.error("未初始化加密器，无法存储数据")
            return False

        try:
            # 存储原始值
            self.data[key] = value

            # 保存到文件
            return self._save_data()

        except Exception as e:
            self.logger.error(f"存储敏感信息失败: {e}")
            return False

    def retrieve(self, key: str) -> Optional[str]:
        """
        获取敏感信息

        Args:
            key: 密钥名称

        Returns:
            敏感值或None（如果未找到）
        """
        return self.data.get(key)

    def delete(self, key: str) -> bool:
        """
        删除敏感信息

        Args:
            key: 密钥名称

        Returns:
            是否成功删除
        """
        if key in self.data:
            del self.data[key]
            return self._save_data()
        return True  # 如果密钥不存在，视为删除成功

    def has_key(self, key: str) -> bool:
        """
        检查密钥是否存在

        Args:
            key: 密钥名称

        Returns:
            密钥是否存在
        """
        return key in self.data

    def get_all_keys(self) -> list:
        """
        获取所有密钥名称

        Returns:
            密钥名称列表
        """
        return list(self.data.keys())

    def clear(self) -> bool:
        """
        清除所有存储的敏感信息

        Returns:
            是否成功清除
        """
        self.data = {}
        return self._save_data()

    def change_master_key(self, new_password: Optional[str] = None) -> bool:
        """
        更改主密钥

        Args:
            new_password: 新密码（如果为None则随机生成）

        Returns:
            是否成功更改
        """
        if not self.fernet:
            self.logger.error("未初始化加密器，无法更改主密钥")
            return False

        try:
            # 备份当前数据
            old_data = self.data.copy()

            # 生成新密钥
            if new_password:
                # 使用提供的密码
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=self.salt,
                    iterations=100000,
                )
                key = kdf.derive(new_password.encode("utf-8"))
            else:
                # 随机生成密钥
                key = Fernet.generate_key()

            # 更新密钥
            self.key = base64.urlsafe_b64decode(key)
            self.fernet = Fernet(key)

            # 保存密钥
            key_file = self.storage_path.with_suffix(".key")
            with open(key_file, "wb") as f:
                f.write(key)

            # 恢复数据并保存
            self.data = old_data
            success = self._save_data()

            if success:
                # 输出环境变量设置提示
                encoded_key = key.decode("utf-8")
                self.logger.info(
                    f"主密钥已更改。为了提高安全性，建议设置环境变量: "
                    f"{self.env_key_name}={encoded_key}"
                    f"\n然后删除密钥文件: {key_file}"
                )

            return success

        except Exception as e:
            self.logger.error(f"更改主密钥失败: {e}")
            return False
