"""What "today" is, in one place.

Nine services defined this identically -- across Tasks, Finances and Jobs -- and
nine copies of a one-line function are nine chances for one of them to start
meaning something slightly different: a timezone, a test seam, a clock injected
for one module and not the rest.

Kept as a function rather than a constant because that is the seam: a service
that needs to be told what day it is takes an `on_day` argument, and the ones
that do not call this. Anything that starts needing a timezone comes through
here.
"""

from datetime import date


def today() -> date:
    return date.today()
