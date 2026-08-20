import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from solutions.models import (
    Judgement,
    TestCaseResult,
    Outcome,
)


def _authorized(request):
    token = request.headers.get('Worker-Token', '')
    expected = getattr(settings, 'WORKER_TOKEN', 'abacaba')
    return token == expected


def _outcome(name):
    aliases = {
        'ACCEPTED': [
            'ACCEPTED',
        ],
        'WRONG_ANSWER': [
            'WRONG_ANSWER',
        ],
        'RUNTIME_ERROR': [
            'RUNTIME_ERROR',
            'RUNTIME_FAILURE',
        ],
        'TIME_LIMIT_EXCEEDED': [
            'TIME_LIMIT_EXCEEDED',
            'TIME_LIMIT',
        ],
        'INTERNAL_ERROR': [
            'CHECK_FAILED',
            'INTERNAL_ERROR',
        ],
    }

    for attr in aliases[name]:
        if hasattr(Outcome, attr):
            return getattr(Outcome, attr)

    raise RuntimeError(
        'Unable to find Outcome constant for {}'.format(name)
    )


@csrf_exempt
def take_job(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    if not _authorized(request):
        return HttpResponse(status=403)

    with transaction.atomic():
        judgement = (
            Judgement.objects
            .select_for_update()
            .select_related(
                'solution',
                'solution__problem',
                'solution__source_code',
                'solution__compiler',
            )
            .filter(status=Judgement.WAITING)
            .order_by('id')
            .first()
        )

        if judgement is None:
            return HttpResponse(status=204)

        judgement.status = Judgement.PREPARING
        judgement.save(update_fields=['status'])

        try:
            extra = judgement.extra_info
            extra.start_testing_time = timezone.now()
            extra.save(update_fields=['start_testing_time'])
        except Exception:
            pass

        solution = judgement.solution
        problem = solution.problem

        tests = []

        for test in problem.testcase_set.all().order_by(
            'ordinal_number',
            'id',
        ):
            tests.append({
                'id': test.id,
                'number': test.ordinal_number,
                'input_resource_id': str(test.input_resource_id),
                'answer_resource_id': str(test.answer_resource_id),
                'time_limit': test.time_limit,
                'memory_limit': test.memory_limit,
                'points': test.points,
            })

        compiler = getattr(solution.compiler, 'handle', None)

        if compiler is None:
            compiler = str(solution.compiler)

        data = {
            'judgement_id': judgement.id,

            'solution': {
                'resource_id': str(
                    solution.source_code.resource_id
                ),
                'filename': solution.source_code.filename,
                'compiler': compiler,
            },

            'tests': tests,
        }

    return JsonResponse(data)


@csrf_exempt
def put_result(request, judgement_id):
    if request.method != 'POST':
        return HttpResponse(status=405)

    if not _authorized(request):
        return HttpResponse(status=403)

    try:
        payload = json.loads(
            request.body.decode('utf-8')
        )
    except Exception:
        return JsonResponse(
            {'error': 'invalid json'},
            status=400,
        )

    try:
        final_outcome = _outcome(payload['outcome'])
    except Exception as exc:
        return JsonResponse(
            {'error': str(exc)},
            status=400,
        )

    with transaction.atomic():
        judgement = (
            Judgement.objects
            .select_for_update()
            .select_related('solution__problem')
            .get(pk=judgement_id)
        )

        TestCaseResult.objects.filter(
            judgement=judgement
        ).delete()

        total_score = 0
        max_score = 0

        results = payload.get('tests', [])

        for index, item in enumerate(results, start=1):
            test_id = item.get('test_id')

            test = (
                judgement.solution.problem
                .testcase_set
                .filter(pk=test_id)
                .first()
            )

            if test is None:
                continue

            try:
                test_outcome = _outcome(
                    item['outcome']
                )
            except Exception:
                test_outcome = _outcome(
                    'INTERNAL_ERROR'
                )

            score = int(item.get('score', 0))
            points = int(test.points)

            total_score += score
            max_score += points

            TestCaseResult.objects.create(
                judgement=judgement,
                test_case=test,

                input_resource_id=
                    test.input_resource_id,

                answer_resource_id=
                    test.answer_resource_id,

                exit_code=int(
                    item.get('exit_code', 0)
                ),

                time_limit=int(
                    test.time_limit
                ),

                time_used=int(
                    item.get('time_used', 0)
                ),

                memory_limit=int(
                    test.memory_limit
                ),

                memory_used=int(
                    item.get('memory_used', 0)
                ),

                score=score,
                max_score=points,

                checker_message=item.get(
                    'message',
                    '',
                )[:255],

                outcome=test_outcome,
                is_sample=False,
            )

        judgement.status = Judgement.DONE
        judgement.outcome = final_outcome
        judgement.score = total_score
        judgement.max_score = max_score
        judgement.test_number = len(results)
        judgement.sample_tests_passed = (
            payload['outcome'] == 'ACCEPTED'
        )

        judgement.save()
        solution = judgement.solution
        solution.best_judgement = judgement
        solution.save(update_fields=['best_judgement'])
        try:
            extra = judgement.extra_info
            extra.finish_testing_time = timezone.now()
            extra.save(
                update_fields=[
                    'finish_testing_time'
                ]
            )
        except Exception:
            pass

    return JsonResponse({'ok': True})