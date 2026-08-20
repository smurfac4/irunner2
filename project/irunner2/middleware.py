from django.contrib import messages
from django.contrib.auth import logout
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import ugettext_lazy as _
from users.models import UserSession


class OneSessionPerUserMiddleware(MiddlewareMixin):

    def process_request(self, request):
        if request.user.is_authenticated:
            if not request.session.session_key:
                request.session.save()

            current_key = request.session.session_key
            user_session, created = UserSession.objects.get_or_create(
                user=request.user, defaults={"session_key": current_key}
            )


            if not created:
                
                if (
                    user_session.session_key
                    and user_session.session_key != current_key
                ):
                    logout(request)
                    messages.warning(
                        request,
                        _(
                            "Вы вышли из системы, так как был выполнен вход с другого устройства или браузера."
                        ),
                    )