# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms
from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.views import generic
from django.views.decorators.csrf import csrf_exempt

from cauth.mixins import StaffMemberRequiredMixin
from common.pylightex import tex2html
from contests.homeblock import ContestBlockFactory
from courses.homeblock import CourseBlockFactory
from news.homeblock import NewsBlockFactory

from home.texmarkup import TEX_EXAMPLES
from home.texmarkup import highlight_tex
from home.registry import HomePageBlockStyle

HOME_PAGE_BLOCK_FACTORIES = [
    CourseBlockFactory(),
    ContestBlockFactory(),
    NewsBlockFactory(),
]


def home(request):
    blocks = []
    for factory in HOME_PAGE_BLOCK_FACTORIES:
        blocks.extend(factory.create_blocks(request))

    context = {
        'common_blocks': [block for block in blocks if block.style == HomePageBlockStyle.COMMON],
        'my_blocks': [block for block in blocks if block.style == HomePageBlockStyle.MY],
    }
    return render(request, 'home/home.html', context)


def about(request):
    return render(request, 'home/about.html', {})


def cookie_policy(request):
    return render(request, 'home/cookie_policy.html', {})


@csrf_exempt
def accept_cookie_policy(request):
    request.session['accept_cookies'] = True
    return HttpResponse('OK')


def language(request):
    next = request.GET.get('next')
    return render(request, 'home/language.html', {'redirect_to': next})


def error403(request, exception):
    context = {
        'code': '403',
        'title': 'Forbidden',
        'explanation': "You don't have permission to access the requested resource.",
    }
    return render(request, 'home/error.html', context, status=403)


def error404(request, exception):
    context = {
        'code': '404',
        'title': 'Not Found',
        'explanation': "The requested resource was not found on this server.",
    }
    return render(request, 'home/error.html', context, status=404)


def tex_markup(request):
    sections = []
    for section in TEX_EXAMPLES:
        name = section[0]
        examples = []
        for example in section[1:]:
            examples.append((
                mark_safe(highlight_tex(example)),
                mark_safe(tex2html(example))
            ))
        sections.append((name, examples))

    return render(request, 'home/texmarkup.html', {'sections': sections})


class TestEmailForm(forms.Form):
    email = forms.EmailField(label='Email', required=True)
    subject = forms.CharField(label=_('Subject'), required=False)
    body = forms.CharField(
        label=_('Message'),
        required=False,
        widget=forms.Textarea(),
        max_length=2**16
    )


class TestSendingEmailsView(StaffMemberRequiredMixin, generic.FormView):
    template_name = 'home/test_sending_emails.html'
    form_class = TestEmailForm

    def form_valid(self, form):
        sent = False
        try:
            send_mail(
                subject=form.cleaned_data['subject'],
                message=form.cleaned_data['body'],
                from_email=None,
                recipient_list=[form.cleaned_data['email']],
            )
            sent = True
        except Exception as e:
            return render(self.request, self.template_name, {'form': form, 'exception': e, 'exception_type': type(e).__name__})
        if sent:
            messages.success(self.request, 'OK')
        return redirect('test_sending_emails')
