# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.template.defaultfilters import filesizeformat
from django.utils.timezone import make_aware

from solutions.models import Judgement, TestCaseResult
from storage.resource_id import ResourceId
from storage.storage_base import _get_data_directly
import logging
import argparse
import datetime

FORMAT = '%Y-%m-%d'


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, FORMAT)
    except ValueError:
        msg = 'Not a valid date: "{0}".'.format(s)
        raise argparse.ArgumentTypeError(msg)


def read_fs_dump(path):
    fs = {}
    with open(path) as fd:
        for line in fd:
            resource_id, size = line.rstrip().split('\t')[:2]
            fs[resource_id] = int(size)
    return fs


class Command(BaseCommand):
    help = 'Removes old judging results'

    def add_arguments(self, parser):
        parser.add_argument('date', help='YYYY-MM-DD', type=valid_date)
        parser.add_argument('fs_dump', help='tsv file')
        parser.add_argument('--do', action='store_true')
        parser.add_argument('--size-limit', type=int, default=2**20)

    def handle(self, *args, **options):
        logger = logging.getLogger('irunner_import')

        ts = make_aware(options['date'])
        fs = read_fs_dump(options['fs_dump'])
        size_limit = options['size_limit']
        logger.info('FS dump contains %d files', len(fs))

        last_judgement = Judgement.objects.filter(extra_info__finish_testing_time__lt=ts).order_by('-id').first()
        if last_judgement is None:
            logger.info('No judgements before %s found, exiting...', ts.strftime(FORMAT))
            return

        logger.info('Consider the judgements <= %d', last_judgement.id)

        batch_last_id = 0
        batch_size = 10000
        field_names = ['output_resource_id', 'stdout_resource_id', 'stderr_resource_id']
        while True:
            test_case_qs = TestCaseResult.objects.\
                filter(judgement_id__lte=last_judgement.id).\
                filter(id__gt=batch_last_id).\
                filter(
                    Q(output_resource_id__isnull=False) |
                    Q(stdout_resource_id__isnull=False) |
                    Q(stderr_resource_id__isnull=False)
                ).\
                values('id', 'judgement_id', *field_names).\
                order_by('id')[:batch_size]

            test_cases = list(test_case_qs)
            logger.info('Read %d test cases (id > %d)', len(test_cases), batch_last_id)
            if len(test_cases) == 0:
                break
            batch_last_id = test_cases[-1]['id']

            files_removed = 0
            total_size = 0

            for test_case in test_cases:
                testcase_id, judjement_id = test_case['id'], test_case['judgement_id']
                for field in field_names:
                    resource_id = test_case[field]
                    if resource_id is None:
                        continue
                    blob = _get_data_directly(resource_id)
                    if blob is not None:
                        continue
                    size = fs.get(str(resource_id))
                    if size is None:
                        logger.warning('Missing file %s', resource_id)
                        continue
                    if size <= size_limit:
                        continue
                    logger.info('Removing %s (%s, judgement=%d, test_case=%d, size=%d)', resource_id, field, judjement_id, testcase_id, size)
                    if options['do']:
                        row_count = TestCaseResult.objects.filter(id=testcase_id).update(**{field: None})
                        if row_count != 1:
                            logger.warning('Update of test case result %d failed', testcase_id)
                    files_removed += 1
                    total_size += size

        logger.info('Removed %d references (%s in total)', files_removed, filesizeformat(total_size))
