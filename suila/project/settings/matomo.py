import os
import re

MATOMO_URL = os.environ.get("MATOMO_URL", "")
MATOMO_HOST = re.sub(r"^https?://", "", MATOMO_URL)
