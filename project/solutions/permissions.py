# -*- coding: utf-8 -*-

from collections import namedtuple

from django.utils.translation import ugettext_lazy as _

from common.access import Permissions


class SolutionAccessLevel(object):
    '''
    Helper class to use in course/contest settings to set up access level of students/contestants.
    '''
    NO_ACCESS = 0
    STATE = 10
    COMPILATION_LOG = 20
    SOURCE_CODE = 30
    TESTING_DETAILS_ON_SAMPLE_TESTS = 40
    TESTING_DETAILS = 50
    TESTING_DETAILS_CHECKER_MESSAGES = 60
    TESTING_DETAILS_TEST_DATA = 70

    FULL = TESTING_DETAILS_TEST_DATA

    CHOICES = (
        (NO_ACCESS, _('no access')),
        (STATE, _('view current solution state')),
        (COMPILATION_LOG, _('view compilation log')),
        (SOURCE_CODE, _('view source code')),
        (TESTING_DETAILS_ON_SAMPLE_TESTS, _('view testing details on sample tests')),
        (TESTING_DETAILS, _('view testing details')),
        (TESTING_DETAILS_CHECKER_MESSAGES, _('view testing details with checker messages')),
        (TESTING_DETAILS_TEST_DATA, _('view testing details and test data')),
    )


class SolutionPermissions(Permissions):
    VIEW_STATE_ON_SAMPLES = 1 << 0
    VIEW_STATE = 1 << 1
    VIEW_COMPILATION_LOG = 1 << 2
    VIEW_SOURCE_CODE = 1 << 3
    VIEW_SAMPLE_RESULTS = 1 << 4  # includes the full sample test data and outputs
    VIEW_RESULTS = 1 << 5
    VIEW_EXIT_CODES = 1 << 6
    VIEW_CHECKER_MESSAGES = 1 << 7
    VIEW_TESTS_DATA = 1 << 8
    VIEW_ATTEMPTS = 1 << 9

    # special permissions that are not included into the levels above
    VIEW_PLAGIARISM_SCORE = 1 << 10
    VIEW_PLAGIARISM_DETAILS = 1 << 11
    VIEW_JUDGEMENTS = 1 << 12
    VIEW_IP_ADDRESS = 1 << 13
    REJUDGE = 1 << 14
    REFER_TO_PROBLEM = 1 << 15

    def update(self, level):
        if level >= SolutionAccessLevel.STATE:
            self.allow_view_state_on_samples()
            self.allow_view_state()

        if level >= SolutionAccessLevel.COMPILATION_LOG:
            self.allow_view_compilation_log()

        if level >= SolutionAccessLevel.SOURCE_CODE:
            self.allow_view_attempts()
            self.allow_view_source_code()

        if level >= SolutionAccessLevel.TESTING_DETAILS_ON_SAMPLE_TESTS:
            self.allow_view_sample_results()

        if level >= SolutionAccessLevel.TESTING_DETAILS:
            self.allow_view_results()

        if level >= SolutionAccessLevel.TESTING_DETAILS_CHECKER_MESSAGES:
            self.allow_view_checker_messages()

        if level >= SolutionAccessLevel.TESTING_DETAILS_TEST_DATA:
            self.allow_view_tests_data()
            self.allow_view_exit_codes()


# course/contest the solution belongs to
SolutionEnvironment = namedtuple('SolutionEnvironment', 'course link_to_course contest link_to_contest')
