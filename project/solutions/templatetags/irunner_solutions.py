# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from collections import namedtuple
import uuid

from django import template
from django.utils.encoding import smart_text
from django.utils.html import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from common.outcome import Outcome
from problems.calcpermissions import has_limited_problems_queryset
from proglangs.utils import get_ace_mode
from solutions.models import Judgement, JudgementLog
from solutions.permissions import SolutionPermissions
from storage.storage import create_storage

register = template.Library()

TWO_LETTER_OUTCOME_CODES = {
    Outcome.ACCEPTED: 'OK',
    Outcome.COMPILATION_ERROR: 'CE',
    Outcome.WRONG_ANSWER: 'WA',
    Outcome.TIME_LIMIT_EXCEEDED: 'TLE',
    Outcome.MEMORY_LIMIT_EXCEEDED: 'MLE',
    Outcome.IDLENESS_LIMIT_EXCEEDED: 'ILE',
    Outcome.RUNTIME_ERROR: 'RTE',
    Outcome.PRESENTATION_ERROR: 'PE',
    Outcome.SECURITY_VIOLATION: 'SV',
    Outcome.CHECK_FAILED: 'CF',
    Outcome.FAILED: 'FL',
}

ONE_LETTER_STATUS_CODES = {
    Judgement.COMPILING: 'C',
    Judgement.TESTING: 'T',
}

ELLIPSIS = '…'


def _get_style(outcome, code):
    if outcome == Outcome.ACCEPTED:
        return 'ok' if not settings.APRIL_FOOLS_DAY_MODE else 'fail'
    elif code not in (None, ELLIPSIS):
        return 'fail' if not settings.APRIL_FOOLS_DAY_MODE else 'ok'
    else:
        return ''


@register.inclusion_tag('solutions/irunner_solutions_box_tag.html')
def irunner_solutions_judgementbox(judgement, tooltip=False, complete=True, block=False):
    '''
    Displays judgement state.

    args:
        judgement(solutions.models.Judgement)
        tooltip: show hint (localized explanation) in tooltip
    '''
    context = {
        'code': '—',
        'style': '',
        'test_no': 0,
        'tooltip': '',
        'block': block,
    }

    if judgement is not None:
        if judgement.status == Judgement.DONE:
            if complete or (judgement.sample_tests_passed is False):
                code = TWO_LETTER_OUTCOME_CODES.get(judgement.outcome)
                
                # --- LOGIC FOR PLAGIARISM ---
                is_plag = getattr(judgement.solution, 'is_cheater', False)
                if judgement.outcome == Outcome.ACCEPTED and is_plag:
                    context['code'] = 'OKC'   # <--- Replaced AC with OKC
                    context['style'] = 'fail' 
                else:
                    context['code'] = code
                    context['style'] = _get_style(judgement.outcome, code)
                # ---------------------------

                if judgement.outcome == Outcome.ACCEPTED:
                    context['test_no'] = 0
                else:
                    context['test_no'] = 0
            else:
                context['code'] = 'OKC' # <--- Just in case, replacing it here too (if status is still "in progress", but already AC)
                context['style'] = 'pending'
        else:
            context['code'] = ONE_LETTER_STATUS_CODES.get(judgement.status, ELLIPSIS)
            if complete:
                context['test_no'] = 0

    if tooltip:
        # Change tooltip on hover
        if judgement is not None and getattr(judgement.solution, 'is_cheater', False) and judgement.outcome == Outcome.ACCEPTED:
            context['tooltip'] = 'OK (Cheater)' # <--- Slightly changed the tooltip text for better appearance
        else:
            context['tooltip'] = judgement.show_status(complete)

    return context


@register.simple_tag(takes_context=False)
def irunner_solutions_judgementtext(judgement, complete=True):
    '''
    Displays judgement state as text (i. e. "Wrong Answer (42)").
    '''
    text = ''
    if judgement is not None:
        # Replace the full text
        if getattr(judgement.solution, 'is_cheater', False) and judgement.outcome == Outcome.ACCEPTED:
            text = 'OK (Cheater)' # <--- Replaced Accepted (Cheater) with OK (Cheater)
        else:
            text = judgement.show_status(complete)

    return text


def _find_in_choices(choices, what):
    for pair in choices:
        if pair[0] == what:
            return pair[1]
    return ''


@register.inclusion_tag('solutions/irunner_solutions_box_tag.html')
def irunner_solutions_outcomebox(outcome, tooltip=False, block=False):
    '''
    Displays outcome for a single test.

    args:
        outcome(int): value of solutions.models.Outcome enum
    '''
    if outcome is not None:
        code = TWO_LETTER_OUTCOME_CODES.get(outcome, ELLIPSIS)
        context = {
            'block': block,
            'code': code,
            'style': _get_style(outcome, code),
            'tooltip': _find_in_choices(Outcome.CHOICES, outcome) if tooltip else '',
        }
    else:
        context = {
            'block': block,
        }
    return context


@register.simple_tag(takes_context=False)
def irunner_solutions_scorebox(judgement=None, hide_score_if_accepted=False, accepted_before_deadline=True):
    '''
    Displays score for a judgement.

    args:
        judgement
    '''

    classes = ['ir-box', 'ir-scorebox']
    contents = '\u200B'
    title = ''

    if judgement is not None:
        accepted = (judgement.outcome == Outcome.ACCEPTED)

        if accepted:
            if accepted_before_deadline:
                classes.append('ir-scorebox-accepted')
            else:
                classes.append('ir-scorebox-accepted-after-deadline')
                title = _('Accepted after deadline')
        else:
            classes.append('ir-scorebox-attempted')

        if accepted and hide_score_if_accepted:
            pass
        else:
            if judgement.score == judgement.max_score or judgement.max_score >= 1000 or judgement.max_score == 0:
                contents = '{0}'.format(judgement.score)
            else:
                contents = '{0}&thinsp;/&thinsp;{1}'.format(judgement.score, judgement.max_score)

    if not title:
        return mark_safe('<div class="{0}">{1}</div>'.format(' '.join(classes), contents))
    else:
        return mark_safe('<div class="{0}" title="{2}">{1}</div>'.format(' '.join(classes), contents, title))


@register.simple_tag(takes_context=False)
def irunner_solutions_scorecell(judgement=None, accepted_before_deadline=True):
    '''
    Displays score for a judgement.

    args:
        judgement
    '''

    classes = ['ir-scorecell']
    contents = ''

    if judgement is not None:
        accepted = (judgement.outcome == Outcome.ACCEPTED)

        if accepted:
            if accepted_before_deadline:
                classes.append('ir-scorebox-accepted')
                contents = _('Accepted')
            else:
                classes.append('ir-scorebox-accepted-after-deadline')
                contents = _('Accepted after deadline')
        else:
            classes.append('ir-scorebox-attempted')

        if not contents and judgement.score != judgement.max_score:
            contents = '{0}&thinsp;/&thinsp;{1}'.format(judgement.score, judgement.max_score)
    if contents:
        return mark_safe('<td class="{}" title="{}"></td>'.format(' '.join(classes), contents))
    else:
        return mark_safe('<td class="{}"></td>'.format(' '.join(classes)))


TestResultColumns = namedtuple('TestResultColumns', ['verbose_outcome', 'score', 'exit_code', 'checker_message', 'tooltip'])


@register.inclusion_tag('solutions/irunner_solutions_testresults_tag.html')
def irunner_solutions_testresults(test_results, permissions, url_pattern=None, first_placeholder=None, compact=False):
    '''
    Displays a table with results per test.

    args:
        compact: if is true, the table fits better in a limited-width region
    '''
    if not isinstance(permissions, SolutionPermissions):
        raise TypeError('SolutionPermissions required')

    any_toggleable = False
    some_tests_hidden = False

    pairs = []
    for test in test_results:
        is_sample_may_be_expanded = permissions.can_view_sample_results and test.is_sample
        if not (permissions.can_view_results or is_sample_may_be_expanded):
            some_tests_hidden = True
            continue
        toggleable = (url_pattern is not None) and (permissions.can_view_tests_data or is_sample_may_be_expanded)
        any_toggleable |= toggleable
        pairs.append((test, toggleable))

    columns = TestResultColumns(
        verbose_outcome=(not compact and not permissions.can_view_checker_messages),
        exit_code=(not compact and permissions.can_view_exit_codes),
        checker_message=(not compact and permissions.can_view_checker_messages),
        tooltip=(compact or permissions.can_view_exit_codes or permissions.can_view_checker_messages),
        score=True,
    )
    span_columns_cnt = (
        (compact * 2) + 3 +
        columns.verbose_outcome + columns.score +
        columns.exit_code + columns.checker_message
    )

    uid = smart_text(uuid.uuid1().hex)
    return {
        'test_results': pairs,
        'url_pattern': url_pattern,
        'first_placeholder': first_placeholder,
        'uid': uid,
        'any_toggleable': any_toggleable,
        'columns': columns,
        'span_columns_cnt': span_columns_cnt,
        'compact': compact,
        'some_tests_hidden': some_tests_hidden,
    }


def _prepare_limit(actual, limit, preparer):
    if limit:
        clamped = min(max(0, actual), limit)
        percent = int(round(100.0 * clamped / limit))
    else:
        percent = 0

    return {
        'actual': preparer(actual),
        'limit': preparer(limit),
        'percent': percent,
    }


@register.inclusion_tag('solutions/irunner_solutions_timelimitbox_tag.html')
def irunner_solutions_timelimitbox(actual, limit):
    return _prepare_limit(actual, limit, lambda x: float(x) / 1000)


@register.inclusion_tag('solutions/irunner_solutions_memorylimitbox_tag.html')
def irunner_solutions_memorylimitbox(actual, limit):
    return _prepare_limit(actual, limit, lambda x: x // 1024)


@register.inclusion_tag('solutions/irunner_solutions_livesubmission_tag.html')
def irunner_solutions_livesubmission(solution_id):
    assert solution_id is not None
    return {
        'solution_id': solution_id,
        'uid': uuid.uuid1().hex,
        'red_style': 'danger' if not settings.APRIL_FOOLS_DAY_MODE else 'success',
        'green_style': 'success' if not settings.APRIL_FOOLS_DAY_MODE else 'danger',
    }


@register.inclusion_tag('solutions/irunner_solutions_rejudgestate_tag.html')
def irunner_solutions_rejudgestate(committed):
    return {'committed': committed}


GENERAL_FAILURE_MESSAGES = {
    'UNKNOWN': _('unknown error'),
    'CHECKER_NOT_COMPILED': _('error while compiling checker'),
    'VALIDATOR_NOT_COMPILED': _('error while compiling validator'),
    'UNKNOWN_PROGRAMMING_LANGUAGE': _('compiler is not available for the testing module'),
}


@register.inclusion_tag('solutions/irunner_solutions_checkfailed_tag.html')
def irunner_solutions_checkfailed(extra_info):
    context = {}
    if extra_info:
        context['reason'] = GENERAL_FAILURE_MESSAGES.get(extra_info.general_failure_reason, extra_info.general_failure_reason)
        context['message'] = extra_info.general_failure_message

        if extra_info.general_failure_reason == 'CHECKER_NOT_COMPILED':
            log = JudgementLog.objects.filter(judgement_id=extra_info.judgement_id, kind=JudgementLog.CHECKER_COMPILATION).first()
            if log is not None:
                storage = create_storage()
                context['log_repr'] = storage.represent(log.resource_id)
    return context


@register.inclusion_tag('solutions/irunner_solutions_sourcelink_tag.html')
def irunner_solutions_sourcelink(solution):
    return {
        'solution': solution,
    }


@register.inclusion_tag('solutions/irunner_solutions_limited_tag.html', takes_context=True)
def irunner_solutions_limited(context):
    user = context['user']
    return {
        'limited_access': has_limited_problems_queryset(user)
    }


@register.inclusion_tag('solutions/irunner_solutions_submit_tag.html')
def irunner_solutions_submit(form, get_attempts_url=None):
    ace_modes = [(compiler.id, get_ace_mode(compiler.language)) for compiler in form.fields['compiler'].queryset]
    return {
        'form': form,
        'get_attempts_url': get_attempts_url,
        'ace_modes': ace_modes,
    }
