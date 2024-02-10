from django.conf import settings
from django.utils import translation

from common.tree.key import ROOT


def _language_translated(language):
    with translation.override(language):
        return translation.gettext('Language')


def system_name(request):
    return {
        'system_full_name': getattr(settings, 'SYSTEM_FULL_NAME', 'Insight Runner 2'),
        'system_short_name': getattr(settings, 'SYSTEM_SHORT_NAME', 'iRunner 2'),
        'show_about_page': getattr(settings, 'SHOW_ABOUT_PAGE', True),
        'meta_description': getattr(settings, 'META_DESCRIPTION', ''),
        'external_links': settings.EXTERNAL_LINKS,
        'root_folder': ROOT,
        'location': settings.LOCATION,
        'language_switcher_link_text': '\u2009/\u2009'.join(_language_translated(lang) for lang, _ in settings.LANGUAGES),
        'show_cookie_consent': not request.user.is_authenticated and not request.session.get('accept_cookies', False),
    }
