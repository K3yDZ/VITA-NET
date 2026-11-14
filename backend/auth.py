import os, json, time, hmac, hashlib, base64

# JWT utilities (stdlib only)

_JWT_SECRET = None

def _get_jwt_secret() -> str:
    """Get and validate JWT_SECRET at first use (startup)."""
    global _JWT_SECRET
    secret = os.getenv('JWT_SECRET')
    if not secret:
        raise ValueError('JWT_SECRET not configured')
    if len(secret) < 32:
        raise ValueError('JWT_SECRET must be at least 32 characters for HS256 security')
    _JWT_SECRET = secret
    return _JWT_SECRET

def reset_jwt_secret() -> None:
    """Reset cached JWT_SECRET (for testing only)."""
    global _JWT_SECRET
    _JWT_SECRET = None

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)

def create_jwt(sub: str, role: str, exp_seconds: int = 3600) -> str:
    """Create HS256 JWT. Payload includes sub, role, iat, exp."""
    secret = _get_jwt_secret()
    header = {'alg': 'HS256', 'typ': 'JWT'}
    iat = int(time.time())
    payload = {'sub': sub, 'role': role, 'iat': iat, 'exp': iat + exp_seconds}
    header_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_jwt(token: str) -> dict:
    """Validate HS256 JWT, return payload or raise HTTPException."""
    secret = _get_jwt_secret()
    try:
        header_b64, payload_b64, signature_b64 = token.split('.')
    except ValueError:
        raise ValueError('Invalid token format')
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_decode(signature_b64), expected_sig):
        raise ValueError('Invalid signature')
    payload = json.loads(_b64url_decode(payload_b64))
    now = int(time.time())
    if payload.get('exp', 0) < now:
        raise ValueError('Token expired')
    return payload
