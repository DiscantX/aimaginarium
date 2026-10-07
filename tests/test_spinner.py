"""Tests for the loading spinner module."""

import asyncio
import io
import time

from aimaginarium.spinner import Spinner


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
