# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from collections import namedtuple

from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.formats import number_format
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _

from common.constants import EMPTY_SELECT, make_empty_select
from common.outcome import Outcome
from problems.models import Problem
from solutions.models import Judgement, Solution
from solutions.permissions import SolutionAccessLevel
from solutions.submit.limit import ILimitPolicy

from .models import Contest, ContestSolution, Membership, ContestScoringPolicy
from .utils.problemstats import ProblemStats
from .utils.types import SolutionKind

LabeledProblem = namedtuple('LabeledProblem', 'letter problem stats')

LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
RECENT_CHANGES_WINDOW = timezone.timedelta(minutes=30)


def make_letter(x):
    result = []
    while x >= 0:
        x, r = divmod(x, len(LETTERS))
        result.append(LETTERS[r])
        x -= 1
    return ''.join(reversed(result))


def make_lettered_name(letter, name):
    if name:
        return '{0}: {1}'.format(letter, name)
    else:
        return letter


def make_problem_choices(contest, empty_label=None):
    if empty_label is None:
        empty_label = make_empty_select(_('Problem'))

    result = []
    result.append((None, empty_label))
    for i, problem in enumerate(contest.get_problems()):
        text = make_lettered_name(make_letter(i), problem.unnumbered_brief_name())
        result.append((problem.id, text))
    return tuple(result)


def make_contestant_choices(contest, empty_label=None):
    if empty_label is None:
        empty_label = make_empty_select(_('Contestant'))

    result = []
    result.append((None, empty_label))
    for user in contest.members.filter(contestmembership__role=Membership.CONTESTANT):
        result.append((user.id, user.get_full_name()))
    return tuple(result)


def total_minutes(td):
    return total_seconds(td) // 60


def total_seconds(td):
    return td.days * 24 * 60 * 60 + td.seconds


def _format_score(score):
    return number_format(score, force_grouping=True)


class ProblemResolver(object):
    def __init__(self, contest):
        self._problems = {}
        self._letters = {}
        for i, problem in enumerate(contest.get_problems()):
            letter = make_letter(i)
            problem_id = force_text(problem.id)
            self._letters[problem_id] = letter
            self._problems[problem_id] = make_lettered_name(letter, problem.short_name)

    def get_problem_name(self, problem_id):
        name = self._problems.get(force_text(problem_id))
        if name is None:
            # fallback
            problem = Problem.objects.filter(pk=problem_id).first()
            if problem is not None:
                name = problem.unnumbered_brief_name()
            else:
                name = EMPTY_SELECT
        return name

    def get_letter(self, problem_id):
        return self._letters.get(force_text(problem_id), '')


class ContestTiming(object):
    '''
    This class knows nothing about permissions and access rights.
    It is responsible for time only.
    '''
    BEFORE = 0
    IN_PROGRESS = 1
    AFTER = 2

    def get(self):
        return self._status

    def is_freeze_applicable(self):
        return self._freeze_applicable

    def get_time_passed(self):
        return self._time_passed

    def get_time_total(self):
        return self._time_total

    def get_time_before(self):
        return self._time_before

    def __init__(self, contest):
        ts = timezone.now().replace(microsecond=0)

        self._time_passed = None
        self._time_total = contest.duration
        self._time_before = None

        if ts < contest.start_time:
            self._status = ContestTiming.BEFORE
            self._time_before = contest.start_time - ts

        elif ts < contest.start_time + contest.duration:
            self._status = ContestTiming.IN_PROGRESS
            self._time_passed = ts - contest.start_time

        else:
            self._status = ContestTiming.AFTER
            self._time_passed = contest.duration

        self._freeze_applicable = False
        if contest.freeze_time is not None:
            if self._status == ContestTiming.IN_PROGRESS:
                if ts >= contest.start_time + contest.freeze_time:
                    self._freeze_applicable = True
            elif self._status == ContestTiming.AFTER:
                if not contest.unfreeze_standings:
                    self._freeze_applicable = True


ColumnPresence = namedtuple('ColumnPresence', 'solved_problem_count penalty_time total_score')
RunDescription = namedtuple('RunDescription', 'user labeled_problem when kind solution_id')
ContestResults = namedtuple('ContestResults', [
    'contest', 'contest_descr', 'frozen', 'user_results', 'all_runs',
    'last_success', 'last_run', 'column_presence'
])

# cs here means 'ContestSolution'


def _get_judgement(cs):
    # TODO: Speedup select_related('fixed_judgement')
    # return cs.fixed_judgement if cs.fixed_judgement is not None else cs.solution.best_judgement
    return cs.solution.best_judgement


def _get_kind(cs, freeze_time, show_pending_runs):
    if (freeze_time is not None) and (cs.solution.reception_time >= freeze_time):
        return SolutionKind.PENDING if show_pending_runs else None

    judgement = _get_judgement(cs)

    if judgement is not None and judgement.status == Judgement.DONE:
        if judgement.outcome == Outcome.COMPILATION_ERROR:
            # skip CE (compatibility, this case is included into 'sample_tests_passed is False')
            return None
        if judgement.sample_tests_passed is False:
            return None
        if judgement.outcome == Outcome.ACCEPTED:
            return SolutionKind.ACCEPTED
        elif judgement.outcome == Outcome.CHECK_FAILED:
            return SolutionKind.PENDING
        else:
            return SolutionKind.REJECTED
    else:
        return SolutionKind.PENDING


def _get_score(cs):
    judgement = _get_judgement(cs)
    assert (judgement is not None) and (judgement.status == Judgement.DONE)
    return (judgement.score, judgement.max_score)


def _make_contest_results(contest, frozen, user_result_class, column_presence, user_regex):
    contest_descr = ContestDescr(contest)

    # fetch all contestants from the contest
    users = contest.members.filter(contestmembership__role=Membership.CONTESTANT).select_related('userprofile')
    user_id_result = {}
    for user in users:
        if user_regex is not None:
            if not user_regex.match(user.username):
                continue
        user_id_result[user.id] = user_result_class(contest_descr, user)

    # fetch solutions
    queryset = ContestSolution.objects.\
        filter(contest=contest).\
        filter(is_disqualified=False).\
        filter(solution__reception_time__gte=contest.start_time, solution__reception_time__lt=contest.start_time+contest.duration).\
        select_related('solution', 'solution__best_judgement').\
        order_by('solution__reception_time')

    freeze_time = None
    if frozen and (contest.freeze_time is not None):
        freeze_time = contest.start_time + contest.freeze_time

    all_runs = []
    last_success = None
    last_run = None

    ts_now = timezone.now()

    for cs in queryset:
        user_result = user_id_result.get(cs.solution.author_id)
        if user_result is None:
            # The user is a juror or a contestant that has been excluded from the contest.
            continue

        problem_index = contest_descr.get_problem_index(cs.solution.problem_id)
        if problem_index is None:
            # The problem has been excluded from the contest.
            continue

        user_result.has_any_submissions = True

        kind = _get_kind(cs, freeze_time, contest.show_pending_runs)
        if kind is None:
            continue

        user_result.has_valid_submissions = True

        score = None
        if (kind is SolutionKind.REJECTED) or (kind is SolutionKind.ACCEPTED):
            # no score for pending runs
            score = _get_score(cs)

        labeled_problem = contest_descr.labeled_problems[problem_index]

        received = cs.solution.reception_time
        when = received - contest.start_time
        penalty_time = total_minutes(when)

        problem_result = user_result.get_problem_result(problem_index)
        registered = problem_result.register_solution(kind, penalty_time, score)
        if registered:
            labeled_problem.stats.register_solution(kind)

        if received + RECENT_CHANGES_WINDOW >= ts_now:
            problem_result.notify_recently_updated()

        run = RunDescription(user_result.user, labeled_problem, when, kind, cs.solution_id)
        all_runs.append(run)
        last_run = run
        if kind == SolutionKind.ACCEPTED:
            last_success = run

    user_results = user_id_result.values()
    for user_result in user_results:
        user_result.finalize()

    # order the table
    user_results = sorted(user_results, key=lambda x: x.get_key())

    # put places
    place = 0
    tag = 0
    for i, user_result in enumerate(user_results):
        if (i == 0) or (user_results[i - 1].get_key() != user_results[i].get_key()):
            place = i
        if (i > 0) and (user_results[i - 1].get_tag_key() != user_results[i].get_tag_key()):
            tag = tag ^ 1

        user_result.set_place(place + 1)
        user_result.set_row_tag(tag)

    return ContestResults(contest, contest_descr, frozen, user_results, all_runs,
                          last_success, last_run, column_presence)


class ContestDescr(object):
    def __init__(self, contest):
        self.labeled_problems = []
        self._problem_id_to_index = {}

        for i, problem in enumerate(contest.get_problems()):
            self.labeled_problems.append(LabeledProblem(make_letter(i), problem, ProblemStats()))
            self._problem_id_to_index[problem.id] = i

    def get_problem_index(self, problem_id):
        return self._problem_id_to_index.get(problem_id)


REJECTED_SUBMISSION_PENALTY = 20


class ProblemResultBase(object):
    def __init__(self):
        self._updated_recently = False

    def notify_recently_updated(self):
        self._updated_recently = True

    def is_recently_updated(self):
        return self._updated_recently


class ACMProblemResult(ProblemResultBase):
    def __init__(self):
        super(ACMProblemResult, self).__init__()
        self._kind = SolutionKind.REJECTED
        self._num_submissions = 0  # including the accepted one
        self._acceptance_time = None

    def is_ok(self):
        return (self._kind == SolutionKind.ACCEPTED)

    def get_penalty_time(self):
        if self._kind == SolutionKind.ACCEPTED:
            return self._acceptance_time + (self._num_submissions - 1) * REJECTED_SUBMISSION_PENALTY
        else:
            return 0

    def get_acceptance_time(self):
        return self._acceptance_time

    def register_solution(self, kind, penalty_time, score):
        if self._kind == SolutionKind.PENDING:
            self._num_submissions += 1
            return True
        if self._kind == SolutionKind.REJECTED:
            self._kind = kind
            self._num_submissions += 1
            if kind == SolutionKind.ACCEPTED:
                self._acceptance_time = penalty_time
            return True
        return False

    def as_html(self):
        result = ''
        if self._kind == SolutionKind.ACCEPTED:
            number = '+' if self._num_submissions == 1 else '+{0}'.format(self._num_submissions - 1)
            hours, minutes = divmod(self._acceptance_time, 60)
            result = '<span class="ir-accepted">{0}</span><br><span class="ir-ts">{1}:{2:02d}</span>'.format(number, hours, minutes)
        elif self._kind == SolutionKind.PENDING:
            result = '<span class="ir-pending">?{0}</span>'.format(self._num_submissions)
        elif self._kind == SolutionKind.REJECTED:
            if self._num_submissions == 0:
                result = '.'
            else:
                result = '<span class="ir-rejected">−{0}</span>'.format(self._num_submissions)
        return mark_safe(result)


class IOIProblemResultBase(ProblemResultBase):
    def __init__(self):
        super(IOIProblemResultBase, self).__init__()
        self._score = None
        self._max_score = None

    def get_score(self):
        return self._score

    def as_html(self):
        if self._score is None:
            result = '.'
        else:
            score_str = _format_score(self._score)
            if self._max_score == 0 or self._score > self._max_score:
                result = score_str
            elif self._score == self._max_score:
                result = '<span class="ir-accepted">{0}</span>'.format(score_str)
            else:
                result = '<span class="ir-rejected">{0}</span>'.format(score_str)
        return mark_safe(result)


class IOIProblemResultLast(IOIProblemResultBase):
    def register_solution(self, kind, penalty_time, score):
        if score is not None:
            self._score, self._max_score = score
            return True
        return False


class IOIProblemResultMax(IOIProblemResultBase):
    def register_solution(self, kind, penalty_time, score):
        if score is not None:
            s, ms = score
            if (self._score is None) or (self._score <= s):
                self._score, self._max_score = s, ms
            return True
        return False


class UserResultBase(object):
    def __init__(self, user, problem_results):
        self.user = user
        self.problem_results = problem_results
        self.members = user.userprofile.members
        self._place = None
        self._row_tag = None
        self.has_any_submissions = False
        self.has_valid_submissions = False

    def get_problem_result(self, problem_index):
        return self.problem_results[problem_index]

    def set_place(self, place):
        self._place = place

    def set_row_tag(self, tag):
        self._row_tag = tag

    def get_place(self):
        return self._place

    def get_row_tag(self):
        return self._row_tag

    def finalize(self):
        pass

    def get_key(self):
        raise NotImplementedError()

    def get_tag_key(self):
        raise NotImplementedError()


class ACMUserResult(UserResultBase):
    def __init__(self, contest_descr, user):
        super(ACMUserResult, self).__init__(user, [ACMProblemResult() for _ in contest_descr.labeled_problems])

        self._solved_problem_count = None
        self._penalty_time = None
        self._last_acceptance = None

    def finalize(self):
        self._solved_problem_count = sum(pr.is_ok() for pr in self.problem_results)
        self._penalty_time = sum(pr.get_penalty_time() for pr in self.problem_results)
        accepts = [pr.get_acceptance_time() for pr in self.problem_results if pr.get_acceptance_time() is not None]
        self._last_acceptance = max(accepts) if accepts else 0

    def get_solved_problem_count(self):
        return self._solved_problem_count

    def get_penalty_time(self):
        return self._penalty_time

    def get_key(self):
        return (-self._solved_problem_count, self._penalty_time, self._last_acceptance)

    def get_tag_key(self):
        return self._solved_problem_count


class IOIUserResultBase(UserResultBase):
    problem_result_class = None

    def __init__(self, contest_descr, user):
        super().__init__(user, [self.problem_result_class() for _ in contest_descr.labeled_problems])

        self._total_score = 0

    def finalize(self):
        self._total_score = sum(((pr.get_score() or 0) for pr in self.problem_results))

    def get_total_score(self):
        return self._total_score

    def get_total_score_str(self):
        return _format_score(self.get_total_score())

    def get_key(self):
        return (-self._total_score,)

    def get_tag_key(self):
        return self.get_key()


class IOIUserResultLast(IOIUserResultBase):
    problem_result_class = IOIProblemResultLast


class IOIUserResultMax(IOIUserResultBase):
    problem_result_class = IOIProblemResultMax


class IContestService(object):
    def __init__(self, contest):
        pass

    def get_no_standings_yet_message(self):
        raise NotImplementedError()

    def are_standings_available(self, permissions, timing):
        raise NotImplementedError()

    def should_stop_on_fail(self):
        raise NotImplementedError()

    def should_show_my_solutions_completely(self, timing):
        raise NotImplementedError()

    def make_contest_results(self, contest, frozen, user_regex=None):
        raise NotImplementedError()


def create_contest_service(contest):
    if contest.rules == Contest.ACM:
        return ACMContestService(contest)
    if contest.rules == Contest.IOI:
        return IOIContestService(contest)


class ACMContestService(IContestService):
    def get_no_standings_yet_message(self):
        return _('The scoreboard will be available after the start of the contest')

    def are_standings_available(self, permissions, timing):
        if timing.get() == ContestTiming.BEFORE:
            return permissions.standings_before
        return True

    def should_stop_on_fail(self):
        return True

    def should_show_my_solutions_completely(self, timing):
        return True

    def make_contest_results(self, contest, frozen, user_regex=None):
        return _make_contest_results(contest, frozen, ACMUserResult, ColumnPresence(True, True, False), user_regex)


class IOIContestService(IContestService):
    def __init__(self, contest):
        self._own_solutions_access = contest.contestant_own_solutions_access in (
            SolutionAccessLevel.TESTING_DETAILS,
            SolutionAccessLevel.TESTING_DETAILS_CHECKER_MESSAGES,
            SolutionAccessLevel.TESTING_DETAILS_TEST_DATA
        )

    def get_no_standings_yet_message(self):
        return _('The scoreboard is hidden')

    def are_standings_available(self, permissions, timing):
        t = timing.get()
        if t == ContestTiming.BEFORE:
            return permissions.standings_before
        elif t == ContestTiming.IN_PROGRESS:
            return permissions.standings_before or self._own_solutions_access
        else:
            return True

    def should_stop_on_fail(self):
        return False

    def should_show_my_solutions_completely(self, timing):
        return self._own_solutions_access or ((timing.get() == ContestTiming.AFTER) and (not timing.is_freeze_applicable()))

    def make_contest_results(self, contest, frozen, user_regex=None):
        if frozen:
            return None
        if contest.scoring_policy == ContestScoringPolicy.LAST_SOLUTION:
            user_result_cls = IOIUserResultLast
        elif contest.scoring_policy == ContestScoringPolicy.BEST_SOLUTION:
            user_result_cls = IOIUserResultMax
        else:
            user_result_cls = IOIUserResultLast if not self._own_solutions_access else IOIUserResultMax
        return _make_contest_results(contest, False, user_result_cls, ColumnPresence(False, False, True), user_regex)


class ContestAttemptLimitPolicy(ILimitPolicy):
    def __init__(self, contest, user):
        self._contest = contest
        self._user = user

    def get_solution_queryset(self):
        if not self._user.is_authenticated:
            return Solution.objects.none()
        else:
            return Solution.objects.filter(
                contestsolution__contest=self._contest,
                author=self._user
            )

    @property
    def attempt_limit(self):
        return self._contest.attempt_limit

    @property
    def total_attempt_limit(self):
        return self._contest.total_attempt_limit

    @property
    def time_period(self):
        return self._contest.time_period

    @property
    def file_size_limit(self):
        return self._contest.file_size_limit
