from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^language/$', views.language, name='language'),
    url(r'^about/', views.about, name='about'),
    url(r'^cookie-policy/$', views.cookie_policy, name='cookie_policy'),
    url(r'^cookie-policy/accept/$', views.accept_cookie_policy, name='accept_cookie_policy'),
    url(r'^help/tex-markup/', views.tex_markup, name='tex_markup'),
    url(r'^test-sending-emails/', views.TestSendingEmailsView.as_view(), name='test_sending_emails'),
]
