"""
Reporter definitions.

A Reporter informs a UI of the state.
"""
import time
from contextlib import contextmanager

from .util import format_timedelta


class BaseReporter(object):
    """
    Base class for all reporters.
    """
    def msg(self, s, end="\n"):
        """
        Print a message.

        @param s: message to print
        @type s: L{str}
        @param end: what to print after the message. Default: linebreak
        @typ end: l{str}
        """
        pass

    @contextmanager
    def with_progress(self, description, max, unit=None):
        """
        This is a context manager which returns a BaseProgressReporter usable
        to indicate progress.

        @param description: description for progress
        @type description: L{str}
        @param max: max progress value
        @type max: L{int}
        @param unit: unit to use in display
        @type unit: L{str} or L{None}
        @return: a context manager whose value can be used for progress indication.
        @rtype: contextmanager with L{BaseProgressReporter}
        """
        bpr = BaseProgressReporter(description, max, unit=unit)
        try:
            yield bpr
        except Exception:
            bpr.finish(True)
            raise
        else:
            bpr.finish(False)


class BaseProgressReporter(object):
    """
    Base class for ProgressReporters.
    This is used as a context value from L{BaseReporter.with_progress}.
    """
    def __init__(self, description, max, unit=None):
        """
        The default constructor.

        @param description: description for progress
        @type description: L{str}
        @param max: max progress value
        @type max: L{int}
        @param unit: unit to use in display
        @type unit: L{str} or L{None}
        """
        assert isinstance(description, str)
        assert isinstance(unit, str) or (unit is None)
        self.description = description
        self.unit = unit
        self.max = max
        self.steps = 0
        self.initial_steps = 0
        self.start_time = time.time()

    def get_eta(self):
        """
        Return the estimated time in seconds until completion.

        @return: the estimated time (in seconds) until completion
        @rtype: L{float} or L{None}
        """
        if self.steps == 0:
            return None
        cur_time = time.time()
        time_passed = cur_time - self.start_time
        time_per_step = time_passed / float(self.steps - self.initial_steps if self.steps > self.initial_steps else self.steps)
        remaining_steps = self.max - self.steps
        remaining_time = remaining_steps * time_per_step
        return remaining_time

    def advance(self, n):
        """
        Advance the progress by n steps.

        @param n: number of steps to advance
        @type n: L{int}
        """
        if self.steps == 0:
            self.start_time = time.time()
            self.initial_steps = n
        self.steps += n

    def finish(self, error=False):
        """
        Called when the context is left.

        @param error: if nonzero, left due to an error
        @type error: l{bool}
        """
        pass


class VoidReporter(BaseReporter):
    """
    A Reporter discarding all messages.
    """
    def msg(self, s, end="\n"):
        pass

    @contextmanager
    def with_progress(self, description, max, unit=None):
        yield VoidProgressReporter(description, max, unit=unit)


class VoidProgressReporter(BaseProgressReporter):
    """
    ProgressReporter used by L{VoidReporter}.
    """
    pass


class StdoutReporter(BaseReporter):
    """
    A Reporter printing all messages.
    """
    def msg(self, s, end="\n"):
        print(s, end=end, flush=True)

    @contextmanager
    def with_progress(self, description, max, unit=None):
        spr = StdoutProgressReporter(description, max, unit=unit)
        try:
            yield spr
        except Exception:
            spr.finish(True)
            raise
        else:
            spr.finish(False)


class StdoutProgressReporter(BaseProgressReporter):
    """
    Progress reporter used by L{StdoutReporter}.

    @cvar BAR_LENGTH: length of progress bar to print
    @type BAR_LENGTH: L{int}
    """

    BAR_LENGTH = 20
    DRAW_UNITS = True

    def __init__(self, *args, **kwargs):
        BaseProgressReporter.__init__(self, *args, **kwargs)
        self.print_progress()

    def advance(self, steps):
        BaseProgressReporter.advance(self, steps)
        self.print_progress()

    def _get_bar(self, progress, error=False):
        """
        Return the progress bar as a string, not including any decorations.

        @param progress: completion progress to draw (as float between 0 and 1)
        @type progress: L{float}
        @param error: whether to draw the bar in a way that shows that an error occurred or not
        @type error: L{bool}
        @return: the progress bar
        @rtype: L{str}
        """
        assert isinstance(progress, float)
        n_filled = int(progress * self.BAR_LENGTH)
        if n_filled == 0:
            filled_str = ""
        elif n_filled == self.BAR_LENGTH:
            filled_str = "=" * self.BAR_LENGTH
        else:
            filled_str = "=" * (n_filled - 1) + ">"
        if error:
            empty_char = "X"
        else:
            empty_char = " "
        empty_str = empty_char * (self.BAR_LENGTH - len(filled_str))
        bar = "[" + filled_str + empty_str + "]"
        return bar

    def _get_rate(self):
        """
        Return the progress rate string.

        @return: a string describing the progress speed. May be empty.
        @rtype: L{str}
        """
        if (self.unit is None) or (not self.DRAW_UNITS):
            unit_str = ""
        else:
            time_passed = time.time() - self.start_time
            progress_per_second = round(self.steps / max(time_passed, 0.00000000000000001), 2)
            unit_str = "{} {}/s".format(progress_per_second, self.unit)
        return unit_str

    def print_progress(self):
        """
        Print the current progress.
        """
        progress = ((self.steps / self.max) if self.max > 0 else 0.0)
        bar = self._get_bar(progress)
        eta = self.get_eta()
        eta_string = (format_timedelta(round(eta, 2)) if eta is not None else "??:??")
        unit_str = self._get_rate()
        if unit_str:
            unit_str = "({})".format(unit_str)
        print("\33[2K{} {} {} {} ".format(self.description, bar, eta_string, unit_str), end="\r")

    def finish(self, error=False):
        if error:
            progress = self.steps / self.max
            bar = self._get_bar(progress, error=True)
        else:
            bar = self._get_bar(1.0, error=False)
        time_str = format_timedelta(time.time() - self.start_time)
        unit_str = self._get_rate()
        if unit_str:
            unit_str = "({})".format(unit_str)
        print("\33[2K{} {} {} {} ".format(self.description, bar, time_str, unit_str))


if __name__ == "__main__":
    # test code
    rep = StdoutReporter()
    rep.msg("Beginning test...")
    try:
        with rep.with_progress("test", 300, unit="steps") as pb:
            for i in range(300):
                pb.advance(1)
                time.sleep(0.02)
                if i == 250:
                    raise RuntimeError("test")
    except RuntimeError:
        pass
    rep.msg("Done.")
