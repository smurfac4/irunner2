import re
import six

from rest_framework import serializers

from common.outcome import Outcome
from solutions.models import (
    Judgement,
    JudgementLog,
    TestCaseResult,
)
from storage.resource_id import ResourceId
from plagiarism.plagiarismstructs import (
    PlagiarismSubJob,
    PlagiarismTestingJob,
)
from api.workerstructs import (
    WorkerGreeting,
    WorkerState,
    WorkerTestingReport,
)


def parse_resource_id(string):
    try:
        return ResourceId.parse(string)
    except (ValueError, TypeError) as e:
        raise serializers.ValidationError('Unable to parse resource id: {0}'.format(e))


def _enum_from_string(cls, data):
    if not isinstance(data, six.string_types):
        msg = 'Incorrect type. Expected a string, but got {0}'
        raise serializers.ValidationError(msg.format(type(data).__name__))

    if len(data) == 0:
        raise serializers.ValidationError('String is empty.')

    if not re.match(r'^[A-Z]+(_[A-Z]+)*$', data):
        raise serializers.ValidationError('Incorrect format. Expected capitalized Latin string with possible inner underscores.')

    if not hasattr(cls, data):
        raise serializers.ValidationError('Unknown value of {0} enumeration: `{1}`'.format(cls.__name__, data))

    return getattr(cls, data)


class ResourceIdField(serializers.Field):
    def to_internal_value(self, data):
        return parse_resource_id(data)

    def to_representation(self, obj):
        return str(obj)


class OutcomeField(serializers.Field):
    def to_internal_value(self, data):
        return _enum_from_string(Outcome, data)


class StatusField(serializers.Field):
    def to_internal_value(self, data):
        return _enum_from_string(Judgement, data)


class LogKindField(serializers.Field):
    def to_internal_value(self, data):
        return _enum_from_string(JudgementLog, data)


class SolutionSerializer(serializers.Serializer):
    compiler = serializers.CharField(read_only=True, source='compiler.handle')
    resource_id = ResourceIdField(read_only=True, source='source_code.resource_id')
    filename = serializers.CharField(read_only=True, source='source_code.filename')


class ProblemRelatedSourceFileSerializer(serializers.Serializer):
    compiler = serializers.CharField(read_only=True, source='compiler.handle')
    resource_id = ResourceIdField(read_only=True)
    filename = serializers.CharField(read_only=True)


class WorkerFileSerializer(serializers.Serializer):
    resource_id = ResourceIdField(read_only=True)


class WorkerTestCaseSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    input = WorkerFileSerializer()
    answer = WorkerFileSerializer()
    time_limit = serializers.IntegerField(read_only=True)
    memory_limit = serializers.IntegerField(read_only=True)
    max_score = serializers.IntegerField(read_only=True)
    is_sample = serializers.BooleanField()


class WorkerCheckerSerializer(serializers.Serializer):
    source = ProblemRelatedSourceFileSerializer()
    kind = serializers.CharField()


class WorkerLibrarySerializer(serializers.Serializer):
    source = ProblemRelatedSourceFileSerializer()


class WorkerValidatorSerializer(serializers.Serializer):
    source = ProblemRelatedSourceFileSerializer()


class WorkerScorerSerializer(serializers.Serializer):
    source = ProblemRelatedSourceFileSerializer()


class WorkerInteractorSerializer(serializers.Serializer):
    source = ProblemRelatedSourceFileSerializer()


class WorkerProblemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    input_file_name = serializers.CharField()
    output_file_name = serializers.CharField()
    tests = WorkerTestCaseSerializer(many=True)
    checker = WorkerCheckerSerializer()
    libraries = WorkerLibrarySerializer(many=True)
    validator = WorkerValidatorSerializer()
    scorer = WorkerScorerSerializer()
    interactor = WorkerInteractorSerializer()
    default_time_limit = serializers.IntegerField()
    run_twice = serializers.BooleanField()


class WorkerTestingJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    problem = WorkerProblemSerializer()
    solution = SolutionSerializer()
    stop_after_first_failed_test = serializers.BooleanField()


class TestCaseResultSerializer(serializers.Serializer):
    outcome = OutcomeField()
    id = serializers.IntegerField(allow_null=True, default=None, source='test_case_id')
    exit_code = serializers.IntegerField(default=0)
    time_limit = serializers.IntegerField(min_value=0, default=0)
    time_used = serializers.IntegerField(min_value=0, default=0)
    memory_limit = serializers.IntegerField(min_value=0, default=0)
    memory_used = serializers.IntegerField(min_value=0, default=0)
    score = serializers.IntegerField(min_value=0, default=None)
    max_score = serializers.IntegerField(min_value=0, default=1)
    checker_message = serializers.CharField(allow_blank=True, default='')
    input_resource_id = ResourceIdField(default=None, allow_null=True)
    output_resource_id = ResourceIdField(default=None, allow_null=True)
    answer_resource_id = ResourceIdField(default=None, allow_null=True)
    stdout_resource_id = ResourceIdField(default=None, allow_null=True)
    stderr_resource_id = ResourceIdField(default=None, allow_null=True)
    is_sample = serializers.BooleanField(default=False)

    def create(self, validated_data):
        return TestCaseResult(**validated_data)


class JudgementLogSerializer(serializers.Serializer):
    kind = LogKindField()
    resource_id = ResourceIdField()

    def create(self, validated_data):
        return JudgementLog(**validated_data)


class TestCaseResultField(serializers.Field):
    def to_internal_value(self, data):
        serializer = TestCaseResultSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()


class JudgementLogField(serializers.Field):
    def to_internal_value(self, data):
        serializer = JudgementLogSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()


class WorkerTestingReportSerializer(serializers.Serializer):
    outcome = OutcomeField()
    first_failed_test = serializers.IntegerField(min_value=0, required=False, default=None)
    score = serializers.IntegerField(min_value=0, required=False, default=None)
    max_score = serializers.IntegerField(min_value=0, required=False, default=None)
    tests = serializers.ListField(child=TestCaseResultField())
    logs = serializers.ListField(child=JudgementLogField(), required=False, default=[])
    general_failure_reason = serializers.CharField(allow_null=True, allow_blank=True, default='')
    general_failure_message = serializers.CharField(allow_null=True, allow_blank=True, default='')
    sample_tests_passed = serializers.BooleanField(required=False, default=True)

    def create(self, validated_data):
        return WorkerTestingReport(**validated_data)


class WorkerStateSerializer(serializers.Serializer):
    status = StatusField()
    test_number = serializers.IntegerField(min_value=0, default=0)

    def create(self, validated_data):
        return WorkerState(**validated_data)


class WorkerGreetingSerializer(serializers.Serializer):
    name = serializers.CharField()
    tag = serializers.CharField(required=False, allow_blank=True, default='')

    def create(self, validated_data):
        return WorkerGreeting(**validated_data)

#
# Plagiarism serializers
#


class PlagiarismJobFieldSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    language = serializers.CharField(read_only=True)
    resource_id = ResourceIdField(read_only=True)

    def create(self, validated_data):
        return PlagiarismSubJob(**validated_data)


class PlagiarismJobField(serializers.Field):
    def to_internal_value(self, data):
        serializer = PlagiarismJobFieldSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def to_representation(self, obj):
        return {"id": obj.id, "language": obj.language, "resourceId": obj.resource_id}


class PlagiarismJobSerializer(serializers.Serializer):
    solution = PlagiarismJobFieldSerializer(read_only=True)
    solutions = serializers.ListField(child=PlagiarismJobField())

    def create(self, validated_data):
        return PlagiarismTestingJob(**validated_data)
