"""
Root conftest.py — applied before any test collection or imports.

Suppresses noisy third-party warnings that are irrelevant to this project:
  - google-auth FutureWarning (Python 3.9 EOL notice)
  - urllib3 NotOpenSSLWarning (macOS LibreSSL vs OpenSSL)
  - google-genai PydanticDeprecatedSince212 (internal google-genai issue)
"""

import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module=r"google.*")
warnings.filterwarnings("ignore", message=r".*LibreSSL.*")
warnings.filterwarnings("ignore", message=r".*urllib3 v2 only supports OpenSSL.*")
warnings.filterwarnings("ignore", message=r".*Using `@model_validator`.*")
