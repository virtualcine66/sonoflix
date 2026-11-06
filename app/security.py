"""Cabeçalhos de segurança aplicados a todas as respostas."""

from flask import request

# Sem 'unsafe-inline': todo CSS e JS vem de arquivos estáticos do próprio site.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "img-src 'self' data: https://image.tmdb.org https://i.ytimg.com",
    "frame-src https://www.youtube-nocookie.com",
    "script-src 'self'",
    "style-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def register_security(app):
    @app.after_request
    def add_security_headers(response):
        policy = CONTENT_SECURITY_POLICY
        if request.endpoint == "main.watch":
            policy = policy.replace("connect-src 'self'", "connect-src 'self' https:")
            policy += "; media-src 'self' https: blob:; worker-src 'self' blob:"
        response.headers.setdefault("Content-Security-Policy", policy)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if app.config.get("ENABLE_HSTS"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
