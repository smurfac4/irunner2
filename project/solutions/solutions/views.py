from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext_lazy
from django.views import generic
from django.views.generic.base import View

from cauth.mixins import StaffMemberRequiredMixin, ProblemEditorMemberRequiredMixin
from common.pagination import paginate
from common.views import MassOperationView
from problems.calcpermissions import get_problem_ids_queryset, has_limited_problems_queryset

from solutions.filters import apply_state_filter, apply_compiler_filter, apply_difficulty_filter
from solutions.forms import AllSolutionsFilterForm
from solutions.models import Solution


'''
All solutions list
'''


class SolutionListView(ProblemEditorMemberRequiredMixin, generic.View):
    paginate_by = 25
    template_name = 'solutions/solution_list.html'

    def get(self, request):
        form = AllSolutionsFilterForm(request.GET)

        queryset = Solution.objects.\
            prefetch_related('compiler').\
            prefetch_related('problem').\
            prefetch_related('author').\
            select_related('best_judgement').\
            prefetch_related('source_code').\
            prefetch_related('aggregatedresult').\
            defer('ip_address', 'stop_on_fail', 'source_code__resource_id', 'best_judgement__rejudge_id', 'best_judgement__judgement_before_id').\
            order_by('-id')

        if has_limited_problems_queryset(request.user):
            queryset = queryset.filter(problem_id__in=get_problem_ids_queryset(request.user))

        if form.is_valid():
            queryset = apply_state_filter(queryset, form.cleaned_data['state'])
            queryset = apply_compiler_filter(queryset, form.cleaned_data['compiler'])

            user_id = form.cleaned_data.get('user')
            if user_id is not None:
                queryset = queryset.filter(author_id=user_id)

            problem_id = form.cleaned_data.get('problem')
            if problem_id is not None:
                queryset = queryset.filter(problem_id=problem_id)

            difficulty = form.cleaned_data.get('difficulty')
            if difficulty is not None:
                queryset = apply_difficulty_filter(queryset, difficulty)

        context = paginate(request, queryset, self.paginate_by, allow_all=False, show_total_count=request.user.is_staff)
        context['form'] = form
        return render(request, self.template_name, context)


'''
Mass delete
'''


class DeleteSolutionsView(StaffMemberRequiredMixin, MassOperationView):
    '''
    Staff member is allowed to delete any solution.
    '''
    template_name = 'solutions/confirm_multiple.html'

    def get_context_data(self, **kwargs):
        context = super(DeleteSolutionsView, self).get_context_data(**kwargs)
        context['action'] = ugettext_lazy('delete')
        return context

    def perform(self, filtered_queryset, form):
        filtered_queryset.delete()

    def get_queryset(self):
        return Solution.objects.order_by('id')


class TogglePlagiarismView(ProblemEditorMemberRequiredMixin, View):
    def post(self, request, solution_id):
        solution = get_object_or_404(Solution, pk=solution_id)
        solution.is_plagiarism = not solution.is_plagiarism
        solution.save(update_fields=['is_plagiarism'])
        return redirect(request.META.get('HTTP_REFERER', 'solutions:solution_plagiarism', solution.id))