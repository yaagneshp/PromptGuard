from slowapi import Limiter
from slowapi.util import get_remote_address

# Per-IP limits. Also serves as a brute-force throttle on the API key check,
# since a failed auth attempt still counts against the same limit.
limiter = Limiter(key_func=get_remote_address)
