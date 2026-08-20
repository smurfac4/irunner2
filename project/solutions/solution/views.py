from collections import namedtuple

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.encoding import force_text
from django.utils.timesince import timesince
from django.views import generic

from cauth.mixins import LoginRequiredMixin, ProblemEditorMemberRequiredMixin
from common.highlight import list_highlight_styles, get_highlight_style, update_highlight_style
from common.outcome import Outcome
from common.pagination import paginate
from plagiarism.models import AggregatedResult, JudgementResult
from storage.storage import create_storage
from storage.utils import serve_resource, serve_resource_metadata

from solutions.mixins import TestCaseResultMixin
from solutions.models import Solution, Judgement, TestCaseResult, JudgementLog
from solutions.utils import bulk_rejudge

from .calcpermissions import calculate_permissions


class BaseSolutionView(LoginRequiredMixin, generic.View):
    tab = None
    with_related = True

    def _load_solution(self, solution_id):
        if self.with_related:
            queryset = Solution.objects.\
                select_related('compiler').\
                select_related('best_judgement').\
                select_related('best_judgement__extra_info').\
                select_related('problem').\
                select_related('source_code')
        else:
            queryset = Solution.objects

        return get_object_or_404(queryset, pk=solution_id)

    def get_context_data(self, **kwargs):
        context = {
            'solution': self.solution,
            'solution_environment': self.environment,
            'permissions': self.permissions,
            'active_tab': self.tab,
        }
        best = self.solution.best_judgement
        if best is not None:
            if hasattr(best, 'extra_info'):
                context['extra_info'] = best.extra_info

        if self.permissions.can_view_attempts:
            context['attempt_count'] = Solution.objects.filter(problem_id=self.solution.problem_id, author_id=self.solution.author_id).count()
        if self.permissions.can_view_judgements:
            context['judgement_count'] = Judgement.objects.filter(solution_id=self.solution.id).count()

        context.update(**kwargs)
        return context

    def get(self, request, solution_id, *args, **kwargs):
        self.solution = self._load_solution(solution_id)
        self.permissions, self.environment = calculate_permissions(self.solution, request.user)

        result = self.do_checked_get(request, self.solution, *args, **kwargs)
        return result

    def do_checked_get(self, *args, **kwargs):
        if not self.is_allowed(self.permissions):
            raise PermissionDenied()
        return self.do_get(*args, **kwargs)

    '''
    methods that must be implemented
    '''

    def is_allowed(self, permissions):
        raise NotImplementedError()

    def do_get(self, request, solution, *args, **kwargs):
        raise NotImplementedError()


class SolutionEmptyView(BaseSolutionView):
    template_name = 'solutions/solution/main.html'

    def is_allowed(self, permissions):
        return permissions.can_view_state_on_samples or permissions.can_view_state

    def do_get(self, request, solution):
        return render(request, self.template_name, self.get_context_data())


class SolutionSourceView(BaseSolutionView):
    tab = 'source'
    template_name = 'solutions/solution/source.html'

    def is_allowed(self, permissions):
        return permissions.can_view_source_code

    def do_get(self, request, solution):
        update_highlight_style(request)

        storage = create_storage()
        source_repr = storage.represent(solution.source_code.resource_id)

        context = self.get_context_data()
        context['highlight_styles'] = list_highlight_styles()
        context['highlight_style'] = get_highlight_style(request)
        context['compiler'] = solution.compiler
        context['source_repr'] = source_repr
        return render(request, self.template_name, context)


class SolutionTestsView(BaseSolutionView):
    tab = 'tests'
    template_name = 'solutions/solution/tests.html'

    def is_allowed(self, permissions):
        return permissions.can_view_sample_results or permissions.can_view_results

    def do_get(self, request, solution):
        test_results = _get_plain_testcaseresults(solution.best_judgement)
        context = self.get_context_data(test_results=test_results)
        return render(request, self.template_name, context)


class SolutionJudgementsView(BaseSolutionView):
    tab = 'judgements'
    template_name = 'solutions/solution/judgements.html'

    def is_allowed(self, permissions):
        return permissions.can_view_judgements

    def do_get(self, request, solution):
        judgements = solution.judgement_set.order_by('-id').select_related('extra_info').all()
        context = self.get_context_data(judgements=judgements)
        return render(request, self.template_name, context)


def _get_compilation_log_repr(judgement):
    if judgement is not None:
        judgementlog = judgement.judgementlog_set.filter(kind=JudgementLog.SOLUTION_COMPILATION).first()
        if judgementlog is not None:
            storage = create_storage()
            return storage.represent(judgementlog.resource_id)


def _get_plain_testcaseresults(judgement):
    if judgement is not None:
        # do not even load unnecessary fields from the database
        test_results = judgement.testcaseresult_set.all()
        test_results = test_results.defer('input_resource_id', 'output_resource_id', 'answer_resource_id', 'stdout_resource_id', 'stderr_resource_id')
        return list(test_results)
    return []


class SolutionLogView(BaseSolutionView):
    tab = 'log'
    template_name = 'solutions/solution/log.html'

    def is_allowed(self, permissions):
        return permissions.can_view_compilation_log

    def do_get(self, request, solution):
        log_repr = None
        if solution.best_judgement is not None:
            log_repr = _get_compilation_log_repr(solution.best_judgement)
        context = self.get_context_data(log_repr=log_repr)
        return render(request, self.template_name, context)


AttemptInfo = namedtuple('AttemptInfo', 'number solution active delta pair space')


class SolutionAttemptsView(BaseSolutionView):
    tab = 'attempts'
    template_name = 'solutions/solution/attempts.html'

    def is_allowed(self, permissions):
        return permissions.can_view_attempts

    def _calc_visual_space(self, seconds):
        days = seconds / (60. * 60. * 24.)
        if days < 0.5:
            return 0
        return 20 + int(100. * min(days / 7., 1.))

    def do_get(self, request, solution):
        related_solutions = []
        last = None
        number = 0

        for cur in Solution.objects.\
                filter(problem_id=solution.problem_id, author_id=solution.author_id).\
                prefetch_related('compiler').\
                select_related('source_code', 'best_judgement').\
                order_by('reception_time'):
            delta = None
            pair = None
            space = None

            if last is not None:
                delta = timesince(d=last.reception_time, now=cur.reception_time)
                pair = (last.id, cur.id)
                space = self._calc_visual_space((cur.reception_time - last.reception_time).total_seconds())

            number += 1
            related_solutions.append(AttemptInfo(number, cur, (cur == solution), delta, pair, space))

            last = cur

        related_solutions.reverse()

        enable_compare = (len(related_solutions) >= 2)
        context = self.get_context_data(related_solutions=related_solutions, enable_compare=enable_compare)
        return render(request, self.template_name, context)


class SolutionMainView(BaseSolutionView):
    def _get_class(self, request, solution, permissions):
        judgement = solution.best_judgement
        if permissions.can_view_sample_results or permissions.can_view_results:
            if judgement is not None:
                test_results_count = judgement.testcaseresult_set.count()
                if test_results_count > 0:
                    return SolutionTestsView
                if judgement.outcome == Outcome.CHECK_FAILED:
                    return SolutionTestsView

        if permissions.can_view_compilation_log:
            if judgement is not None:
                return SolutionLogView

        if permissions.can_view_source_code:
            return SolutionSourceView

        if permissions.can_view_attempts:
            return SolutionAttemptsView

        if permissions.can_view_state_on_samples or permissions.can_view_state:
            return SolutionEmptyView

    def do_checked_get(self, *args, **kwargs):
        cls = self._get_class(self.request, self.solution, self.permissions)
        if cls is None:
            raise PermissionDenied()
        # make a copy of self, but use specific class
        instance = cls(
            request=self.request,
            solution=self.solution,
            environment=self.environment,
            permissions=self.permissions,
            args=self.args,
            kwargs=self.kwargs
        )
        return instance.do_checked_get(*args, **kwargs)


class SolutionStatusJsonView(BaseSolutionView):
    with_related = False
    template_name = 'solutions/solution/status.html'
    box_template_name = 'solutions/solution/status_box.html'

    def is_allowed(self, permissions):
        return permissions.can_view_state_on_samples or permissions.can_view_state

    def _render_report(self, request, judgement):
        if judgement.outcome == Outcome.COMPILATION_ERROR:
            context = self.get_context_data(mode='compilation_log', log_repr=_get_compilation_log_repr(judgement))
        else:
            context = self.get_context_data(mode='test_results', test_results=_get_plain_testcaseresults(judgement))
        return render_to_string(self.template_name, context, request)

    def do_get(self, request, solution):
        judgement = solution.best_judgement

        if judgement is not None:
            final = (judgement.status == Judgement.DONE)
            complete = self.permissions.can_view_state
            data = {
                'text': force_text(judgement.show_status(complete)),
                'final': final
            }
            if final:
                if complete or (judgement.sample_tests_passed is False):
                    data['color'] = 'green' if (judgement.outcome == Outcome.ACCEPTED) ^ settings.APRIL_FOOLS_DAY_MODE else 'red'
                else:
                    data['color'] = 'yellow'
                if request.GET.get('table') == '1':
                    data['report'] = self._render_report(request, judgement)
                    data['box'] = render_to_string(self.box_template_name, self.get_context_data(), request)
        else:
            data = {
                'text': 'N/A',
                'final': False
            }
        return JsonResponse(data, json_dumps_params={'ensure_ascii': False})


class BaseSolutionSourceCodeView(BaseSolutionView):
    '''
    Open/download source code
    '''
    with_related = False

    def is_allowed(self, permissions):
        return permissions.can_view_source_code


class SolutionSourceOpenView(BaseSolutionSourceCodeView):
    def do_get(self, request, solution, filename):
        if filename != solution.source_code.filename:
            raise Http404()

        return serve_resource(request, solution.source_code.resource_id, 'text/plain')


class SolutionSourceDownloadView(BaseSolutionSourceCodeView):
    def do_get(self, request, solution, filename):
        if filename != solution.source_code.filename:
            raise Http404()

        return serve_resource_metadata(request, solution.source_code, force_download=True)


class BaseSolutionTestDataView(BaseSolutionView):
    '''
    View test data
    '''
    with_related = False

    def is_allowed(self, permissions):
        if permissions.can_view_tests_data:
            return True
        if permissions.can_view_sample_results:
            testcaseresult_id = self.kwargs.get('testcaseresult_id')
            if testcaseresult_id is not None:
                is_sample = TestCaseResult.objects.filter(pk=testcaseresult_id).values_list('is_sample', flat=True).first()
                if is_sample:
                    return True
        return False


class SolutionTestCaseResultView(TestCaseResultMixin, BaseSolutionTestDataView):
    def do_get(self, request, solution, testcaseresult_id):
        if solution.best_judgement_id is None:
            raise Http404('Solution is not judged')

        testcaseresult = get_object_or_404(TestCaseResult, id=testcaseresult_id, judgement_id=solution.best_judgement_id)
        return self.serve_testcaseresult_page(testcaseresult, 'solutions:test_data', 'solutions:test_image', solution.id, self.permissions.can_refer_to_problem)


class SolutionTestCaseResultDataView(TestCaseResultMixin, BaseSolutionTestDataView):
    def do_get(self, request, solution, testcaseresult_id, mode):
        if solution.best_judgement_id is None:
            raise Http404('Solution is not judged')

        testcaseresult = get_object_or_404(TestCaseResult, id=testcaseresult_id, judgement_id=solution.best_judgement_id)
        return self.serve_testcaseresult_data(mode, testcaseresult)


class SolutionTestCaseResultImageView(TestCaseResultMixin, BaseSolutionTestDataView):
    def do_get(self, request, solution, testcaseresult_id, filename):
        if solution.best_judgement_id is None:
            raise Http404('Solution is not judged')

        testcaseresult = get_object_or_404(TestCaseResult, id=testcaseresult_id, judgement_id=solution.best_judgement_id)
        return self.serve_testcaseresult_image(filename, testcaseresult)


class SolutionPlagiarismView(BaseSolutionView):
    tab = 'plagiarism'
    template_name = 'solutions/solution/plagiarism.html'
    paginate_by = 25

    def is_allowed(self, permissions):
        return permissions.can_view_plagiarism_score or permissions.can_view_plagiarism_details

    def do_get(self, request, solution):
        plagiarism_judgements = JudgementResult.\
            objects.filter(solution_to_judge=solution).all().\
            select_related('solution_to_compare').\
            select_related('solution_to_compare__author').\
            order_by('-similarity', '-solution_to_compare__reception_time')

        aggregated_result = AggregatedResult.objects.filter(id=solution.id).first()

        context = paginate(request, plagiarism_judgements, self.paginate_by)
        context = self.get_context_data(aggregated_result=aggregated_result, **context)
        return render(request, self.template_name, context)


class SolutionRejudgeView(LoginRequiredMixin, generic.View):
    def post(self, request, solution_id):
        solution = get_object_or_404(Solution, pk=solution_id)
        permissions, _ = calculate_permissions(solution, request.user)

        if not permissions.can_rejudge:
            raise Http404('Not allowed to rejudge')

        with transaction.atomic():
            notifier, rejudge = bulk_rejudge(Solution.objects.filter(pk=solution_id), self.request.user)
        notifier.notify()
        return redirect('solutions:rejudge', rejudge.id)

class SolutionTogglePlagiarismView(ProblemEditorMemberRequiredMixin, generic.View):
    def post(self, request, solution_id):
        solution = get_object_or_404(Solution, pk=solution_id)
        
        if solution.is_cheater:
            solution.is_plagiarism = False
        else:
            solution.is_plagiarism = True
            
        solution.save(update_fields=['is_plagiarism'])
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('solutions:main', solution_id=solution.id)