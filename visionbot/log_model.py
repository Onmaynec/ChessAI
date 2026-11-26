"""Pure helpers for the bounded, searchable session journal."""
from __future__ import annotations

def matches(entry, category='all', query=''):
    tag, line = entry
    return (category == 'all' or category == tag) and query.strip().casefold() in line.casefold()

def select_entries(entries, category='all', query=''):
    return [entry for entry in entries if matches(entry, category, query)]

def export_text(entries, category='all', query=''):
    return ''.join(line for _, line in select_entries(entries, category, query))
