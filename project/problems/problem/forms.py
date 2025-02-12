from __future__ import unicode_literals

import zipfile

from django import forms
from django.core.files.base import ContentFile
from django.utils.translation import ugettext_lazy as _

from cauth.acl.accessmode import AccessMode
from common.constants import EMPTY_SELECT
from common.tree.mptt_fields import OrderedTreeNodeMultipleChoiceField
from users.fields import UsernameField
from proglangs.fields import ProgrammingLanguagesField

from problems.problem.importing import extract_tests
from problems.problem.fields import TimeLimitField, MemoryLimitField
from problems.models import (
    Problem,
    ProblemExtraInfo,
    ProblemFolder,
    ProblemRelatedFile,
    ProblemRelatedSourceFile,
    TestCase,
)

'''
Edit single problem
'''


class ProblemNameForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = ['number', 'subnumber', 'full_name', 'short_name']


class ProblemForm(forms.ModelForm):
    class Meta:
        model = Problem
        fields = ['difficulty', 'input_filename', 'output_filename']
        help_texts = {
            'difficulty': _('Difficulty level on the ten-point scale (for courses).'),
            'input_filename': _('Leave empty to use standard input.'),
            'output_filename': _('Leave empty to use standard output.'),
        }

    def __init__(self, *args, **kwargs):
        super(ProblemForm, self).__init__(*args, **kwargs)
        self.fields['input_filename'].widget.attrs['class'] = 'ir-monospace'
        self.fields['output_filename'].widget.attrs['class'] = 'ir-monospace'


class ProblemFoldersForm(forms.ModelForm):
    folders = OrderedTreeNodeMultipleChoiceField(
        widget=forms.SelectMultiple(attrs={'size': 20}),
        label=_('Problem folders'),
        queryset=None,
        required=False)

    class Meta:
        model = Problem
        fields = ['folders']

    def __init__(self, *args, **kwargs):
        super(ProblemFoldersForm, self).__init__(*args, **kwargs)
        self.fields['folders'].queryset = ProblemFolder.objects.all()


class ProblemExtraInfoForm(forms.ModelForm):
    default_time_limit = TimeLimitField(label=_('Time limit'), required=True)
    default_memory_limit = MemoryLimitField(label=_('Memory limit'), required=False)
    allowed_programming_languages = ProgrammingLanguagesField(label=_('Allowed programming languages'), required=False)

    class Meta:
        model = ProblemExtraInfo
        fields = ['sample_test_count', 'default_time_limit', 'default_memory_limit',
                  'description', 'allowed_programming_languages', 'check_plagiarism', 'run_twice']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'sample_test_count': _('The number of the first test cases with full feedback available.'),
            'run_twice': _('Enables the special judging format. '
                           'Solutions will be invoked twice for each test: output of the solution or the interactor '
                           'will be forwarded to the input on the second invocation. '
                           'Probably, the problem should be interactive.'),
        }


class TestDescriptionForm(forms.ModelForm):
    time_limit = TimeLimitField(label=_('Time limit'), required=True)
    memory_limit = MemoryLimitField(label=_('Memory limit'), required=False)

    class Meta:
        model = TestCase
        fields = ['description', 'points', 'time_limit', 'memory_limit']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class TestUploadOrTextForm(forms.Form):
    upload = forms.FileField(required=False, widget=forms.FileInput)
    text = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'ir-monospace'}))

    def extract_file_result(self):
        '''
        Always returns not None.
        '''
        upload = self.cleaned_data['upload']
        if upload is None:
            text = self.cleaned_data['text']
            if text is not None:
                if len(text) > 0:
                    # Normalize text to use windows newlines.
                    # Trailing newline is added. Empty file is left empty.
                    lines = text.splitlines()
                    newline = '\r\n'
                    text = newline.join(lines) + newline

                upload = ContentFile(text.encode('utf-8'))
        return upload


class TestUploadForm(forms.Form):
    upload = forms.FileField(required=False, widget=forms.FileInput)

    def __init__(self, *args, **kwargs):
        representation = kwargs.pop('representation')
        super(TestUploadForm, self).__init__(*args, **kwargs)
        self.representation = representation

    def extract_file_result(self):
        upload = self.cleaned_data['upload']
        return upload


class MassSetTimeLimitForm(forms.Form):
    time_limit = TimeLimitField(label=_('Time limit'), required=True)


class MassSetMemoryLimitForm(forms.Form):
    memory_limit = MemoryLimitField(label=_('Memory limit'), required=False)


class MassSetPointsForm(forms.Form):
    points = forms.IntegerField(label=_('Points'), required=True, min_value=0, initial=1)


class ValidateUniqueFilenameMixin(object):
    def clean(self):
        cleaned_data = super(ValidateUniqueFilenameMixin, self).clean()
        filename = cleaned_data.get('filename')

        if (self.instance is not None) and (self.instance.problem_id is not None) and (filename is not None):
            model_class = self.instance._meta.model

            queryset = model_class.objects.filter(problem_id=self.instance.problem_id, filename=filename)
            if self.instance.pk is not None:
                # object has been already saved
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                msg = _('A file with this name already exists.')
                self.add_error('filename', msg)
        return cleaned_data


class ProblemRelatedDataFileForm(ValidateUniqueFilenameMixin, forms.ModelForm):
    upload = forms.FileField(label=_('File'), required=False, widget=forms.FileInput)

    class Meta:
        model = ProblemRelatedFile
        fields = ['upload', 'filename', 'file_type', 'language', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super(ProblemRelatedDataFileForm, self).__init__(*args, **kwargs)
        self.fields['file_type'].choices = [('', EMPTY_SELECT)] + list(self.fields['file_type'].choices)[1:]


class ProblemRelatedDataFileNewForm(ProblemRelatedDataFileForm):
    '''
    When adding new file, uploading data is required.
    '''
    upload = forms.FileField(label=_('File'), required=True, widget=forms.FileInput)


class ProblemRelatedSourceFileForm(ValidateUniqueFilenameMixin, forms.ModelForm):
    upload = forms.FileField(label=_('File'), required=False, widget=forms.FileInput)

    class Meta:
        model = ProblemRelatedSourceFile
        fields = ['upload', 'filename', 'file_type', 'compiler', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super(ProblemRelatedSourceFileForm, self).__init__(*args, **kwargs)
        self.fields['file_type'].choices = [('', EMPTY_SELECT)] + list(self.fields['file_type'].choices)[1:]
        self.fields['compiler'].choices = [('', EMPTY_SELECT)] + list(self.fields['compiler'].choices)[1:]


class ProblemRelatedSourceFileNewForm(ProblemRelatedSourceFileForm):
    '''
    When adding new file, uploading data is required.
    '''
    upload = forms.FileField(label=_('File'), required=True, widget=forms.FileInput)


class ProblemTestArchiveUploadForm(forms.Form):
    ARCHIVE_SCHEME_CHOICES = (
        ('/a', 'X / X.a'),
        ('in/out', 'X.in / X.out'),
        ('i/o', 'X.i / X.o'),
    )

    upload = forms.FileField(label=_('ZIP-archive'), required=True, widget=forms.FileInput,
                             help_text=_('The archive should not contain any other files except test inputs and outputs.'))
    scheme = forms.ChoiceField(label=_('File naming scheme'), required=True, choices=ARCHIVE_SCHEME_CHOICES)

    def clean(self):
        cleaned_data = super(ProblemTestArchiveUploadForm, self).clean()
        upload = cleaned_data.get('upload')
        scheme = cleaned_data.get('scheme')

        if upload is not None and scheme is not None:
            filenames = []
            try:
                with zipfile.ZipFile(upload, 'r', allowZip64=True) as myzip:
                    # Consider only root directory. Zip always uses forward slashes.
                    filenames = [filename for filename in myzip.namelist() if '/' not in filename]
            except zipfile.BadZipfile:
                self.add_error('upload', _('Archive format is not supported.'))
                return

            if scheme == '/a':
                tests = extract_tests(filenames, None, 'a')
            elif scheme == 'in/out':
                tests = extract_tests(filenames, 'in', 'out')
            elif scheme == 'i/o':
                tests = extract_tests(filenames, 'i', 'o')
            else:
                tests = []

            if len(tests) == 0:
                raise forms.ValidationError(_('No test files found in the archive.'), code='empty')

            cleaned_data['tests'] = tests


'''
TeX
'''


class ProblemRelatedTeXFileForm(ValidateUniqueFilenameMixin, forms.ModelForm):
    class Meta:
        model = ProblemRelatedFile
        fields = ['filename', 'language']


'''
Validator
'''


class ValidatorForm(forms.Form):
    validator = forms.ModelChoiceField(label=_('Validator'), queryset=ProblemRelatedSourceFile.objects.none(), empty_label=EMPTY_SELECT, required=False)

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop('validators')
        super(ValidatorForm, self).__init__(*args, **kwargs)
        self.fields['validator'].queryset = qs


'''
Challenge
'''


class ChallengeForm(forms.Form):
    time_limit = TimeLimitField(label=_('Time limit'), required=True)
    memory_limit = MemoryLimitField(label=_('Memory limit'), required=False)
