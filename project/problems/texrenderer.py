# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import namedtuple

from django.utils.encoding import force_text
from django.utils.html import escape
from django.utils.translation import pgettext_lazy
from common.constants import STDIN, STDOUT
from common.pylightex import tex2html as pylightex_tex2html

# for strings passed to external library
TEX2HTML_ENCODING = 'utf-8'

IMAGE_PATH = '/fIpZ6d9gT5GYgPFox3cO/'

SUBSTITUTIONS = [
    ('<h2>Формат входного файла</h2>', pgettext_lazy('section', 'Input'), '<h2>{}</h2>'),
    ('<h2>Формат выходного файла</h2>', pgettext_lazy('section', 'Output'), '<h2>{}</h2>'),
    ('<h2>Пример</h2>', pgettext_lazy('section', 'Example'), '<h2>{}</h2>'),
    ('<h2>Примеры</h2>', pgettext_lazy('section', 'Examples'), '<h2>{}</h2>'),
    ('<h2><i>Замечание</i></h2>', pgettext_lazy('section', 'Note'), '<h2><i>{}</i></h2>'),
]

PYLIGHTEX_SECTIONS = {
    'InputFile': pgettext_lazy('section', 'Input'),
    'OutputFile': pgettext_lazy('section', 'Output'),
    'Example': pgettext_lazy('section', 'Example'),
    'Examples': pgettext_lazy('section', 'Examples'),
    'Note': pgettext_lazy('section', 'Note'),
    'Notes': pgettext_lazy('section', 'Notes'),
    'Scoring': pgettext_lazy('section', 'Scoring'),
}

'''
output contains HTML data
'''
TeXRenderResult = namedtuple('TeXRenderResult', 'output log')


def _render(begin, tex_source, end):
    src = begin + tex_source + end
    try:
        import tex2html
        src = src.encode(TEX2HTML_ENCODING)
        dst, log = tex2html.convert(src)
        dst, log = dst.decode(TEX2HTML_ENCODING, errors='replace'), log.decode(TEX2HTML_ENCODING, errors='replace')
    except ImportError as e:
        dst, log = ('<pre>' + escape(src) + '</pre>'), force_text(e)

    dst = dst.replace(IMAGE_PATH, '')

    for src_phrase, translated_text, template in SUBSTITUTIONS:
        dst_phrase = template.format(translated_text)
        dst = dst.replace(src_phrase, dst_phrase)

    return TeXRenderResult(dst, log)


def _render_tex_tex2html(tex_source, input_filename, output_filename):
    begin = '\\begin{rawproblem}{%s}{%s}\n' % (
        input_filename or STDIN,
        output_filename or STDOUT,
    )
    end = '\n\\end{rawproblem}\n'
    return _render(begin, tex_source, end)


def _render_tex_pylightex(tex_source, input_filename, output_filename):
    return TeXRenderResult(pylightex_tex2html(
        tex_source, inline=False,
        olymp_file_names={
            'input': input_filename or STDIN,
            'output': output_filename or STDOUT,
        },
        olymp_section_names=PYLIGHTEX_SECTIONS
    ), '')


def render_tex(tex_source, input_filename=None, output_filename=None, renderer='tex2html'):
    if renderer == 'tex2html':
        return _render_tex_tex2html(tex_source, input_filename, output_filename)
    if renderer == 'pylightex':
        return _render_tex_pylightex(tex_source, input_filename, output_filename)
    return TeXRenderResult('', 'Unknown renderer: <{}>'.format(renderer))
