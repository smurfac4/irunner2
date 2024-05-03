# -*- coding: utf-8 -*-

from __future__ import unicode_literals
import itertools
from .highlight import get_highlight_func, html_escape
from lark import Lark, Transformer, v_args, UnexpectedInput

TEX_GRAMMAR = r'''
// General
_COMMENT: "%" /[^\n]/* "\n"?
_PARAGRAPH_BREAKER: /\n{2,}/
NEWLINE: /\n/
_WHITESPACE: /\s+/

// Plain text
!usual_symbol: /[^\\%${}~\n\-<>&]+/
!special_symbol: "~" | "<" | "<<" | ">" | ">>" | "-" | "--" | "---" | "{}"
!escaped_symbol: "\\" /[\\%${}&_#,\\ ]/
!noarg_command: /\\(textbackslash|dots|ldots|quad) */
_plain_text: usual_symbol | special_symbol | escaped_symbol | noarg_command | NEWLINE

// Math
MATH_SPECIAL: "\\$" | "\\\\"
math_symbol: /[^$]/ | MATH_SPECIAL
equation: math_symbol+
inline_math: "$" equation "$"
display_math: "$$" equation "$$"

// Verbatim
VERBATIM_CHAR: /./s
!inline_verbatim_block: (/[^{}]+/ | ("{" inline_verbatim_block? "}")) inline_verbatim_block?
verbatim_content: VERBATIM_CHAR*
verb_cmd: ("\\verb{" inline_verbatim_block "}") | ("\\verb|" /[^|]+/ "|") | ("\\verb!" /[^!]+/ "!")
path_cmd: "\\path{" inline_verbatim_block "}"
url_cmd: "\\url{" inline_verbatim_block "}"
href_cmd: "\\href{" inline_verbatim_block "}" "{" phrase "}"
mintinline_cmd: "\\mintinline{" CNAME "}{" inline_verbatim_block "}"
verbatim_env: "\\begin{verbatim}" verbatim_content "\\end{verbatim}"
minted_env: "\\begin{minted}{" CNAME "}" verbatim_content "\\end{minted}"

// Center
center_env: "\\begin{center}" paragraphs "\\end{center}"

// Lists
_ITEM: /\\item\s*/
_BEGIN_ITEMIZE: /\\begin{itemize}\s*/
_END_ITEMIZE: /\\end{itemize}/
_BEGIN_ENUMERATE: /\\begin{enumerate}\s*/
_END_ENUMERATE: /\\end{enumerate}/
item: _ITEM paragraphs
itemize_env: _BEGIN_ITEMIZE item* _END_ITEMIZE
enumerate_env: _BEGIN_ENUMERATE item* _END_ENUMERATE

// Style
texttt_cmd: "\\texttt{" phrase "}"
textit_cmd: "\\textit{" phrase "}"
textbf_cmd: "\\textbf{" phrase "}"
emph_cmd: "\\emph{" phrase "}"
underline_cmd: "\\underline{" phrase "}"
_text_style_cmd: texttt_cmd | textit_cmd | textbf_cmd | emph_cmd | underline_cmd

// mbox
mbox_cmd: "\\mbox{" phrase "}"

// Sectioning
section_cmd: "\\section{" phrase "}"
subsection_cmd: "\\subsection{" phrase "}"
!olymp_section_cmd: "\\InputFile" | "\\OutputFile" | "\\Note" | "\\Notes" | "\\Example" | "\\Examples" | "\\Scoring"

// Images
includegraphics_cmd: "\\includegraphics{" text_phrase "}"

// Iframe
iframe_cmd: "\\iframe{" NUMBER "}{" NUMBER "}{" text_phrase "}"

// Olymp environments
exmp_cmd: "\\exmp{" text_phrase "}{" text_phrase "}"
example_env: "\\begin{example}" (exmp_cmd | _WHITESPACE | _COMMENT)* "\\end{example}"

// Document structure
multiple_newlines: /\n{2,}/
_phrasing_element: _COMMENT | _plain_text | inline_math | verb_cmd | path_cmd | url_cmd | href_cmd | mintinline_cmd | includegraphics_cmd | iframe_cmd | _text_style_cmd | mbox_cmd
_text_phrasing_element: _COMMENT | _plain_text | multiple_newlines

phrase: _phrasing_element*
text_phrase: _text_phrasing_element*
paragraph: (_phrasing_element | display_math | verbatim_env | minted_env | center_env | example_env | itemize_env | enumerate_env)+

_breaker: (section_cmd | subsection_cmd | olymp_section_cmd | _PARAGRAPH_BREAKER) _WHITESPACE?

paragraphs: _WHITESPACE? ((_breaker* paragraph (_breaker+ paragraph)* _breaker*) // at least one paragraph
    | _breaker*) // no paragraphs

document: paragraphs

%import common.CNAME
%import common.NUMBER
'''

CHARACTER_MAP = {
    '~': '\u00A0',
    '<': '&lt;',
    '<<': '\u00AB',
    '>': '&gt;',
    '>>': '\u00BB',
    '-': '-',
    '--': '\u2013',
    '---': '\u2014',
    '{}': '',
}

ESCAPED_SYMBOL_MAP = {
    ',': '\u2009',  # THIN SPACE
    '&': '&amp;',
    '\\': '<br>',
}

NOARG_COMMAND_MAP = {
    'textbackslash': '\\',
    'ldots': '\u2026',
    'dots': '\u2026',
    'quad': '\u2003',  # EM SPACE
}


def _cut_leading_newline(s):
    if s.startswith('\n'):
        return s[1:]
    return s


class TreeToHtml(Transformer):
    def __init__(self, highlight_func, olymp_section_names, olymp_file_names):
        self._highlight_func = highlight_func
        self._olymp_section_names = olymp_section_names
        self._olymp_file_names = olymp_file_names

    def plain_text(self, children):
        return ''.join(children)

    @v_args(inline=True)
    def escaped_symbol(self, backslash, symbol):
        assert backslash == '\\'
        return ESCAPED_SYMBOL_MAP.get(symbol, symbol)

    @v_args(inline=True)
    def noarg_command(self, command):
        return NOARG_COMMAND_MAP[command[1:].rstrip()]

    @v_args(inline=True)
    def usual_symbol(self, symbol):
        return symbol

    def paragraph(self, children):
        return ['<div class="paragraph">'] + children + ['</div>']

    def paragraphs(self, children):
        return list(itertools.chain.from_iterable(children))

    def phrase(self, children):
        return ''.join(children)

    def text_phrase(self, children):
        return ''.join(children)

    @v_args(inline=True)
    def document(self, paragraphs):
        return ''.join(paragraphs)

    @v_args(inline=True)
    def math_symbol(self, symbol):
        return html_escape(symbol)

    def equation(self, children):
        return ''.join(children)

    @v_args(inline=True)
    def inline_math(self, equation):
        return '<span class="math">{}</span>'.format(equation)

    @v_args(inline=True)
    def display_math(self, equation):
        return '<div class="math">{}</div>'.format(equation)

    def inline_verbatim_block(self, children):
        return ''.join(children)

    @v_args(inline=True)
    def verb_cmd(self, block):
        return '<span class="verbatim">{}</span>'.format(html_escape(block))

    @v_args(inline=True)
    def path_cmd(self, block):
        return '<span class="path">{}</span>'.format(html_escape(block))

    @v_args(inline=True)
    def url_cmd(self, block):
        escaped = html_escape(block)
        return '<a href="{}" class="monospace">{}</a>'.format(escaped, escaped)

    @v_args(inline=True)
    def href_cmd(self, link, *children):
        return '<a href="{}">{}</a>'.format(html_escape(link), ''.join(children))

    @v_args(inline=True)
    def mintinline_cmd(self, language, block):
        return '<span class="verbatim">{}</span>'.format(self._highlight_func(block, language).rstrip('\n'))

    def verbatim_content(self, children):
        if len(children) > 0 and children[0] == '\n':
            children = children[1:]
        return ''.join(children)

    @v_args(inline=True)
    def verbatim_env(self, content):
        return '<div class="verbatim">{}</div>'.format(html_escape(content))

    @v_args(inline=True)
    def minted_env(self, language, content):
        return '<div class="verbatim">{}</div>'.format(self._highlight_func(content, language))

    @v_args(inline=True)
    def special_symbol(self, value):
        return CHARACTER_MAP[value]

    def texttt_cmd(self, children):
        return '<span class="monospace">{}</span>'.format(''.join(children))

    def textit_cmd(self, children):
        return '<i>{}</i>'.format(''.join(children))

    def textbf_cmd(self, children):
        return '<b>{}</b>'.format(''.join(children))

    def emph_cmd(self, children):
        return '<em>{}</em>'.format(''.join(children))

    def underline_cmd(self, children):
        return '<u>{}</u>'.format(''.join(children))

    def section_cmd(self, children):
        return '<h2>{}</h2>'.format(children[0])

    def subsection_cmd(self, children):
        return '<h3>{}</h3>'.format(''.join(children))

    @v_args(inline=True)
    def olymp_section_cmd(self, command):
        assert command[0] == '\\'
        command = command[1:]
        return '<h2>{}</h2>'.format(self._olymp_section_names.get(command, command))

    @v_args(inline=True)
    def center_env(self, paragraphs):
        return '<div class="center">{}</div>'.format(''.join(paragraphs))

    @v_args(inline=True)
    def includegraphics_cmd(self, url):
        return '<img src="{}">'.format(url.replace('"', '&quot;'))

    @v_args(inline=True)
    def iframe_cmd(self, width, height, url):
        return '<iframe width="{}" height="{}" src="{}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'.\
            format(width, height, url.replace('"', '&quot;'))

    @v_args(inline=True)
    def exmp_cmd(self, inp, outp):
        return '<tr><td>{}</td><td>{}</td></tr>'.format(
            _cut_leading_newline(inp),
            _cut_leading_newline(outp)
        )

    def example_env(self, rows):
        tokens = []

        input_name = self._olymp_file_names.get('input')
        output_name = self._olymp_file_names.get('output')
        if input_name is not None and output_name is not None:
            tokens.extend(['<thead><tr><th>', html_escape(input_name),
                           '</th><th>', html_escape(output_name), '</th></tr></thead>'])

        tokens.append('<tbody>')
        for row in rows:
            tokens.append(row)
        tokens.append('</tbody>')

        return ''.join(['<table class="example">'] + tokens + ['</table>'])

    @v_args(inline=True)
    def item(self, paragraphs):
        return '<li>{}</li>'.format(''.join(paragraphs))

    def itemize_env(self, items):
        return '<ul>{}</ul>'.format(''.join(items))

    def enumerate_env(self, items):
        return '<ol>{}</ol>'.format(''.join(items))

    def mbox_cmd(self, children):
        return '<span class="mbox">{}</span>'.format(''.join(children))

    @v_args(inline=True)
    def multiple_newlines(self, data):
        return data


DEBUG = True
PARSER = 'lalr'
TEX_PARSER = Lark(TEX_GRAMMAR, parser=PARSER, debug=DEBUG, start='document')
TEX_PARSER_INLINE = Lark(TEX_GRAMMAR, parser=PARSER, debug=DEBUG, start='phrase')


def _make_error_page(tex, inline, u):
    body = '{}: {}'.format(type(u).__name__, u)
    if inline:
        body = body.splitlines()[0]
    return '<{0} class="monospace error">{1}</{0}>'.format('span' if inline else 'div', html_escape(body))


def tex2html(tex, inline=False, pygmentize=True, wrap=True, throw=False, olymp_section_names={}, olymp_file_names={}):
    # Convert to single-byte UNIX newlines
    tex = tex.replace('\r\n', '\n').replace('\r', '\n')

    parser = TEX_PARSER_INLINE if inline else TEX_PARSER
    try:
        tree = parser.parse(tex)
        transformer = TreeToHtml(get_highlight_func(pygmentize), olymp_section_names, olymp_file_names)
        html = transformer.transform(tree)
    except UnexpectedInput as u:
        if throw:
            raise
        html = _make_error_page(tex, inline, u)

    if not wrap:
        return html
    else:
        return '<{0} class="pylightex">{1}</{0}>'.format('span' if inline else 'div', html)
