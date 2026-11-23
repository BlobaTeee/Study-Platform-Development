"""A unit after a number as its symbol: "500 joule" is "500 J", "2 Pascal"
is "2 Pa", "3 mét trên giây" is "3 m/s".

The prompts ask for symbols (`WRITING_STYLE`); this catches what the model
spells out anyway. Only a unit right after a number changes, so prose about a
unit ("the joule is the unit of energy", "định luật Pascal") is left alone.
Time words (second, phút, giờ) change only inside a rate ("km per hour"), since
"học 2 giờ mỗi ngày" is not a measurement.
"""
from __future__ import annotations

import re

_PREFIX = {'k': r'kilo|ki-?lô', 'M': r'mega|mê-?ga', 'G': r'giga|gi-?ga', 'm': r'milli|mi-?li',
           'c': r'centi|xen-?ti', 'µ': r'micro|mi-?crô', 'n': r'nano|na-?nô'}

# Longer names first: "watt-hour" before "watt". (?-i:...) is case-sensitive:
# "Newton" and "Jun" are a person and a month, "newton" and "jun" are units.
_UNIT = {
    'Wh': r'watt[- ]hours?|oát[- ]giờ',
    'eV': r'electron[- ]?volts?|êlectron[- ]?vôn|electron[- ]?vôn',
    'J': r'joules?|(?-i:jun)',
    'Pa': r'pascals?|pascan|pa-?xcan|pa-?scan',
    'N': r'(?-i:newtons?)|niu-?tơn',
    'W': r'watts?|oát',
    'V': r'volts?|vôn',
    'A': r'amperes?|ampères?|amps?|ampe',
    'Ω': r'ohms?|ôm',
    'Hz': r'hertz|héc(?!\s*-?\s*ta\b)',
    'C': r'coulombs?|cu-?lông',
    'K': r'kelvins?|ken-?vin',
    'T': r'teslas?',
    'F': r'farads?|fa-?ra',
    'm': r'met(?:er|re)s?|mét',
    'g': r'gram(?:me)?s?|gam',
    'L': r'lit(?:er|re)s?|lít',
    'mol': r'moles?',
}
_TIME = {'s': r'seconds?|giây', 'min': r'minutes?|phút', 'h': r'hours?|giờ'}
_DEGREES = {'°C': r'(?:độ|degrees?)\s*(?:Celsius|(?-i:C))', '°F': r'(?:độ|degrees?)\s*(?:Fahrenheit|(?-i:F))'}

_ANY_PREFIX = '|'.join(_PREFIX.values())
_ANY_UNIT = '|'.join(_UNIT.values())
_ONE = rf'(?:(?:{_ANY_PREFIX})-?)?(?:{_ANY_UNIT})'
_TERM = rf'(?:(?:square|cubic)\s+{_ONE}|{_ONE}(?:\s+(?:vuông|khối))?)'
_RATE = rf'(?:\s*(?:\bper\b|\btrên\b|/)\s*(?:{_TERM}|{"|".join(_TIME.values())})(?:\s+(?:squared|bình phương))?)'
_EXPR = rf'(?:{"|".join(_DEGREES.values())}|{_TERM}{_RATE}?)'
# The end of a word, and not a meter ("vôn kế", "ampe kế").
_END = r'(?![\w-])(?!\s+kế\b)'

# A number, or maths held out of the text by `tidy_prose` (\x01n\x01).
_AFTER_NUMBER = re.compile(rf'(?P<num>(?<![\w.,])\d(?:[\d.,]*\d)?|\x01\d+\x01)(?P<gap>\s*)(?P<unit>{_EXPR}){_END}',
                           re.I)
# Inside maths: \text{joule}, \mathrm{ pascal }.
_IN_MATH = re.compile(rf'\\(?:text|mathrm|rm)\s*\{{(?P<lead>\s*)(?P<unit>{_EXPR})\s*\}}', re.I)


def _symbol(phrase: str) -> str | None:
    """The symbol of one unit name with its prefix, or None."""
    phrase = phrase.strip()
    for sym, pattern in {**_DEGREES, **_TIME}.items():
        if re.fullmatch(pattern, phrase, re.I):
            return sym
    power = ''
    m = re.fullmatch(r'(square|cubic)\s+(.+)', phrase, re.I)
    if m:
        power, phrase = ('²' if m.group(1).lower() == 'square' else '³'), m.group(2)
    m = re.fullmatch(r'(.+?)\s+(vuông|khối)', phrase, re.I)
    if m:
        power, phrase = ('²' if m.group(2).lower() == 'vuông' else '³'), m.group(1)
    for prefix_sym, prefix in [('', '')] + list(_PREFIX.items()):
        for sym, pattern in _UNIT.items():
            if re.fullmatch(rf'(?:{prefix})-?(?:{pattern})' if prefix else pattern, phrase, re.I):
                return prefix_sym + sym + power
    return None


def _symbol_of(expr: str) -> str | None:
    """The symbol of a whole unit expression, a rate included ("m/s²")."""
    parts = re.split(r'\s*(?:\bper\b|\btrên\b|/)\s*', expr.strip(), maxsplit=1, flags=re.I)
    head = _symbol(parts[0])
    if head is None or len(parts) == 1:
        return head
    tail, squared = parts[1], ''
    m = re.fullmatch(r'(.+?)\s+(?:squared|bình phương)', tail, re.I)
    if m:
        tail, squared = m.group(1), '²'
    below = _symbol(tail)
    return f'{head}/{below}{squared}' if below else None


def unit_symbols(text: str | None) -> str:
    """`text` with every unit written after a number as its symbol."""
    if not text:
        return text or ''

    def swap(m):
        sym = _symbol_of(m.group('unit'))
        return f'{m.group("num")} {sym}' if sym else m.group(0)

    return _AFTER_NUMBER.sub(swap, text)


_LATEX = {'Ω': r'\Omega', 'µ': r'\mu ', '°': r'^{\circ}', '²': '^2', '³': '^3'}


def unit_symbols_in_math(latex: str) -> str:
    """LaTeX with \\text{joule} as \\mathrm{J}."""
    def swap(m):
        sym = _symbol_of(m.group('unit'))
        if not sym:
            return m.group(0)
        body = ''.join(_LATEX.get(ch, ch) for ch in sym)
        return (r'\,' if m.group('lead') else '') + rf'\mathrm{{{body}}}'

    return _IN_MATH.sub(swap, latex)
