"""
Showcases how to use `Lark.scan` to select a pattern from a larger text without having to parse all of it.

Uses `requests` to fetch the current wikitext from `Python (Programming Language)` and uses a simple grammar
to extract all wikitext templates used in the page.

"""

from collections import Counter
from pprint import pprint

import lark
import requests

page_name = "Python_(programming_language)"
url = f"https://en.wikipedia.org/wiki/{page_name}?action=raw"

wikitext = requests.get(url).text

grammar = r"""
template: "{{" TEXT ("|" argument)* "}}"
text: (TEXT|template)+
argument: /\w+(?==)/ "=" text -> named_argument
        | text -> numbered_argument

TEXT: / (?:[^{}|]
      | \{(?!\{)
      | \}(?!\})
      )+/x
"""
parser = lark.Lark(grammar, parser='lalr', start='template')
used_templates = Counter()
inner_templates = 0
for (start, end), res in parser.scan(wikitext):
    for temp in res.find_data('template'):
        if temp != res:
            inner_templates += 1
        used_templates[temp.children[0].value] += 1

pprint(used_templates)
print("Total templates used:", used_templates.total())
print("Number of templates nested inside others:", inner_templates)
