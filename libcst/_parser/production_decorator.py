# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict
from typing import Callable, Iterable, Optional, TypeVar

from libcst._parser.types.conversions import NonterminalConversion
from libcst._parser.types.production import Production


_NonterminalConversionT = TypeVar(
    "_NonterminalConversionT", bound=NonterminalConversion
)


# We could version our grammar at a later point by adding a version metadata kwarg to
# this decorator.
def with_production(
    production_name: str, children: str, *, version: Optional[str] = None
) -> Callable[[_NonterminalConversionT], _NonterminalConversionT]:
    """
    Attaches a bit of grammar to a conversion function. The parser extracts all of these
    production strings, and uses it to form the language's full grammar.

    If you need to attach multiple productions to the same conversion function
    """

    def inner(fn: _NonterminalConversionT) -> _NonterminalConversionT:
        if not hasattr(fn, "productions"):
            fn.productions = []
        # pyre-fixme[16]: `Callable[[ParserConfig, Sequence[Any]], Any]` has no attri...
        fn_name = fn.__name__
        if not fn_name.startswith("convert_"):
            raise Exception(
                "A function with a production must be named 'convert_X', not "
                + f"'{fn_name}'."
            )
        # pyre-fixme[16]: Pyre doesn't know about this magic field we added
        fn.productions.append(Production(production_name, children, version))
        return fn

    return inner


def get_productions(fn: NonterminalConversion) -> Iterable[Production]:
    return fn.productions
