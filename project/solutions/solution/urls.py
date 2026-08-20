from django.conf.urls import include, url

from . import views

single_solution_urlpatterns = [
    url(r'^$', views.SolutionMainView.as_view(), name='main'),
    url(r'^source/$', views.SolutionSourceView.as_view(), name='source'),
    url(r'^log/$', views.SolutionLogView.as_view(), name='log'),
    url(r'^tests/$', views.SolutionTestsView.as_view(), name='tests'),
    url(r'^runs/$', views.SolutionJudgementsView.as_view(), name='judgements'),
    url(r'^rejudge/$', views.SolutionRejudgeView.as_view(), name='perform_rejudge'),
    url(r'^attempts/$', views.SolutionAttemptsView.as_view(), name='attempts'),
    url(r'^plagiarism/$', views.SolutionPlagiarismView.as_view(), name='plagiarism'),
    url(r'^toggle-plagiarism/$', views.SolutionTogglePlagiarismView.as_view(), name='toggle_plagiarism'),
    url(r'^status/json/$', views.SolutionStatusJsonView.as_view(), name='status_json'),
    url(r'^tests/(?P<testcaseresult_id>[0-9]+)/$', views.SolutionTestCaseResultView.as_view(), name='test_case_result'),
    url(r'^tests/(?P<testcaseresult_id>[0-9]+)/(?P<mode>input|output|answer|stdout|stderr)\.txt$', views.SolutionTestCaseResultDataView.as_view(), name='test_data'),
    url(r'^tests/(?P<testcaseresult_id>[0-9]+)/images/(?P<filename>.*)$', views.SolutionTestCaseResultImageView.as_view(), name='test_image'),
    url(r'^source/open/(?P<filename>.*)$', views.SolutionSourceOpenView.as_view(), name='source_open'),
    url(r'^source/download/(?P<filename>.*)$', views.SolutionSourceDownloadView.as_view(), name='source_download'),
]

urlpatterns = [
    url(r'^(?P<solution_id>[0-9]+)/', include(single_solution_urlpatterns))
]
