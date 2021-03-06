"""Greenlet-based main-thread trampolining for UIs.

During the normal execution of a function, it will be running in the
main thread. However, special functions (provided by this module) will
allow for that function to be interrupted, leave the main thread, wait
for some action, and then resume the function back in the main thread.

::

    @trampoline.decorate(threads.call_in_main_thread)
    def test_something(self):

        # We are running in the main thread.
        dialog = my_tool.run()

        # Fall back out of the main event loop while we want for the following
        # to become true.
        button = trampoline.qpath(dialog, '//QPushButton[@enabled]', timeout=5)[0]

        # Do something else in the main thread.

        # Wait a second while letting the event loop resume.
        trampoline.sleep(1)


"""

import functools
import time
import sys
import contextlib


from .qpath import qpath as _qpath
from .threads import call_in_main_thread


if True:

    start_time = time.time()

    def debug(msg=None, *args, **kwargs):
        if args:
            msg = msg % args
        debug.indent -= int(kwargs.get('dedent', 0))

        if msg:
            sys.__stdout__.write(('%8.3f ' % ((time.time() - start_time) * 1000)) + '  | ' * debug.indent + msg + '\n')
            sys.__stdout__.flush()

        debug.indent += int(kwargs.get('indent', 0))

    debug.indent = 0

    @contextlib.contextmanager
    def indent(*args):
        debug(*args, indent=True)
        try:
            yield
        finally:
            debug(dedent=True)

else:

    def debug(msg=None, *args, **kwargs):
        pass

    @contextlib.contextmanager
    def indent(*args, **kwargs):
        yield


def trampoline(call_in_main_thread, func, *args, **kwargs):
    """Call a function in the main thread, allowing it to bounce into the background.

    When called via ``trampoline`` a function's main body will execute in the
    main thread. However, it is allowed to use :func:`bounce` (and functions
    which use :func:`bounce`) to effectively run synchronous tasks in the
    background while giving the main thread a chance to perform other tasks.

    ::
    
        def my_func():
            print 'Going to sleep (without locking up the main thread)...'
            bounce(sleep, 10)
            print 'Back!'

    :param call_in_main_thread: Function to call another function in the main thread.
    :param func: The function to run.
    :param *args: Passed to ``func``.
    :param **kwargs: Passed to ``func``.

    """

    # Must be imported here so that the maya test bootstrap can insert into
    # the sys.path
    global greenlet
    import greenlet

    def _construct_and_start(args, kwargs):
        g = greenlet.greenlet(func)
        res = g.switch(*args, **kwargs)
        return g, res

    debug('trampoline', indent=True)
    g = None
    res = None
    while g is None or not g.dead:

        debug('top of loop')

        exc = None
        if res is not None:
            with indent('calling %r', res):
                try:
                    func, args, kwargs = res
                    res = func(*args, **kwargs)
                except Exception as exc:
                    pass

        if g is None:
            with indent('starting greenlet'):
                g, res = call_in_main_thread(_construct_and_start, args, kwargs)

        elif exc:
            with indent('raising in main thread: %r', exc):
                call_in_main_thread(g.throw, exc)

        else:
            with indent('sending to main thread: %r', res):
                res = call_in_main_thread(g.switch, res)

    debug(dedent=True)
    return res


def decorate(call_in_main_thread):
    """Decorate a function so that its body runs in the main thread as
    if called via :func:`trampoline`."""
    def _decorator(func):
        @functools.wraps(func)
        def _decorated(*args, **kwargs):
            return trampoline(call_in_main_thread, func, *args, **kwargs)
        return _decorated
    return _decorator


def bounce(func=None, *args, **kwargs):
    """Perform an effectively sychnorous call in the background from a
    trampolined function.

    :param func: The function to call.
    :param *args: Passed to ``func``.
    :param **kwargs: Passed to ``func``.
    :returns: The return value of ``func``.
    :raises: Anything that ``func`` raises.

    """

    debug('bounce to %r, %r, %r', func, args, kwargs)
    if func:
        res = greenlet.getcurrent().parent.switch(func, args, kwargs)
    else:
        greenlet.getcurrent().parent.switch(None)
        res = None
    debug('bounce landed with %r', res)
    return res


def sleep(seconds):
    """Sleep in the background."""
    return bounce(time.sleep, seconds)


def raise_(e):
    bounce(_raise, e)


def _raise(e):
    raise e


def qpath(root, query, timeout=5, repeat_delay=0.033, strict=False):
    start_time = time.time()
    while True:
        res = _qpath(root, query)
        if res:
            return res
        if (time.time() - start_time) >= timeout:
            break
        time.sleep(repeat_delay)
    if strict:
        raise RuntimeError('could not resolve qpath: %r' % query)


def test():

    def main_thread(func, *args, **kwargs):
        res = func(*args, **kwargs)
        return res

    @decorate(main_thread)
    def tester(*args, **kwargs):
        debug('1 - func started with %r, %r', args, kwargs)
        sleep(0.1)
        debug('2')
        bounce()
        debug('3')
        
        try:
            raise_(ValueError('expected'))
        except ValueError:
            debug('4')
        else:
            debug("SHOULD NOT GET HERE!!!")

        return 'we finished'

    debug('Starting...')

    res = tester(1, 2, 3, key='value')

    debug('Done.')
    debug('Return value: %r', res)


if __name__ == '__main__':
    test()



