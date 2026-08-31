"""Shells out to the Java-side CrossLanguageDecimalTool CLI (see
contracts/generated/java/src/test/java/com/meridian/contracts/CrossLanguageDecimalTool.java)
so the cross-language decimal fidelity test in test_cross_language_decimal.py
can drive both languages against the same bytes.

Builds the module's test classpath once (via `mvn dependency:build-classpath`)
and caches it for the process lifetime -- repeated `mvn` invocations per
test case would make the test suite slow for no benefit, since the
classpath doesn't change between cases.
"""
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_JAVA_MODULE = _REPO_ROOT / "contracts" / "generated" / "java"

_classpath_cache: str | None = None


def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True, check=False, **kwargs)  # type: ignore[arg-type]


def _classpath() -> str:
    global _classpath_cache
    if _classpath_cache is not None:
        return _classpath_cache

    test_compile = _run(["mvn", "-q", "-pl", "contracts/generated/java", "test-compile"])
    if test_compile.returncode != 0:
        raise RuntimeError(f"mvn test-compile failed:\n{test_compile.stdout}\n{test_compile.stderr}")

    cp_file = _JAVA_MODULE / "target" / "test-classpath.txt"
    build_cp = _run(
        [
            "mvn",
            "-q",
            "-pl",
            "contracts/generated/java",
            "dependency:build-classpath",
            f"-Dmdep.outputFile={cp_file}",
            "-Dmdep.includeScope=test",
        ]
    )
    if build_cp.returncode != 0:
        raise RuntimeError(f"mvn dependency:build-classpath failed:\n{build_cp.stdout}\n{build_cp.stderr}")

    deps_cp = cp_file.read_text().strip()
    classes = _JAVA_MODULE / "target" / "classes"
    test_classes = _JAVA_MODULE / "target" / "test-classes"
    _classpath_cache = f"{deps_cp}:{classes}:{test_classes}"
    return _classpath_cache


def write_price(decimal_str: str, out_file: Path) -> None:
    result = _run(
        [
            "java",
            "-cp",
            _classpath(),
            "com.meridian.contracts.CrossLanguageDecimalTool",
            "write",
            decimal_str,
            str(out_file),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"Java write failed:\n{result.stdout}\n{result.stderr}")


def read_price(in_file: Path, expected_decimal_str: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "java",
            "-cp",
            _classpath(),
            "com.meridian.contracts.CrossLanguageDecimalTool",
            "read",
            str(in_file),
            expected_decimal_str,
        ]
    )
