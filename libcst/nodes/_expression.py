# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict

import re
from abc import ABC
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
from tokenize import (
    Floatnumber as FLOATNUMBER_RE,
    Imagnumber as IMAGNUMBER_RE,
    Intnumber as INTNUMBER_RE,
)
from typing import Callable, Generator, List, Optional, Sequence, Union

from typing_extensions import Literal

from libcst._add_slots import add_slots
from libcst._base_visitor import CSTVisitor
from libcst._maybe_sentinel import MaybeSentinel
from libcst.nodes._base import (
    AnnotationIndicatorSentinel,
    CSTCodegenError,
    CSTNode,
    CSTValidationError,
)
from libcst.nodes._internal import (
    CodegenState,
    visit_optional,
    visit_required,
    visit_sentinel,
    visit_sequence,
)
from libcst.nodes._op import (
    AssignEqual,
    BaseBinaryOp,
    BaseBooleanOp,
    BaseCompOp,
    BaseUnaryOp,
    Colon,
    Comma,
    Dot,
    In,
    Is,
    IsNot,
    Minus,
    Not,
    NotIn,
    Plus,
)
from libcst.nodes._whitespace import BaseParenthesizableWhitespace, SimpleWhitespace


@add_slots
@dataclass(frozen=True)
class LeftSquareBracket(CSTNode):
    """
    Used by various nodes to denote a subscript or list section. This doesn't own
    the whitespace to the left of it since this is owned by the parent node.
    """

    whitespace_after: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "LeftSquareBracket":
        return LeftSquareBracket(
            whitespace_after=visit_required(
                "whitespace_after", self.whitespace_after, visitor
            )
        )

    def _codegen(self, state: CodegenState) -> None:
        state.tokens.append("[")
        self.whitespace_after._codegen(state)


@add_slots
@dataclass(frozen=True)
class RightSquareBracket(CSTNode):
    """
    Used by various nodes to denote a subscript or list section. This doesn't own
    the whitespace to the right of it since this is owned by the parent node.
    """

    whitespace_before: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "RightSquareBracket":
        return RightSquareBracket(
            whitespace_before=visit_required(
                "whitespace_before", self.whitespace_before, visitor
            )
        )

    def _codegen(self, state: CodegenState) -> None:
        self.whitespace_before._codegen(state)
        state.tokens.append("]")


@add_slots
@dataclass(frozen=True)
class LeftParen(CSTNode):
    """
    Used by various nodes to denote a parenthesized section. This doesn't own
    the whitespace to the left of it since this is owned by the parent node.
    """

    whitespace_after: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "LeftParen":
        return LeftParen(
            whitespace_after=visit_required(
                "whitespace_after", self.whitespace_after, visitor
            )
        )

    def _codegen(self, state: CodegenState) -> None:
        state.tokens.append("(")
        self.whitespace_after._codegen(state)


@add_slots
@dataclass(frozen=True)
class RightParen(CSTNode):
    """
    Used by various nodes to denote a parenthesized section. This doesn't own
    the whitespace to the right of it since this is owned by the parent node.
    """

    whitespace_before: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "RightParen":
        return RightParen(
            whitespace_before=visit_required(
                "whitespace_before", self.whitespace_before, visitor
            )
        )

    def _codegen(self, state: CodegenState) -> None:
        self.whitespace_before._codegen(state)
        state.tokens.append(")")


class _BaseParenthesizedNode(CSTNode, ABC):
    """
    We don't want to have another level of indirection for parenthesis in
    our tree, since that makes us more of a CST than an AST. So, all the
    expressions or atoms that can be wrapped in parenthesis will subclass
    this to get that functionality.
    """

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        if self.lpar and not self.rpar:
            raise CSTValidationError("Cannot have left paren without right paren.")
        if not self.lpar and self.rpar:
            raise CSTValidationError("Cannot have right paren without left paren.")
        if len(self.lpar) != len(self.rpar):
            raise CSTValidationError("Cannot have unbalanced parens.")

    @contextmanager
    def _parenthesize(self, state: CodegenState) -> Generator[None, None, None]:
        for lpar in self.lpar:
            lpar._codegen(state)
        yield
        for rpar in self.rpar:
            rpar._codegen(state)


class ExpressionPosition(Enum):
    LEFT = auto()
    RIGHT = auto()


class BaseExpression(_BaseParenthesizedNode, ABC):
    def _safe_to_use_with_word_operator(self, position: ExpressionPosition) -> bool:
        """
        Returns true if this expression is safe to be use with a word operator
        such as "not" without space between the operator an ourselves. Examples
        where this is true are "not(True)", "(1)in[1,2,3]", etc. This base
        function handles parenthesized nodes, but certain nodes such as tuples,
        dictionaries and lists will override this to signifiy that they're always
        safe.
        """

        return len(self.lpar) > 0 and len(self.rpar) > 0


class BaseAtom(BaseExpression, ABC):
    """
    > Atoms are the most basic elements of expressions. The simplest atoms are
    > identifiers or literals. Forms enclosed in parentheses, brackets or braces are
    > also categorized syntactically as atoms.

    -- https://docs.python.org/3/reference/expressions.html#atoms
    """

    pass


class BaseAssignTargetExpression(BaseExpression, ABC):
    """
    An expression that's valid on the left side of an assign statement.

    Python's grammar defines all expression as valid in this position, but the AST
    compiler further restricts the allowed types, which is what this type attempts to
    express.

    See also: https://github.com/python/cpython/blob/v3.8.0a4/Python/ast.c#L1120
    """

    pass


class BaseDelTargetExpression(BaseExpression, ABC):
    """
    An expression that's valid on the right side of a 'del' statement.

    Python's grammar defines all expression as valid in this position, but the AST
    compiler further restricts the allowed types, which is what this type attempts to
    express.

    This is similar to a BaseAssignTargetExpression, but excludes `Starred`.

    See also: https://github.com/python/cpython/blob/v3.8.0a4/Python/ast.c#L1120
    and: https://github.com/python/cpython/blob/v3.8.0a4/Python/compile.c#L4854
    """

    pass


@add_slots
@dataclass(frozen=True)
class Name(BaseAssignTargetExpression, BaseDelTargetExpression, BaseAtom):
    # The actual identifier string
    value: str

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Name":
        return Name(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=self.value,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _validate(self) -> None:
        super(Name, self)._validate()
        if len(self.value) == 0:
            raise CSTValidationError("Cannot have empty name identifier.")
        if not self.value.isidentifier():
            raise CSTValidationError("Name is not a valid identifier.")

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.value)


@add_slots
@dataclass(frozen=True)
class Ellipses(BaseAtom):
    """
    An ellipses "..."
    """

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Ellipses":
        return Ellipses(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append("...")


@add_slots
@dataclass(frozen=True)
class Integer(_BaseParenthesizedNode):
    value: str

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Integer":
        return Integer(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=self.value,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _validate(self) -> None:
        super(Integer, self)._validate()
        if not re.fullmatch(INTNUMBER_RE, self.value):
            raise CSTValidationError("Number is not a valid integer.")

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.value)


@add_slots
@dataclass(frozen=True)
class Float(_BaseParenthesizedNode):
    value: str

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Float":
        return Float(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=self.value,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _validate(self) -> None:
        super(Float, self)._validate()
        if not re.fullmatch(FLOATNUMBER_RE, self.value):
            raise CSTValidationError("Number is not a valid float.")

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.value)


@add_slots
@dataclass(frozen=True)
class Imaginary(_BaseParenthesizedNode):
    value: str

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Imaginary":
        return Imaginary(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=self.value,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _validate(self) -> None:
        super(Imaginary, self)._validate()
        if not re.fullmatch(IMAGNUMBER_RE, self.value):
            raise CSTValidationError("Number is not a valid imaginary.")

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.value)


@add_slots
@dataclass(frozen=True)
class Number(BaseAtom):
    # The actual number component
    number: Union[Integer, Float, Imaginary]

    # Any unary operator applied to the number
    operator: Optional[Union[Plus, Minus]] = None

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _safe_to_use_with_word_operator(self, position: ExpressionPosition) -> bool:
        """
        Numbers are funny. The expression "5in [1,2,3,4,5]" is a valid expression
        which evaluates to "True". So, encapsulate that here by allowing zero spacing
        with the left hand side of an expression with a comparison operator.
        """
        if position == ExpressionPosition.LEFT:
            return True
        return super(Number, self)._safe_to_use_with_word_operator(position)

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Number":
        return Number(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            operator=visit_optional("operator", self.operator, visitor),
            number=visit_required("number", self.number, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            operator = self.operator
            if operator is not None:
                operator._codegen(state)
            self.number._codegen(state)


class BaseString(BaseAtom, ABC):
    """
    A type that can be used anywhere that you need to explicitly take any
    string.
    """

    pass


@add_slots
@dataclass(frozen=True)
class SimpleString(BaseString):
    value: str

    # Sequence of open parenthesis for precidence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precidence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        super(SimpleString, self)._validate()

        # Validate any prefix
        prefix = self._get_prefix()
        if prefix not in ("", "r", "u", "b", "br", "rb"):
            raise CSTValidationError("Invalid string prefix.")
        prefixlen = len(prefix)
        # Validate wrapping quotes
        if len(self.value) < (prefixlen + 2):
            raise CSTValidationError("String must have enclosing quotes.")
        if (
            self.value[prefixlen] not in ['"', "'"]
            or self.value[prefixlen] != self.value[-1]
        ):
            raise CSTValidationError("String must have matching enclosing quotes.")
        # Check validity of triple-quoted strings
        if len(self.value) >= (prefixlen + 6):
            if self.value[prefixlen] == self.value[prefixlen + 1]:
                # We know this isn't an empty string, so there needs to be a third
                # identical enclosing token.
                if (
                    self.value[prefixlen] != self.value[prefixlen + 2]
                    or self.value[prefixlen] != self.value[-2]
                    or self.value[prefixlen] != self.value[-3]
                ):
                    raise CSTValidationError(
                        "String must have matching enclosing quotes."
                    )
        # We should check the contents as well, but this is pretty complicated,
        # partially due to triple-quoted strings.

    def _get_prefix(self) -> str:
        prefix = ""
        for c in self.value:
            if c in ['"', "'"]:
                break
            prefix += c
        return prefix.lower()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "SimpleString":
        return SimpleString(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=self.value,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.value)


class BaseFormattedStringContent(CSTNode, ABC):
    """
    A type that can be used anywhere that you need to take any part of a f-string.
    """

    pass


@add_slots
@dataclass(frozen=True)
class FormattedStringText(BaseFormattedStringContent):
    # The raw string value.
    value: str

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "FormattedStringText":
        return FormattedStringText(value=self.value)

    def _codegen(self, state: CodegenState) -> None:
        state.tokens.append(self.value)


@add_slots
@dataclass(frozen=True)
class FormattedStringExpression(BaseFormattedStringContent):
    # The expression we will render when printing the string
    expression: BaseExpression

    # An optional conversion specifier
    conversion: Optional[str] = None

    # An optional format specifier
    format_spec: Optional[Sequence[BaseFormattedStringContent]] = None

    # Whitespace
    whitespace_before_expression: BaseParenthesizableWhitespace = SimpleWhitespace("")
    whitespace_after_expression: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _validate(self) -> None:
        if self.conversion is not None and self.conversion not in ("s", "r", "a"):
            raise CSTValidationError("Invalid f-string conversion.")

    def _visit_and_replace_children(
        self, visitor: CSTVisitor
    ) -> "FormattedStringExpression":
        format_spec = self.format_spec
        return FormattedStringExpression(
            whitespace_before_expression=visit_required(
                "whitespace_before_expression",
                self.whitespace_before_expression,
                visitor,
            ),
            expression=visit_required("expression", self.expression, visitor),
            whitespace_after_expression=visit_required(
                "whitespace_after_expression", self.whitespace_after_expression, visitor
            ),
            conversion=self.conversion,
            format_spec=(
                visit_sequence("format_spec", format_spec, visitor)
                if format_spec is not None
                else None
            ),
        )

    def _codegen(self, state: CodegenState) -> None:
        state.tokens.append("{")
        self.whitespace_before_expression._codegen(state)
        self.expression._codegen(state)
        self.whitespace_after_expression._codegen(state)
        conversion = self.conversion
        if conversion is not None:
            state.tokens.append("!")
            state.tokens.append(conversion)
        format_spec = self.format_spec
        if format_spec is not None:
            state.tokens.append(":")
            for spec in format_spec:
                spec._codegen(state)
        state.tokens.append("}")


@add_slots
@dataclass(frozen=True)
class FormattedString(BaseString):
    # Sequence of formatted string parts
    parts: Sequence[BaseFormattedStringContent]

    # String start indicator
    start: str = 'f"'

    # String end indicator
    end: str = '"'

    # Sequence of open parenthesis for precidence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precidence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        super(FormattedString, self)._validate()

        # Validate any prefix
        prefix = self._get_prefix()
        if prefix not in ("f", "fr", "rf"):
            raise CSTValidationError("Invalid f-string prefix.")

        # Validate wrapping quotes
        starttoken = self.start[len(prefix) :]
        if starttoken != self.end:
            raise CSTValidationError("f-string must have matching enclosing quotes.")

        # Validate valid wrapping quote usage
        if starttoken not in ('"', "'", '"""', "'''"):
            raise CSTValidationError("Invalid f-string enclosing quotes.")

    def _get_prefix(self) -> str:
        prefix = ""
        for c in self.start:
            if c in ['"', "'"]:
                break
            prefix += c
        return prefix.lower()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "FormattedString":
        return FormattedString(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            start=self.start,
            parts=visit_sequence("parts", self.parts, visitor),
            end=self.end,
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append(self.start)
            for part in self.parts:
                part._codegen(state)
            state.tokens.append(self.end)


@add_slots
@dataclass(frozen=True)
class ConcatenatedString(BaseString):
    # String on the left of the concatenation.
    left: Union[SimpleString, FormattedString]

    # String on the right of the concatenation.
    right: Union[SimpleString, FormattedString, "ConcatenatedString"]

    # Sequence of open parenthesis for precidence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precidence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace between strings.
    whitespace_between: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _validate(self) -> None:
        super(ConcatenatedString, self)._validate()

        # Strings that are concatenated cannot have parens.
        if bool(self.left.lpar) or bool(self.left.rpar):
            raise CSTValidationError("Cannot concatenate parenthesized strings.")
        if bool(self.right.lpar) or bool(self.right.rpar):
            raise CSTValidationError("Cannot concatenate parenthesized strings.")

        # Cannot concatenate str and bytes
        leftbytes = "b" in self.left._get_prefix()
        if isinstance(self.right, ConcatenatedString):
            rightbytes = "b" in self.right.left._get_prefix()
        elif isinstance(self.right, SimpleString):
            rightbytes = "b" in self.right._get_prefix()
        elif isinstance(self.right, FormattedString):
            rightbytes = "b" in self.right._get_prefix()
        else:
            raise Exception("Logic error!")
        if leftbytes != rightbytes:
            raise CSTValidationError("Cannot concatenate string and bytes.")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "ConcatenatedString":
        return ConcatenatedString(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            left=visit_required("left", self.left, visitor),
            whitespace_between=visit_required(
                "whitespace_between", self.whitespace_between, visitor
            ),
            right=visit_required("right", self.right, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.left._codegen(state)
            self.whitespace_between._codegen(state)
            self.right._codegen(state)


@add_slots
@dataclass(frozen=True)
class Starred(BaseAssignTargetExpression):
    # The actual expression
    expression: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace nodes
    whitespace_after_star: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Starred":
        return Starred(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            whitespace_after_star=visit_required(
                "whitespace_after_star", self.whitespace_after_star, visitor
            ),
            expression=visit_required("expression", self.expression, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append("*")
            self.whitespace_after_star._codegen(state)
            self.expression._codegen(state)


@add_slots
@dataclass(frozen=True)
class ComparisonTarget(CSTNode):
    """
    A target for a comparison. Owns the comparison operator itself.
    """

    # The actual comparison operator
    operator: BaseCompOp

    # The right hand side of the comparison operation
    comparator: BaseExpression

    def _validate(self) -> None:
        # Validate operator spacing rules
        if (
            isinstance(self.operator, (In, NotIn, Is, IsNot))
            and self.operator.whitespace_after.empty
            and not self.comparator._safe_to_use_with_word_operator(
                ExpressionPosition.RIGHT
            )
        ):
            raise CSTValidationError(
                "Must have at least one space around comparison operator."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "ComparisonTarget":
        return ComparisonTarget(
            operator=visit_required("operator", self.operator, visitor),
            comparator=visit_required("comparator", self.comparator, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        self.operator._codegen(state)
        self.comparator._codegen(state)


@add_slots
@dataclass(frozen=True)
class Comparison(BaseExpression):
    """
    Any comparison such as "x < y < z"
    """

    # The left hand side of the comparison operation
    left: BaseExpression

    # The actual comparison operator
    comparisons: Sequence[ComparisonTarget]

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        # Perform any validation on base type
        super(Comparison, self)._validate()

        if len(self.comparisons) == 0:
            raise CSTValidationError("Must have at least one ComparisonTarget.")

        # Validate operator spacing rules
        operator = self.comparisons[0].operator
        if (
            isinstance(operator, (In, NotIn, Is, IsNot))
            and operator.whitespace_before.empty
            and not self.left._safe_to_use_with_word_operator(ExpressionPosition.LEFT)
        ):
            raise CSTValidationError(
                "Must have at least one space around comparison operator."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Comparison":
        return Comparison(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            left=visit_required("left", self.left, visitor),
            comparisons=visit_sequence("comparisons", self.comparisons, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.left._codegen(state)
            for comp in self.comparisons:
                comp._codegen(state)


@add_slots
@dataclass(frozen=True)
class UnaryOperation(BaseExpression):
    """
    Any generic unary expression, such as "not x" or "-x". Note that this node
    does not get used for immediate number negation such as "-5". For that,
    the Number class is used.
    """

    # The unary operator applied to the expression
    operator: BaseUnaryOp

    # The actual expression or atom
    expression: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        # Perform any validation on base type
        super(UnaryOperation, self)._validate()

        if (
            isinstance(self.operator, Not)
            and self.operator.whitespace_after.empty
            and not self.expression._safe_to_use_with_word_operator(
                ExpressionPosition.RIGHT
            )
        ):
            raise CSTValidationError("Must have at least one space after not operator.")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "UnaryOperation":
        return UnaryOperation(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            operator=visit_required("operator", self.operator, visitor),
            expression=visit_required("expression", self.expression, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.operator._codegen(state)
            self.expression._codegen(state)


@add_slots
@dataclass(frozen=True)
class BinaryOperation(BaseExpression):
    """
    Any binary operation such as "x << y" or "y + z".
    """

    # The left hand side of the operation
    left: BaseExpression

    # The actual operator
    operator: BaseBinaryOp

    # The right hand side of the operation
    right: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "BinaryOperation":
        return BinaryOperation(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            left=visit_required("left", self.left, visitor),
            operator=visit_required("operator", self.operator, visitor),
            right=visit_required("right", self.right, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.left._codegen(state)
            self.operator._codegen(state)
            self.right._codegen(state)


@add_slots
@dataclass(frozen=True)
class BooleanOperation(BaseExpression):
    """
    Any boolean operation such as "x or y" or "z and w"
    """

    # The left hand side of the operation
    left: BaseExpression

    # The actual operator
    operator: BaseBooleanOp

    # The right hand side of the operation
    right: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _validate(self) -> None:
        # Paren validation and such
        super(BooleanOperation, self)._validate()
        # Validate spacing rules
        if (
            self.operator.whitespace_before.empty
            and not self.left._safe_to_use_with_word_operator(ExpressionPosition.LEFT)
        ):
            raise CSTValidationError(
                "Must have at least one space around boolean operator."
            )
        if (
            self.operator.whitespace_after.empty
            and not self.right._safe_to_use_with_word_operator(ExpressionPosition.RIGHT)
        ):
            raise CSTValidationError(
                "Must have at least one space around boolean operator."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "BooleanOperation":
        return BooleanOperation(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            left=visit_required("left", self.left, visitor),
            operator=visit_required("operator", self.operator, visitor),
            right=visit_required("right", self.right, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.left._codegen(state)
            self.operator._codegen(state)
            self.right._codegen(state)


@dataclass(frozen=True)
class Attribute(BaseAssignTargetExpression, BaseDelTargetExpression):
    """
    An attribute reference, such as "x.y". Note that in the case of
    "x.y.z", the outer attribute will have an attr of "z" and the
    value will be another Attribute referencing the "y" attribute on
    "x".
    """

    # Expression which, when evaluated, will have 'attr' as an attribute
    value: BaseExpression

    # Name of the attribute being accessed.
    attr: Name

    # Separating dot, with any whitespace it owns.
    dot: Dot = Dot()

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Attribute":
        return Attribute(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=visit_required("value", self.value, visitor),
            dot=visit_required("dot", self.dot, visitor),
            attr=visit_required("attr", self.attr, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.value._codegen(state)
            self.dot._codegen(state)
            self.attr._codegen(state)


@add_slots
@dataclass(frozen=True)
class Index(CSTNode):
    """
    Any index as passed to a subscript.
    """

    # The index value itself.
    value: BaseExpression

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Index":
        return Index(value=visit_required("value", self.value, visitor))

    def _codegen(self, state: CodegenState) -> None:
        self.value._codegen(state)


@add_slots
@dataclass(frozen=True)
class Slice(CSTNode):
    """
    Any slice operation in a subscript, such as "1:", "2:3:4", etc. Note
    that the grammar does NOT allow parenthesis around a slice so they
    are not supported here.
    """

    # The lower bound in the slice, if present
    lower: Optional[BaseExpression]

    # The upper bound in the slice, if present
    upper: Optional[BaseExpression]

    # The step in the slice, if present
    step: Optional[BaseExpression] = None

    # The first slice operator
    first_colon: Colon = Colon()

    # The second slice operator, usually omitted
    second_colon: Union[Colon, MaybeSentinel] = MaybeSentinel.DEFAULT

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Slice":
        return Slice(
            lower=visit_optional("lower", self.lower, visitor),
            first_colon=visit_required("first_colon", self.first_colon, visitor),
            upper=visit_optional("upper", self.upper, visitor),
            second_colon=visit_sentinel("second_colon", self.second_colon, visitor),
            step=visit_optional("step", self.step, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        lower = self.lower
        if lower is not None:
            lower._codegen(state)
        self.first_colon._codegen(state)
        upper = self.upper
        if upper is not None:
            upper._codegen(state)
        second_colon = self.second_colon
        if second_colon is MaybeSentinel.DEFAULT and self.step is not None:
            state.tokens.append(":")
        elif isinstance(second_colon, Colon):
            second_colon._codegen(state)
        step = self.step
        if step is not None:
            step._codegen(state)


@dataclass(frozen=True)
class ExtSlice(CSTNode):
    """
    A list of slices, such as "1:2, 3". Not used in the stdlib but still
    valid. This also does not allow for wrapping parenthesis.
    "x".
    """

    # A slice or index that is part of the extslice.
    slice: Union[Index, Slice]

    # Separating comma, with any whitespace it owns.
    comma: Union[Comma, MaybeSentinel] = MaybeSentinel.DEFAULT

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "ExtSlice":
        return ExtSlice(
            slice=visit_required("slice", self.slice, visitor),
            comma=visit_sentinel("comma", self.comma, visitor),
        )

    def _codegen(self, state: CodegenState, default_comma: bool = False) -> None:
        self.slice._codegen(state)
        comma = self.comma
        if comma is MaybeSentinel.DEFAULT and default_comma:
            state.tokens.append(", ")
        elif isinstance(comma, Comma):
            comma._codegen(state)


@dataclass(frozen=True)
class Subscript(BaseAssignTargetExpression, BaseDelTargetExpression):
    """
    A subscript reference such as "x[2]".
    """

    # Expression which, when evaluated, will be subscripted.
    value: BaseExpression

    # Subscript to take on the value.
    slice: Union[Index, Slice, Sequence[ExtSlice]]

    # Open bracket surrounding the slice
    lbracket: LeftSquareBracket = LeftSquareBracket()

    # Close bracket surrounding the slice
    rbracket: RightSquareBracket = RightSquareBracket()

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace
    whitespace_after_value: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _validate(self) -> None:
        super(Subscript, self)._validate()
        if isinstance(self.slice, Sequence):
            # Validate valid commas
            if len(self.slice) < 1:
                raise CSTValidationError("Cannot have empty ExtSlice.")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Subscript":
        slice = self.slice
        return Subscript(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            value=visit_required("value", self.value, visitor),
            whitespace_after_value=visit_required(
                "whitespace_after_value", self.whitespace_after_value, visitor
            ),
            lbracket=visit_required("lbracket", self.lbracket, visitor),
            slice=visit_required("slice", slice, visitor)
            if isinstance(slice, (Index, Slice))
            else visit_sequence("slice", slice, visitor),
            rbracket=visit_required("rbracket", self.rbracket, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.value._codegen(state)
            self.whitespace_after_value._codegen(state)
            self.lbracket._codegen(state)
            if isinstance(self.slice, (Index, Slice)):
                self.slice._codegen(state)
            elif isinstance(self.slice, Sequence):
                lastslice = len(self.slice) - 1
                for i, slice in enumerate(self.slice):
                    slice._codegen(state, default_comma=(i != lastslice))
            else:
                # We can make pyre happy this way!
                raise Exception("Logic error!")
            self.rbracket._codegen(state)


@dataclass(frozen=True)
class Annotation(CSTNode):
    """
    An annotation.
    """

    # The annotation itself.
    annotation: Union[Name, Attribute, BaseString, Subscript]

    # The indicator token before the annotation.
    indicator: Union[
        str, AnnotationIndicatorSentinel
    ] = AnnotationIndicatorSentinel.DEFAULT

    # Whitespace
    whitespace_before_indicator: Union[
        BaseParenthesizableWhitespace, MaybeSentinel
    ] = MaybeSentinel.DEFAULT
    whitespace_after_indicator: BaseParenthesizableWhitespace = SimpleWhitespace(" ")

    def _validate(self) -> None:
        if isinstance(self.indicator, str) and self.indicator not in [":", "->"]:
            raise CSTValidationError(
                "An Annotation indicator must be one of ':', '->'."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Annotation":
        return Annotation(
            whitespace_before_indicator=visit_sentinel(
                "whitespace_before_indicator", self.whitespace_before_indicator, visitor
            ),
            indicator=self.indicator,
            whitespace_after_indicator=visit_required(
                "whitespace_after_indicator", self.whitespace_after_indicator, visitor
            ),
            annotation=visit_required("annotation", self.annotation, visitor),
        )

    def _codegen(
        self, state: CodegenState, default_indicator: Optional[str] = None
    ) -> None:
        # First, figure out the indicator which tells us default whitespace.
        indicator = self.indicator
        if isinstance(indicator, AnnotationIndicatorSentinel):
            if default_indicator is None:
                raise CSTCodegenError(
                    "Must specify a concrete default_indicator if default used on indicator."
                )
            indicator = default_indicator

        # Now, output the whitespace
        whitespace_before_indicator = self.whitespace_before_indicator
        if isinstance(whitespace_before_indicator, BaseParenthesizableWhitespace):
            whitespace_before_indicator._codegen(state)
        elif isinstance(whitespace_before_indicator, MaybeSentinel):
            if indicator == "->":
                state.tokens.append(" ")
        else:
            raise Exception("Logic error!")

        # Now, output the indicator and the rest of the annotation
        state.tokens.append(indicator)
        self.whitespace_after_indicator._codegen(state)
        self.annotation._codegen(state)


@dataclass(frozen=True)
class ParamStar(CSTNode):
    """
    A sentinel indicator on a Parameter list to denote that the following params
    are kwonly args.
    """

    # Comma that comes after the star.
    comma: Comma = Comma(whitespace_after=SimpleWhitespace(" "))

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "ParamStar":
        return ParamStar(comma=visit_required("comma", self.comma, visitor))

    def _codegen(self, state: CodegenState) -> None:
        state.tokens.append("*")
        self.comma._codegen(state)


@add_slots
@dataclass(frozen=True)
class Param(CSTNode):
    """
    A single parameter in a Parameter list. May contain a type annotation and
    in some cases a default.
    """

    # The parameter name itself
    name: Name

    # Any optional annotation
    annotation: Optional[Annotation] = None

    # The equals sign used to denote assignment if there is a default.
    equal: Union[AssignEqual, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Any optional default
    default: Optional[BaseExpression] = None

    # Any trailing comma
    comma: Union[Comma, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Optional star appearing before name for star_arg and star_kwarg
    star: Union[str, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Whitespace
    whitespace_after_star: BaseParenthesizableWhitespace = SimpleWhitespace("")
    whitespace_after_param: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _validate(self) -> None:
        if self.default is None and isinstance(self.equal, AssignEqual):
            raise CSTValidationError(
                "Must have a default when specifying an AssignEqual."
            )
        if isinstance(self.star, str) and self.star not in ("", "*", "**"):
            raise CSTValidationError("Must specify either '', '*' or '**' for star.")
        if (
            self.annotation is not None
            and isinstance(self.annotation.indicator, str)
            and self.annotation.indicator != ":"
        ):
            raise CSTValidationError("A param Annotation must be denoted with a ':'.")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Param":
        return Param(
            star=self.star,
            whitespace_after_star=visit_required(
                "whitespace_after_star", self.whitespace_after_star, visitor
            ),
            name=visit_required("name", self.name, visitor),
            annotation=visit_optional("annotation", self.annotation, visitor),
            equal=visit_sentinel("equal", self.equal, visitor),
            default=visit_optional("default", self.default, visitor),
            comma=visit_sentinel("comma", self.comma, visitor),
            whitespace_after_param=visit_required(
                "whitespace_after_param", self.whitespace_after_param, visitor
            ),
        )

    def _codegen(
        self,
        state: CodegenState,
        default_star: Optional[str] = None,
        default_comma: bool = False,
    ) -> None:
        star = self.star
        if isinstance(star, MaybeSentinel):
            if default_star is None:
                raise CSTCodegenError(
                    "Must specify a concrete default_star if default used on star."
                )
            star = default_star
        if isinstance(star, str):
            state.tokens.append(star)
        self.whitespace_after_star._codegen(state)
        self.name._codegen(state)
        annotation = self.annotation
        if annotation is not None:
            annotation._codegen(state, default_indicator=":")
        equal = self.equal
        if equal is MaybeSentinel.DEFAULT and self.default is not None:
            state.tokens.append(" = ")
        elif isinstance(equal, AssignEqual):
            equal._codegen(state)
        default = self.default
        if default is not None:
            default._codegen(state)
        comma = self.comma
        if comma is MaybeSentinel.DEFAULT and default_comma:
            state.tokens.append(", ")
        elif isinstance(comma, Comma):
            comma._codegen(state)
        self.whitespace_after_param._codegen(state)


@add_slots
@dataclass(frozen=True)
class Parameters(CSTNode):
    """
    A function or lambda parameter list.
    """

    # Positional parameters.
    params: Sequence[Param] = ()

    # Positional parameters with defaults.
    default_params: Sequence[Param] = ()

    # Optional parameter that captures unspecified positional arguments or a sentinel
    # star that dictates parameters following are kwonly args.
    star_arg: Union[Param, ParamStar, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Keyword-only params that may or may not have defaults.
    kwonly_params: Sequence[Param] = ()

    # Optional parameter that captures unspecified kwargs.
    star_kwarg: Optional[Param] = None

    def _validate_stars_sequence(self, vals: Sequence[Param], *, section: str) -> None:
        if len(vals) == 0:
            return
        for val in vals:
            if isinstance(val.star, str) and val.star != "":
                raise CSTValidationError(
                    f"Expecting a star prefix of '' for {section} Param."
                )

    def _validate_kwonlystar(self) -> None:
        if isinstance(self.star_arg, ParamStar) and len(self.kwonly_params) == 0:
            raise CSTValidationError(
                "Must have at least one kwonly param if ParamStar is used."
            )

    def _validate_defaults(self) -> None:
        for param in self.params:
            if param.default is not None:
                raise CSTValidationError(
                    "Cannot have defaults for params. Place them in default_params."
                )
        for param in self.default_params:
            if param.default is None:
                raise CSTValidationError(
                    "Must have defaults for default_params. Place non-defaults in params."
                )
        if isinstance(self.star_arg, Param) and self.star_arg.default is not None:
            raise CSTValidationError("Cannot have default for star_arg.")
        if self.star_kwarg is not None and self.star_kwarg.default is not None:
            raise CSTValidationError("Cannot have default for star_kwarg.")

    def _validate_stars(self) -> None:
        if len(self.params) > 0:
            self._validate_stars_sequence(self.params, section="params")
        if len(self.default_params) > 0:
            self._validate_stars_sequence(self.default_params, section="default_params")
        star_arg = self.star_arg
        if (
            isinstance(star_arg, Param)
            and isinstance(star_arg.star, str)
            and star_arg.star != "*"
        ):
            raise CSTValidationError(
                "Expecting a star prefix of '*' for star_arg Param."
            )
        if len(self.kwonly_params) > 0:
            self._validate_stars_sequence(self.kwonly_params, section="kwonly_params")
        star_kwarg = self.star_kwarg
        if (
            star_kwarg is not None
            and isinstance(star_kwarg.star, str)
            and star_kwarg.star != "**"
        ):
            raise CSTValidationError(
                "Expecting a star prefix of '**' for star_kwarg Param."
            )

    def _validate(self) -> None:
        # Validate kwonly_param star placement semantics.
        self._validate_kwonlystar()
        # Validate defaults semantics for params, default_params and star_arg/star_kwarg.
        self._validate_defaults()
        # Validate that we don't have random stars on non star_kwarg.
        self._validate_stars()

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Parameters":
        return Parameters(
            params=visit_sequence("params", self.params, visitor),
            default_params=visit_sequence(
                "default_params", self.default_params, visitor
            ),
            star_arg=visit_sentinel("star_arg", self.star_arg, visitor),
            kwonly_params=visit_sequence("kwonly_params", self.kwonly_params, visitor),
            star_kwarg=visit_optional("star_kwarg", self.star_kwarg, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        # Compute the star existence first so we can ask about whether
        # each element is the last in the list or not.
        star_arg = self.star_arg
        if isinstance(star_arg, MaybeSentinel):
            starincluded = len(self.kwonly_params) > 0
        elif isinstance(star_arg, (Param, ParamStar)):
            starincluded = True
        else:
            starincluded = False
        # Render out the params first, computing necessary trailing commas.
        lastparam = len(self.params) - 1
        more_values = (
            len(self.default_params) > 0
            or starincluded
            or len(self.kwonly_params) > 0
            or self.star_kwarg is not None
        )
        for i, param in enumerate(self.params):
            param._codegen(
                state, default_star="", default_comma=(i < lastparam or more_values)
            )
        # Render out the default_params next, computing necessary trailing commas.
        lastparam = len(self.default_params) - 1
        more_values = (
            starincluded or len(self.kwonly_params) > 0 or self.star_kwarg is not None
        )
        for i, param in enumerate(self.default_params):
            param._codegen(
                state, default_star="", default_comma=(i < lastparam or more_values)
            )
        # Render out optional star sentinel if its explicitly included or
        # if we are inferring it from kwonly_params. Otherwise, render out the
        # optional star_arg.
        if isinstance(star_arg, MaybeSentinel):
            if starincluded:
                state.tokens.append("*, ")
        elif isinstance(star_arg, Param):
            more_values = len(self.kwonly_params) > 0 or self.star_kwarg is not None
            star_arg._codegen(state, default_star="*", default_comma=more_values)
        elif isinstance(star_arg, ParamStar):
            star_arg._codegen(state)
        # Render out the kwonly_args next, computing necessary trailing commas.
        lastparam = len(self.kwonly_params) - 1
        more_values = self.star_kwarg is not None
        for i, param in enumerate(self.kwonly_params):
            param._codegen(
                state, default_star="", default_comma=(i < lastparam or more_values)
            )
        # Finally, render out any optional star_kwarg
        star_kwarg = self.star_kwarg
        if star_kwarg is not None:
            star_kwarg._codegen(state, default_star="**", default_comma=False)


@add_slots
@dataclass(frozen=True)
class Lambda(BaseExpression):
    # The parameters to the lambda
    params: Parameters

    # The body of the lambda
    body: BaseExpression

    # The colon separating the parameters from the body
    colon: Colon = Colon(whitespace_after=SimpleWhitespace(" "))

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace
    whitespace_after_lambda: Union[
        BaseParenthesizableWhitespace, MaybeSentinel
    ] = MaybeSentinel.DEFAULT

    def _validate(self) -> None:
        # Validate parents
        super(Lambda, self)._validate()
        # Sum up all parameters
        all_params: List[Param] = [
            *self.params.params,
            *self.params.default_params,
            *self.params.kwonly_params,
        ]
        if isinstance(self.params.star_arg, Param):
            all_params.append(self.params.star_arg)
        if self.params.star_kwarg is not None:
            all_params.append(self.params.star_kwarg)
        # Check for nonzero parameters because several checks care
        # about this.
        if len(all_params) > 0:
            for param in all_params:
                if param.annotation is not None:
                    raise CSTValidationError(
                        "Lambda params cannot have type annotations."
                    )
            if (
                isinstance(self.whitespace_after_lambda, BaseParenthesizableWhitespace)
                and self.whitespace_after_lambda.empty
            ):
                raise CSTValidationError(
                    "Must have at least one space after lambda when specifying params"
                )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Lambda":
        return Lambda(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            whitespace_after_lambda=visit_sentinel(
                "whitespace_after_lambda", self.whitespace_after_lambda, visitor
            ),
            params=visit_required("params", self.params, visitor),
            colon=visit_required("colon", self.colon, visitor),
            body=visit_required("body", self.body, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append("lambda")
            whitespace_after_lambda = self.whitespace_after_lambda
            if isinstance(whitespace_after_lambda, MaybeSentinel):
                if not (
                    len(self.params.params) == 0
                    and len(self.params.default_params) == 0
                    and not isinstance(self.params.star_arg, Param)
                    and len(self.params.kwonly_params) == 0
                    and self.params.star_kwarg is None
                ):
                    # We have one or more params, provide a space
                    state.tokens.append(" ")
            elif isinstance(whitespace_after_lambda, BaseParenthesizableWhitespace):
                whitespace_after_lambda._codegen(state)
            self.params._codegen(state)
            self.colon._codegen(state)
            self.body._codegen(state)


@add_slots
@dataclass(frozen=True)
class Arg(CSTNode):
    """
    A single argument to a Call. It may be a * or a ** expansion, or it may be in
    the form of "keyword=expression" for named arguments.
    """

    # The argument expression itself
    value: BaseExpression

    # Optional keyword for the argument
    keyword: Optional[Name] = None

    # The equals sign used to denote assignment if there is a keyword.
    equal: Union[AssignEqual, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Any trailing comma
    comma: Union[Comma, MaybeSentinel] = MaybeSentinel.DEFAULT

    # Optional star appearing before name for * and ** expansion
    star: Literal["", "*", "**"] = ""

    # Whitespace
    whitespace_after_star: BaseParenthesizableWhitespace = SimpleWhitespace("")
    whitespace_after_arg: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _validate(self) -> None:
        if self.keyword is None and isinstance(self.equal, AssignEqual):
            raise CSTValidationError(
                "Must have a keyword when specifying an AssignEqual."
            )
        if self.star not in ("", "*", "**"):
            raise CSTValidationError("Must specify either '', '*' or '**' for star.")
        if self.star in ("*", "**") and self.keyword is not None:
            raise CSTValidationError("Cannot specify a star and a keyword together.")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Arg":
        return Arg(
            star=self.star,
            whitespace_after_star=visit_required(
                "whitespace_after_star", self.whitespace_after_star, visitor
            ),
            keyword=visit_optional("keyword", self.keyword, visitor),
            equal=visit_sentinel("equal", self.equal, visitor),
            value=visit_required("value", self.value, visitor),
            comma=visit_sentinel("comma", self.comma, visitor),
            whitespace_after_arg=visit_required(
                "whitespace_after_arg", self.whitespace_after_arg, visitor
            ),
        )

    def _codegen(self, state: CodegenState, default_comma: bool = False) -> None:
        state.tokens.append(self.star)
        self.whitespace_after_star._codegen(state)
        keyword = self.keyword
        if keyword is not None:
            keyword._codegen(state)
        equal = self.equal
        if equal is MaybeSentinel.DEFAULT and self.keyword is not None:
            state.tokens.append(" = ")
        elif isinstance(equal, AssignEqual):
            equal._codegen(state)
        self.value._codegen(state)
        comma = self.comma
        if comma is MaybeSentinel.DEFAULT and default_comma:
            state.tokens.append(", ")
        elif isinstance(comma, Comma):
            comma._codegen(state)
        self.whitespace_after_arg._codegen(state)


class _BaseExpressionWithArgs(BaseExpression, ABC):
    """
    Arguments are complicated enough that we can't represent them easily
    in typing. So, we have common validation functions here.
    """

    # Sequence of arguments that will be passed to the functgion call
    args: Sequence[Arg] = ()  # TODO This can also be a single Generator.

    def _check_kwargs_or_keywords(
        self, arg: Arg
    ) -> Optional[Callable[[Arg], Callable]]:
        """
        Validates that we only have a mix of "keyword=arg" and "**arg" expansion.
        """

        if arg.keyword is not None:
            # Valid, keyword argument
            return None
        elif arg.star == "**":
            # Valid, kwargs
            return None
        elif arg.star == "*":
            # Invalid, cannot have "*" follow "**"
            raise CSTValidationError(
                "Cannot have iterable argument unpacking after keyword argument unpacking."
            )
        else:
            # Invalid, cannot have positional argument follow **/keyword
            raise CSTValidationError(
                "Cannot have positional argument after keyword argument unpacking."
            )

    def _check_starred_or_keywords(
        self, arg: Arg
    ) -> Optional[Callable[[Arg], Callable]]:
        """
        Validates that we only have a mix of "*arg" expansion and "keyword=arg".
        """

        if arg.keyword is not None:
            # Valid, keyword argument
            return None
        elif arg.star == "**":
            # Valid, but we now no longer allow "*" args
            # pyre-fixme[7]: Expected `Optional[Callable[[Arg], Callable[...,
            #  Any]]]` but got `Callable[[Arg], Optional[Callable[[Arg], Callable[...,
            #  Any]]]]`.
            return self._check_kwargs_or_keywords
        elif arg.star == "*":
            # Valid, iterable unpacking
            return None
        else:
            # Invalid, cannot have positional argument follow **/keyword
            raise CSTValidationError(
                "Cannot have positional argument after keyword argument."
            )

    def _check_positional(self, arg: Arg) -> Optional[Callable[[Arg], Callable]]:
        """
        Validates that we only have a mix of positional args and "*arg" expansion.
        """

        if arg.keyword is not None:
            # Valid, but this puts us into starred/keyword state
            # pyre-fixme[7]: Expected `Optional[Callable[[Arg], Callable[...,
            #  Any]]]` but got `Callable[[Arg], Optional[Callable[[Arg], Callable[...,
            #  Any]]]]`.
            return self._check_starred_or_keywords
        elif arg.star == "**":
            # Valid, but we skip states to kwargs/keywords
            # pyre-fixme[7]: Expected `Optional[Callable[[Arg], Callable[...,
            #  Any]]]` but got `Callable[[Arg], Optional[Callable[[Arg], Callable[...,
            #  Any]]]]`.
            return self._check_kwargs_or_keywords
        elif arg.star == "*":
            # Valid, iterator expansion
            return None
        else:
            # Valid, allowed to have positional arguments here
            return None

    def _validate(self) -> None:
        # Validate any super-class stuff, whatever it may be.
        super()._validate()
        # Now, validate the weird intermingling rules for arguments by running
        # a small validator state machine. This works by passing each argument
        # to a validator function which can either raise an exception if it
        # detects an invalid sequence, return a new validator to be used for the
        # next arg, or return None to use the same validator. We could enforce
        # always returning ourselves instead of None but it ends up making the
        # functions themselves less readable. In this way, the current validator
        # function encodes the state we're in (positional state, iterable
        # expansion state, or dictionary expansion state).
        validator = self._check_positional
        for arg in self.args:
            # pyre-fixme[29]: `Union[Callable[[Arg], Callable[..., Any]],
            #  Callable[..., Any]]` is not a function.
            validator = validator(arg) or validator


@add_slots
@dataclass(frozen=True)
class Call(_BaseExpressionWithArgs):
    # The expression resulting in a callable that we are to call
    func: Union[BaseAtom, Attribute, Subscript, "Call"]

    # The arguments to pass to the resulting callable
    args: Sequence[Arg] = ()  # TODO This can also be a single Generator.

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace nodes
    whitespace_after_func: BaseParenthesizableWhitespace = SimpleWhitespace("")
    whitespace_before_args: BaseParenthesizableWhitespace = SimpleWhitespace("")

    def _safe_to_use_with_word_operator(self, position: ExpressionPosition) -> bool:
        """
        Calls have a close paren on the right side regardless of whether they're
        parenthesized as a whole. As a result, they are safe to use directly against
        an adjacent node to the right.
        """
        if position == ExpressionPosition.LEFT:
            return True
        return super(Call, self)._safe_to_use_with_word_operator(position)

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Call":
        return Call(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            func=visit_required("func", self.func, visitor),
            whitespace_after_func=visit_required(
                "whitespace_after_func", self.whitespace_after_func, visitor
            ),
            whitespace_before_args=visit_required(
                "whitespace_before_args", self.whitespace_before_args, visitor
            ),
            args=visit_sequence("args", self.args, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.func._codegen(state)
            self.whitespace_after_func._codegen(state)
            state.tokens.append("(")
            self.whitespace_before_args._codegen(state)
            lastarg = len(self.args) - 1
            for i, arg in enumerate(self.args):
                arg._codegen(state, default_comma=(i != lastarg))
            state.tokens.append(")")


@add_slots
@dataclass(frozen=True)
class Await(BaseExpression):
    # The actual expression we need to await on
    expression: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace nodes
    whitespace_after_await: BaseParenthesizableWhitespace = SimpleWhitespace(" ")

    def _validate(self) -> None:
        # Validate any super-class stuff, whatever it may be.
        super(Await, self)._validate()
        # Make sure we don't run identifiers together.
        if self.whitespace_after_await.empty:
            raise CSTValidationError("Must have at least one space after await")

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Await":
        return Await(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            whitespace_after_await=visit_required(
                "whitespace_after_await", self.whitespace_after_await, visitor
            ),
            expression=visit_required("expression", self.expression, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append("await")
            self.whitespace_after_await._codegen(state)
            self.expression._codegen(state)


@add_slots
@dataclass(frozen=True)
class IfExp(BaseExpression):
    """
    An if expression similar to "body if test else orelse".
    """

    # The test to perform.
    test: BaseExpression

    # The expression to evaluate if the test is true.
    body: BaseExpression

    # The expression to evaluate if the test is false.
    orelse: BaseExpression

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace nodes
    whitespace_before_if: BaseParenthesizableWhitespace = SimpleWhitespace(" ")
    whitespace_after_if: BaseParenthesizableWhitespace = SimpleWhitespace(" ")
    whitespace_before_else: BaseParenthesizableWhitespace = SimpleWhitespace(" ")
    whitespace_after_else: BaseParenthesizableWhitespace = SimpleWhitespace(" ")

    def _validate(self) -> None:
        # Paren validation and such
        super(IfExp, self)._validate()
        # Validate spacing rules
        if (
            self.whitespace_before_if.empty
            and not self.body._safe_to_use_with_word_operator(ExpressionPosition.LEFT)
        ):
            raise CSTValidationError(
                "Must have at least one space before 'if' keyword."
            )
        if (
            self.whitespace_after_if.empty
            and not self.test._safe_to_use_with_word_operator(ExpressionPosition.RIGHT)
        ):
            raise CSTValidationError("Must have at least one space after 'if' keyword.")
        if (
            self.whitespace_before_else.empty
            and not self.test._safe_to_use_with_word_operator(ExpressionPosition.LEFT)
        ):
            raise CSTValidationError(
                "Must have at least one space before 'else' keyword."
            )
        if (
            self.whitespace_after_else.empty
            and not self.orelse._safe_to_use_with_word_operator(
                ExpressionPosition.RIGHT
            )
        ):
            raise CSTValidationError(
                "Must have at least one space after 'else' keyword."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "IfExp":
        return IfExp(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            body=visit_required("body", self.body, visitor),
            whitespace_before_if=visit_required(
                "whitespace_before_if", self.whitespace_before_if, visitor
            ),
            whitespace_after_if=visit_required(
                "whitespace_after_if", self.whitespace_after_if, visitor
            ),
            test=visit_required("test", self.test, visitor),
            whitespace_before_else=visit_required(
                "whitespace_before_else", self.whitespace_before_else, visitor
            ),
            whitespace_after_else=visit_required(
                "whitespace_after_else", self.whitespace_after_else, visitor
            ),
            orelse=visit_required("orelse", self.orelse, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            self.body._codegen(state)
            self.whitespace_before_if._codegen(state)
            state.tokens.append("if")
            self.whitespace_after_if._codegen(state)
            self.test._codegen(state)
            self.whitespace_before_else._codegen(state)
            state.tokens.append("else")
            self.whitespace_after_else._codegen(state)
            self.orelse._codegen(state)


@dataclass(frozen=True)
class From(CSTNode):
    """
    A 'from x' stanza in a Yield or Raise.
    """

    # Expression that we are yielding/raising from.
    item: BaseExpression

    whitespace_before_from: Union[
        BaseParenthesizableWhitespace, MaybeSentinel
    ] = MaybeSentinel.DEFAULT
    whitespace_after_from: BaseParenthesizableWhitespace = SimpleWhitespace(" ")

    def _validate(self) -> None:
        if (
            isinstance(self.whitespace_after_from, BaseParenthesizableWhitespace)
            and self.whitespace_after_from.empty
            and not self.item._safe_to_use_with_word_operator(ExpressionPosition.RIGHT)
        ):
            raise CSTValidationError(
                "Must have at least one space after 'from' keyword."
            )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "From":
        return From(
            whitespace_before_from=visit_sentinel(
                "whitespace_before_from", self.whitespace_before_from, visitor
            ),
            item=visit_required("item", self.item, visitor),
            whitespace_after_from=visit_required(
                "whitespace_after_from", self.whitespace_after_from, visitor
            ),
        )

    def _codegen(self, state: CodegenState, default_space: str = "") -> None:
        whitespace_before_from = self.whitespace_before_from
        if isinstance(whitespace_before_from, BaseParenthesizableWhitespace):
            whitespace_before_from._codegen(state)
        else:
            state.tokens.append(default_space)
        state.tokens.append("from")
        self.whitespace_after_from._codegen(state)
        self.item._codegen(state)


@add_slots
@dataclass(frozen=True)
class Yield(BaseExpression):
    """
    A yield expression similar to "yield x" or "yield from fun()"
    """

    # The test to perform.
    value: Optional[Union[BaseExpression, From]] = None

    # Sequence of open parenthesis for precedence dictation.
    lpar: Sequence[LeftParen] = ()

    # Sequence of close parenthesis for precedence dictation.
    rpar: Sequence[RightParen] = ()

    # Whitespace nodes
    whitespace_after_yield: Union[
        BaseParenthesizableWhitespace, MaybeSentinel
    ] = MaybeSentinel.DEFAULT

    def _validate(self) -> None:
        # Paren rules and such
        super(Yield, self)._validate()
        # Our own rules
        if (
            isinstance(self.whitespace_after_yield, BaseParenthesizableWhitespace)
            and self.whitespace_after_yield.empty
        ):
            if isinstance(self.value, From):
                raise CSTValidationError(
                    "Must have at least one space after 'yield' keyword."
                )
            if isinstance(
                self.value, BaseExpression
            ) and not self.value._safe_to_use_with_word_operator(
                ExpressionPosition.RIGHT
            ):
                raise CSTValidationError(
                    "Must have at least one space after 'yield' keyword."
                )

    def _visit_and_replace_children(self, visitor: CSTVisitor) -> "Yield":
        return Yield(
            lpar=visit_sequence("lpar", self.lpar, visitor),
            whitespace_after_yield=visit_sentinel(
                "whitespace_after_yield", self.whitespace_after_yield, visitor
            ),
            value=visit_optional("value", self.value, visitor),
            rpar=visit_sequence("rpar", self.rpar, visitor),
        )

    def _codegen(self, state: CodegenState) -> None:
        with self._parenthesize(state):
            state.tokens.append("yield")
            whitespace_after_yield = self.whitespace_after_yield
            if isinstance(whitespace_after_yield, BaseParenthesizableWhitespace):
                whitespace_after_yield._codegen(state)
            else:
                # Only need a space after yield if there is a value to yield.
                if self.value is not None:
                    state.tokens.append(" ")
            value = self.value
            if isinstance(value, From):
                value._codegen(state, default_space="")
            elif value is not None:
                value._codegen(state)