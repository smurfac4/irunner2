# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.utils.encoding import force_str

from mptt.models import MPTTModel, TreeForeignKey

from cauth.acl.models import BaseAccess
from common.locales.fields import LanguageField
from common.ir18n.fields import IR18nCharField
from proglangs.models import Compiler
from storage.models import FileMetadataBase
from storage.resource_id import ResourceIdField
from users.models import AdminGroup

DEFAULT_TIME_LIMIT = 1000  # 1 s
DEFAULT_MEMORY_LIMIT = 1 * 1024 * 1024 * 1024  # 1 GB


class ProblemFolder(MPTTModel):
    name = models.CharField(_('name'), max_length=64)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', db_index=True)

    def __str__(self):
        return self.name


class Problem(models.Model):
    number = models.IntegerField(_('number'), blank=True, null=True, default=None)
    subnumber = models.IntegerField(_('subnumber'), blank=True, null=True, default=None)
    full_name = IR18nCharField(_('full name'), max_length=200, blank=True)
    short_name = IR18nCharField(_('short name'), max_length=32, blank=True)
    difficulty = models.IntegerField(_('difficulty'), blank=True, null=True, default=None)

    input_filename = models.CharField(_('input file name'), max_length=32, blank=True)
    output_filename = models.CharField(_('output file name'), max_length=32, blank=True)

    folders = models.ManyToManyField(ProblemFolder, verbose_name=_('folders'))

    class Meta:
        ordering = ['number', 'subnumber', 'full_name']

    def get_extra(self):
        try:
            return self.extra
        except ObjectDoesNotExist:
            return None

    def get_default_time_limit(self):
        extra = self.get_extra()
        return extra.default_time_limit if extra is not None else DEFAULT_TIME_LIMIT

    def get_default_memory_limit(self):
        extra = self.get_extra()
        return extra.default_memory_limit if extra is not None else DEFAULT_MEMORY_LIMIT

    def get_formatted_number(self):
        if self.number is None:
            return ''
        if self.subnumber is None:
            return '{0}'.format(self.number)
        else:
            return '{0}.{1}'.format(self.number, self.subnumber)

    def _numbered_name(self, name):
        if self.number is not None:
            if name:
                return '{0}. {1}'.format(self.get_formatted_number(), name)
            else:
                return self.get_formatted_number()
        else:
            return force_str(name)

    def numbered_full_name(self):
        return self._numbered_name(self.full_name)

    def numbered_full_name_for_lang(self, lng):
        return self._numbered_name(self.full_name.localize(lng) if lng else self.full_name)

    def numbered_full_name_difficulty(self):
        result = self.numbered_full_name()
        if self.difficulty is not None:
            return '[{0}] {1}'.format(self.difficulty, result)
        else:
            return result

    def numbered_short_name(self):
        return self._numbered_name(self.short_name)

    # for contests
    def unnumbered_brief_name(self):
        if self.short_name:
            return force_str(self.short_name)
        elif self.full_name:
            return force_str(self.full_name)
        else:
            return self.numbered_full_name()

    @staticmethod
    def _is_non_empty(i18n_str):
        for value in i18n_str.values():
            if not value or not value.strip():
                return False
        return True

    def clean(self):
        has_name = Problem._is_non_empty(self.full_name) or Problem._is_non_empty(self.short_name)
        if self.number is None and not has_name:
            raise ValidationError(_('A problem must have a number or a non-empty name.'))


class ProblemExtraInfo(models.Model):
    problem = models.OneToOneField(Problem, null=False, on_delete=models.CASCADE, primary_key=True, related_name='extra')
    description = models.TextField(_('description'), blank=True)  # public
    hint = models.TextField(_('hint'), blank=True)  # private
    default_time_limit = models.IntegerField(default=DEFAULT_TIME_LIMIT)
    default_memory_limit = models.IntegerField(default=DEFAULT_MEMORY_LIMIT)
    sample_test_count = models.IntegerField(_('number of sample tests'), default=0)
    allowed_programming_languages = models.CharField(_('allowed programming languages'), max_length=255, null=False, blank=True)
    check_plagiarism = models.BooleanField(_('Check plagiarism'), default=True, blank=True)


class ProblemRelatedFile(FileMetadataBase):
    STATEMENT_TEX_TEX2HTML = 211
    STATEMENT_HTML = 212
    ADDITIONAL_STATEMENT_FILE = 213
    SOLUTION_DESCRIPTION = 214
    SAMPLE_INPUT_FILE = 220
    SAMPLE_OUTPUT_FILE = 221
    USER_FILE = 222
    STATEMENT_TEX_PYLIGHTEX = 224
    TUTORIAL_TEX_PYLIGHTEX = 225

    FILE_TYPE_CHOICES = (
        (STATEMENT_TEX_TEX2HTML, _('TeX statement (TeXtoHTML)')),
        (STATEMENT_TEX_PYLIGHTEX, _('TeX statement (pylightex)')),
        (STATEMENT_HTML, _('HTML statement')),
        (ADDITIONAL_STATEMENT_FILE, _('Additional statement file')),
        (TUTORIAL_TEX_PYLIGHTEX, _('Problem tutorial (pylightex)')),
        (SOLUTION_DESCRIPTION, _('Solution description')),
        (SAMPLE_INPUT_FILE, _('Sample input file')),
        (SAMPLE_OUTPUT_FILE, _('Sample output file')),
        (USER_FILE, _('User file')),
    )

    TEST_CASE_IMAGE_FILE_TYPES = (
        ADDITIONAL_STATEMENT_FILE,
        SAMPLE_INPUT_FILE,
        SAMPLE_OUTPUT_FILE,
        USER_FILE,
    )
    TEX_FILE_TYPES = (
        STATEMENT_TEX_TEX2HTML,
        STATEMENT_TEX_PYLIGHTEX,
        TUTORIAL_TEX_PYLIGHTEX,
    )

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    file_type = models.IntegerField(_('file type'), choices=FILE_TYPE_CHOICES)
    description = models.TextField(_('description'), blank=True)
    language = LanguageField(_('language'), blank=True)

    class Meta:
        unique_together = ('problem', 'filename')


class ProblemRelatedSourceFile(FileMetadataBase):
    # These magic constants come from the iRunner 1 (see localization/resources.xml)
    AUTHORS_SOLUTION = 215
    CHECKER = 216
    CONTESTANT_SOLUTION = 217
    GENERATOR = 218
    LIBRARY = 219
    VALIDATOR = 223
    SCORER = 224

    FILE_TYPE_CHOICES = (
        (AUTHORS_SOLUTION, _('Author\'s solution')),
        (CHECKER, _('Checker')),
        (CONTESTANT_SOLUTION, _('Contestant solution')),
        (GENERATOR, _('Generator')),
        (LIBRARY, _('Library')),
        (VALIDATOR, _('Validator')),
        (SCORER, _('Scorer')),
    )

    # null for global checkers
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, null=True)
    file_type = models.IntegerField(_('file type'), choices=FILE_TYPE_CHOICES)
    description = models.TextField(_('description'), blank=True)
    compiler = models.ForeignKey(Compiler, on_delete=models.PROTECT, verbose_name=_('compiler'))

    class Meta:
        unique_together = ('problem', 'filename')


class TestCase(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    ordinal_number = models.PositiveIntegerField(_('number'), default=0)
    description = models.TextField(_('description'), blank=True)

    input_resource_id = ResourceIdField()
    input_size = models.IntegerField(default=0)

    answer_resource_id = ResourceIdField()
    answer_size = models.IntegerField(default=0)

    time_limit = models.IntegerField()
    memory_limit = models.IntegerField(default=0)
    points = models.IntegerField(default=1)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    creation_time = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('problem', 'ordinal_number')

    def set_input(self, storage, f):
        resource_id = storage.save(f)
        updated = (self.input_resource_id != resource_id)
        self.input_resource_id = resource_id
        self.input_size = f.size
        return updated

    def set_answer(self, storage, f):
        resource_id = storage.save(f)
        updated = (self.answer_resource_id != resource_id)
        self.answer_resource_id = resource_id
        self.answer_size = f.size
        return updated


class Validation(models.Model):
    problem = models.OneToOneField(Problem, on_delete=models.CASCADE)
    is_pending = models.BooleanField(default=False)
    validator = models.ForeignKey(ProblemRelatedSourceFile, null=True, blank=True, on_delete=models.SET_NULL)
    general_failure_reason = models.CharField(max_length=64, blank=True)


class TestCaseValidation(models.Model):
    validation = models.ForeignKey(Validation, on_delete=models.CASCADE)
    input_resource_id = ResourceIdField()
    is_valid = models.BooleanField()
    validator_message = models.CharField(max_length=255, blank=True)


class ProblemAccess(BaseAccess):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')

    class Meta:
        unique_together = ('problem', 'user')


class ProblemFolderAccess(BaseAccess):
    folder = models.ForeignKey(ProblemFolder, on_delete=models.CASCADE)
    group = models.ForeignKey(AdminGroup, on_delete=models.CASCADE, related_name='+')

    class Meta:
        unique_together = ('folder', 'group')
