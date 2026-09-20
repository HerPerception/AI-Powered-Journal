"""Throwaway: how does Jinja render None, vs an empty string, vs a real value?

Run it, read the output, then delete it. It is not part of the app.
"""
from jinja2 import Template

t = Template("mood_label: [{{ m }}]")

print("None   ->", repr(t.render(m=None)))
print("''     ->", repr(t.render(m="")))
print("'calm' ->", repr(t.render(m="calm")))
