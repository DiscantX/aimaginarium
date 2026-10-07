"""Tests for the loading spinner module."""

import asyncio
import io
import time

from aimaginarium.ui.utils.spinner import Spinner


def test_spinner_sync_context_manager():
    stream = io.StringIO()
    with Spinner(messages=["Loadingtest..."], interval=0.01, stream=stream):
        time.sleep(0.05)
    output = stream.getvalue()
    assert "Loadingtest..." in output


def test_spinner_manual_start_stop():
    stream = io.StringIO()
    spinner = Spinner(messages=["Manualtest..."], interval=0.01, stream=stream)
    spinner.start()
    time.sleep(0.03)
    spinner.stop()
    output = stream.getvalue()
    assert "Manualtest..." in output


def test_spinner_async_context_manager():
    async def go():
        stream = io.StringIO()
        async with Spinner(messages=["Asynctest..."], interval=0.01, stream=stream):
            await asyncio.sleep(0.03)
        return stream.getvalue()

    output = asyncio.run(go())
    assert "Asynctest..." in output


def test_stop_clears_the_line_and_resets_colours():
    stream = io.StringIO()
    spinner = Spinner(messages=["x"], interval=0.01, stream=stream).start()
    time.sleep(0.03)
    spinner.stop()
    assert stream.getvalue().endswith("\r\033[K\033[0m")
