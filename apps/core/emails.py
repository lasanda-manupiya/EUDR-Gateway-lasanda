from django.conf import settings
from django.core.mail import send_mail


def send_invitation_email(to, subject, intro, link):
    body = (f"{intro}\n\nOpen this secure link to continue:\n{link}\n\n"
            f"The link expires in {settings.INVITATION_TTL_DAYS} days and can only be used once.\n\n"
            "SustainZone EUDR Gateway")
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
