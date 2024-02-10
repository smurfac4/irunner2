# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import mark_safe
from django.views.decorators.csrf import csrf_exempt

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
