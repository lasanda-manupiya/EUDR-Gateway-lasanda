class SecurityHeadersMiddleware:
    """Content Security Policy: all scripts, styles and fonts are self-hosted.
    Map tiles are the only third-party requests (images)."""

    CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data: https://*.tile.openstreetmap.org https://server.arcgisonline.com; "
           "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
           "frame-ancestors 'none'; form-action 'self'")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return response
