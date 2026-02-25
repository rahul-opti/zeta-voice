import cProfile
import io
import os
import pstats
from collections.abc import Callable
from functools import wraps
from typing import Any

from carriage_services.paths import PROJECT_PATH


def profile_method(sort_by: str = "cumulative", lines: int = 30) -> Callable:
    """
    Decorator to profile a single method in detail, only showing project code.

    Args:
        sort_by (str): Sorting key for stats.
        lines (int): Number of lines to display.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if os.getenv("ENABLE_PROFILING") in ("1", "true", "yes"):
                pr = cProfile.Profile()
                pr.enable()
                result = await func(*args, **kwargs)
                pr.disable()

                s = io.StringIO()
                stats = pstats.Stats(pr).sort_stats(sort_by)

                project_root_abs = os.path.abspath(PROJECT_PATH)

                def is_project_file(filename: str) -> bool:
                    return filename.startswith(project_root_abs) and "site-packages" not in filename

                filtered_stats = {key: value for key, value in stats.stats.items() if is_project_file(key[0])}  # type: ignore

                filtered = pstats.Stats()
                filtered.stats = filtered_stats  # type: ignore
                filtered.sort_stats(sort_by)
                filtered.stream = s  # type: ignore
                filtered.print_stats(lines)

                print(f"\n[Profiler: {func.__name__}()]")
                print(s.getvalue())
                return result
            else:
                return await func(*args, **kwargs)

        return wrapper

    return decorator
