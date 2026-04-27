"""Task 1 雛形のスモークテスト（Task 2 以降で本実装と置換予定）。

CLAUDE.md 第10条 test-driven-development に従い、Task 1 段階では
パッケージが import 可能であることのみを検証する skeleton を置く。
本物の単体テストは Task 2（models）以降で各 RED ステップから書き起こす。
"""

import importlib


def test_src_package_importable():
    """src パッケージが import 可能（雛形配置の最低検証）."""
    module = importlib.import_module("src")
    assert module is not None


def test_tests_package_importable():
    """tests パッケージが import 可能."""
    module = importlib.import_module("tests")
    assert module is not None
