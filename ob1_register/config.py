"""OB-1 注册工具配置"""

# WorkOS / OB-1
WORKOS_CLIENT_ID = "client_01K8YDZSSKDMK8GYTEHBAW4N4S"
WORKOS_DEVICE_AUTH_URL = "https://api.workos.com/user_management/authorize/device"
WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
OB1_API_BASE = "https://dashboard.openblocklabs.com/api/v1"

# 邮箱 provider
EMAIL_PROVIDER = "domain-imap"
EMAIL_PROVIDER_CONFIG = {}
EMAIL_CODE_TIMEOUT = 180
EMAIL_CHECK_INTERVAL = 5
EMAIL_POLL_CHUNK_TIMEOUT = 10

# 代理（留空不用）
PROXY_URL = ""

# 输出路径
import os
ACCOUNTS_JSON = os.path.join(os.path.dirname(__file__), "..", "config", "accounts.json")
