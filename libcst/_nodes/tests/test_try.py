# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict
from typing import Any

import libcst as cst
from libcst import CodeRange, parse_statement
from libcst._nodes.tests.base import CSTNodeTest, DummyIndentedBlock
from libcst.testing.utils import data_provider


class TryTest(CSTNodeTest):
    @data_provider(
        (
            # Simple try/except block
            # pyre-fixme[6]: Incompatible parameter type
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                ),
                "code": "try: pass\nexcept: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (2, 12)),
            },
            # Try/except with a class
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("Exception"),
                        ),
                    ),
                ),
                "code": "try: pass\nexcept Exception: pass\n",
                "parser": parse_statement,
            },
            # Try/except with a named class
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("Exception"),
                            name=cst.AsName(cst.Name("exc")),
                        ),
                    ),
                ),
                "code": "try: pass\nexcept Exception as exc: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (2, 29)),
            },
            # Try/except with multiple clauses
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("TypeError"),
                            name=cst.AsName(cst.Name("e")),
                        ),
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("KeyError"),
                            name=cst.AsName(cst.Name("e")),
                        ),
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                ),
                "code": "try: pass\n"
                + "except TypeError as e: pass\n"
                + "except KeyError as e: pass\n"
                + "except: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (4, 12)),
            },
            # Simple try/finally block
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "code": "try: pass\nfinally: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (2, 13)),
            },
            # Simple try/except/finally block
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                    finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "code": "try: pass\nexcept: pass\nfinally: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (3, 13)),
            },
            # Simple try/except/else block
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                    orelse=cst.Else(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "code": "try: pass\nexcept: pass\nelse: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (3, 10)),
            },
            # Simple try/except/else block/finally
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                    orelse=cst.Else(cst.SimpleStatementSuite((cst.Pass(),))),
                    finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "code": "try: pass\nexcept: pass\nelse: pass\nfinally: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (4, 13)),
            },
            # Verify whitespace in various locations
            {
                "node": cst.Try(
                    leading_lines=(cst.EmptyLine(comment=cst.Comment("# 1")),),
                    body=cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            leading_lines=(cst.EmptyLine(comment=cst.Comment("# 2")),),
                            type=cst.Name("TypeError"),
                            name=cst.AsName(
                                cst.Name("e"),
                                whitespace_before_as=cst.SimpleWhitespace("  "),
                                whitespace_after_as=cst.SimpleWhitespace("  "),
                            ),
                            whitespace_after_except=cst.SimpleWhitespace("  "),
                            whitespace_before_colon=cst.SimpleWhitespace(" "),
                            body=cst.SimpleStatementSuite((cst.Pass(),)),
                        ),
                    ),
                    orelse=cst.Else(
                        leading_lines=(cst.EmptyLine(comment=cst.Comment("# 3")),),
                        body=cst.SimpleStatementSuite((cst.Pass(),)),
                        whitespace_before_colon=cst.SimpleWhitespace(" "),
                    ),
                    finalbody=cst.Finally(
                        leading_lines=(cst.EmptyLine(comment=cst.Comment("# 4")),),
                        body=cst.SimpleStatementSuite((cst.Pass(),)),
                        whitespace_before_colon=cst.SimpleWhitespace(" "),
                    ),
                    whitespace_before_colon=cst.SimpleWhitespace(" "),
                ),
                "code": "# 1\ntry : pass\n# 2\nexcept  TypeError  as  e : pass\n# 3\nelse : pass\n# 4\nfinally : pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((2, 0), (8, 14)),
            },
            # Please don't write code like this
            {
                "node": cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    handlers=(
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("TypeError"),
                            name=cst.AsName(cst.Name("e")),
                        ),
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            type=cst.Name("KeyError"),
                            name=cst.AsName(cst.Name("e")),
                        ),
                        cst.ExceptHandler(
                            cst.SimpleStatementSuite((cst.Pass(),)),
                            whitespace_after_except=cst.SimpleWhitespace(""),
                        ),
                    ),
                    orelse=cst.Else(cst.SimpleStatementSuite((cst.Pass(),))),
                    finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "code": "try: pass\n"
                + "except TypeError as e: pass\n"
                + "except KeyError as e: pass\n"
                + "except: pass\n"
                + "else: pass\n"
                + "finally: pass\n",
                "parser": parse_statement,
                "expected_position": CodeRange((1, 0), (6, 13)),
            },
            # Verify indentation
            {
                "node": DummyIndentedBlock(
                    "    ",
                    cst.Try(
                        cst.SimpleStatementSuite((cst.Pass(),)),
                        handlers=(
                            cst.ExceptHandler(
                                cst.SimpleStatementSuite((cst.Pass(),)),
                                type=cst.Name("TypeError"),
                                name=cst.AsName(cst.Name("e")),
                            ),
                            cst.ExceptHandler(
                                cst.SimpleStatementSuite((cst.Pass(),)),
                                type=cst.Name("KeyError"),
                                name=cst.AsName(cst.Name("e")),
                            ),
                            cst.ExceptHandler(
                                cst.SimpleStatementSuite((cst.Pass(),)),
                                whitespace_after_except=cst.SimpleWhitespace(""),
                            ),
                        ),
                        orelse=cst.Else(cst.SimpleStatementSuite((cst.Pass(),))),
                        finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                    ),
                ),
                "code": "    try: pass\n"
                + "    except TypeError as e: pass\n"
                + "    except KeyError as e: pass\n"
                + "    except: pass\n"
                + "    else: pass\n"
                + "    finally: pass\n",
                "parser": None,
            },
            # Verify indentation in bodies
            {
                "node": DummyIndentedBlock(
                    "    ",
                    cst.Try(
                        cst.IndentedBlock((cst.SimpleStatementLine((cst.Pass(),)),)),
                        handlers=(
                            cst.ExceptHandler(
                                cst.IndentedBlock(
                                    (cst.SimpleStatementLine((cst.Pass(),)),)
                                ),
                                whitespace_after_except=cst.SimpleWhitespace(""),
                            ),
                        ),
                        orelse=cst.Else(
                            cst.IndentedBlock((cst.SimpleStatementLine((cst.Pass(),)),))
                        ),
                        finalbody=cst.Finally(
                            cst.IndentedBlock((cst.SimpleStatementLine((cst.Pass(),)),))
                        ),
                    ),
                ),
                "code": "    try:\n"
                + "        pass\n"
                + "    except:\n"
                + "        pass\n"
                + "    else:\n"
                + "        pass\n"
                + "    finally:\n"
                + "        pass\n",
                "parser": None,
            },
        )
    )
    def test_valid(self, **kwargs: Any) -> None:
        self.validate_node(**kwargs)

    @data_provider(
        (
            # pyre-fixme[6]: Incompatible parameter type
            {
                "get_node": lambda: cst.AsName(cst.Name("")),
                "expected_re": "empty name identifier",
            },
            {
                "get_node": lambda: cst.AsName(
                    cst.Name("bla"), whitespace_after_as=cst.SimpleWhitespace("")
                ),
                "expected_re": "between 'as'",
            },
            {
                "get_node": lambda: cst.AsName(
                    cst.Name("bla"), whitespace_before_as=cst.SimpleWhitespace("")
                ),
                "expected_re": "before 'as'",
            },
            {
                "get_node": lambda: cst.ExceptHandler(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    name=cst.AsName(cst.Name("bla")),
                ),
                "expected_re": "name for an empty type",
            },
            {
                "get_node": lambda: cst.ExceptHandler(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    type=cst.Name("TypeError"),
                    whitespace_after_except=cst.SimpleWhitespace(""),
                ),
                "expected_re": "at least one space after except",
            },
            {
                "get_node": lambda: cst.Try(cst.SimpleStatementSuite((cst.Pass(),))),
                "expected_re": "at least one ExceptHandler or Finally",
            },
            {
                "get_node": lambda: cst.Try(
                    cst.SimpleStatementSuite((cst.Pass(),)),
                    orelse=cst.Else(cst.SimpleStatementSuite((cst.Pass(),))),
                    finalbody=cst.Finally(cst.SimpleStatementSuite((cst.Pass(),))),
                ),
                "expected_re": "at least one ExceptHandler in order to have an Else",
            },
        )
    )
    def test_invalid(self, **kwargs: Any) -> None:
        self.assert_invalid(**kwargs)
