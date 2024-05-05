# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import logging
from collections import defaultdict, Counter

from django.core.management.base import BaseCommand
from django.db.models import Count

from storage.resource_id import HASH_SIZE
from users.models import UserProfile
from problems.models import TestCase, TestCaseValidation, ProblemRelatedFile, ProblemRelatedSourceFile
from solutions.models import AdHocRun, JudgementLog, TestCaseResult, Challenge, ChallengedSolution
from storage.models import FileMetadata


class ResourceCollector(object):
    def __init__(self, simple):
        self._count = Counter()
        self._stat = defaultdict(Counter) if not simple else None

    def add(self, resource_id, tag, cnt=1):
        if resource_id is None:
            return

        blob = resource_id.get_binary()
        if len(blob) < HASH_SIZE:
            return

        key = str(resource_id)
        self._count[key] += cnt
        if self._stat is not None:
            self._stat[str(resource_id)][tag] += cnt

    @property
    def size(self):
        return len(self._count)

    def dump(self, path):
        with open(path, 'w') as fd:
            for k in sorted(self._count):
                tokens = [k, str(self._count[k])]
                if self._stat is not None:
                    tokens.append(json.dumps(self._stat[k], sort_keys=True))
                fd.write('\t'.join(tokens) + '\n')


class Command(BaseCommand):
    help = 'Dumps resource ids that are currently in use in DB'

    def add_arguments(self, parser):
        parser.add_argument('dump', help='tsv file')
        parser.add_argument('-s', '--simple', help='no details, just count references (faster)', action='store_true')

    def handle(self, *args, **options):
        logger = logging.getLogger('irunner_import')
        collector = ResourceCollector(options['simple'])

        prev = [0]

        def log_new():
            cur = collector.size
            logger.info('< got %d (+%d)', cur, cur - prev[0])
            prev[0] = cur

        logger.info('> UserProfile')
        for photo, photo_thumbnail in UserProfile.objects.values_list('photo', 'photo_thumbnail'):
            collector.add(photo, 'photo')
            collector.add(photo_thumbnail, 'photo_thumbnail')
        log_new()

        logger.info('> TestCase')
        for inp, ans in TestCase.objects.values_list('input_resource_id', 'answer_resource_id').iterator():
            collector.add(inp, 'testcase_input')
            collector.add(ans, 'testcase_answer')
        log_new()

        logger.info('> TestCaseValidation')
        for inp, in TestCaseValidation.objects.values_list('input_resource_id').iterator():
            collector.add(inp, 'validation_input')
        log_new()

        logger.info('> AdHocRun')
        for r, in AdHocRun.objects.values_list('resource_id'):
            collector.add(r, 'adhoc')
        log_new()

        logger.info('> JudgementLog')
        for r, in JudgementLog.objects.values_list('resource_id'):
            collector.add(r, 'log')
        log_new()

        FIELDS = [
            ('input_resource_id', 'testcaseresult_input'),
            ('output_resource_id', 'testcaseresult_output'),
            ('answer_resource_id', 'testcaseresult_answer'),
            ('stdout_resource_id', 'testcaseresult_stdout'),
            ('stderr_resource_id', 'testcaseresult_stderr'),
        ]

        batch_last_id = 0
        batch_size = 100000
        while True:
            logger.info('> TestCaseResult (id > %d)', batch_last_id)
            test_case_qs = TestCaseResult.objects.\
                filter(id__gt=batch_last_id).\
                values_list('id', *[field for field, _ in FIELDS]).\
                order_by('id')[:batch_size]
            test_cases = list(test_case_qs)
            if len(test_cases) == 0:
                break
            for i, t in enumerate(FIELDS):
                fn, stat = t
                for testcase in test_cases:
                    collector.add(testcase[i+1], stat)
            batch_last_id = test_cases[-1][0]

        log_new()

        logger.info('> Challenge')
        for inp, in Challenge.objects.values_list('input_resource_id'):
            collector.add(inp, 'challenge_input')
        log_new()

        logger.info('> ChallengedSolution')
        for ouf, stdout, stderr in ChallengedSolution.objects.values_list(
                'output_resource_id',
                'stdout_resource_id',
                'stderr_resource_id',
                ):
            collector.add(ouf, 'challenge_output')
            collector.add(stdout, 'challenge_stdout')
            collector.add(stderr, 'challenge_stderr')
        log_new()

        for model in (ProblemRelatedFile, ProblemRelatedSourceFile, FileMetadata):
            logger.info('> %s', model.__name__)
            for r in model.objects.values_list('resource_id', flat=True).iterator():
                collector.add(r, 'metadata')
            log_new()
        collector.dump(options['dump'])
