"""Tracing with Langfuse. Optional: it is on when both Langfuse keys are in .env.

What gets recorded, and how it is organised:

  observation  one step: a model call (with tokens and cost), a tool call, an agent run.
               PydanticAI emits these by itself once it is instrumented.
  trace        one unit of work: one chat turn, one datasheet. Its name says what was
               done ("answer-question"), its input and output are what a reviewer wants
               to see at a glance: the question and the answer, not the whole prompt.
  session      one conversation: all turns of one chat share a session id, so Langfuse
               can replay the conversation in order.

Without keys every function here does nothing, and nothing leaves the machine.

Note on personal data: a trace holds what the model saw, including query results.
Those can contain customer names and cities (phone numbers are not in the graph).
The sample data is invented; with real customers, mask or self-host first.
"""
import os
from contextlib import contextmanager

_on = False


def setup_tracing() -> bool:
    """Turn tracing on if the keys are set. Returns whether it is on.

    Call this after load_dotenv(), so the keys are already in the environment.
    """
    global _on
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return False
    # Keeps these traces apart from a deployed version's in dashboards and evaluations.
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")
    from langfuse import get_client
    from pydantic_ai import Agent
    get_client()            # reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
    Agent.instrument_all()  # PydanticAI emits OpenTelemetry spans; Langfuse collects them
    _on = True
    return True


class _NoTrace:
    def update(self, **_) -> None:
        pass


@contextmanager
def trace(name: str, *, input, session_id: str | None = None,
          tags: list[str] | None = None, metadata: dict[str, str] | None = None):
    """One unit of work as one trace. Everything the agent does inside is nested under it.

      with trace("answer-question", input=question, session_id=chat) as t:
          answer = ...
          t.update(output=answer)

    name      what is done, verb first, the same for every run (no ids, no model names)
    tags      which part of the application ("assistant", "extraction"), for filtering
    metadata  run-specific values such as the model; short strings only
    """
    if not _on:
        yield _NoTrace()
        return
    from langfuse import get_client, propagate_attributes
    with get_client().start_as_current_observation(name=name, as_type="span", input=input) as span:
        # propagate_attributes puts these on every observation created inside the block.
        with propagate_attributes(trace_name=name, session_id=session_id, tags=tags, metadata=metadata):
            yield span


def flush() -> None:
    """Send what is still queued. Call before a script ends, or its last traces are lost."""
    if _on:
        from langfuse import get_client
        get_client().flush()
