.. _libcst-metadata:

========
Metadata
========

-------------
Metadata APIs
-------------

LibCST ships with a metadata interface that defines a standardized way to
associate nodes in a CST with arbitrary metadata while maintaining the immutability
of the tree. The metadata interface is designed to be declarative and type safe.
Here's a quick example of using the metadata interface to get line and column
numbers of nodes through the :class:`~libcst.SyntacticPositionProvider`:

.. _libcst-metadata-position-example:
.. code-block:: python

    class NamePrinter(cst.CSTVisitor):
        METADATA_DEPENDENCIES = (cst.SyntacticPositionProvider,)

        def visit_Name(self, node: cst.Name) -> None:
            pos = self.get_metadata(cst.SyntacticPositionProvider, node).start
            print(f"{node.value} found at line {pos.line}, column {pos.column}")

    wrapper = cst.MetadataWrapper(cst.parse_module("x = 1"))
    result = wrapper.visit(NamePrinter())  # should print "x found at line 1, column 0"

More examples of using the metadata interface can be found on the
:doc:`Metadata Tutorial <metadata_tutorial>`.

Accessing Metadata
------------------

To work with metadata you need to wrap a module with a :class:`~libcst.MetadataWrapper`.
The wrapper provides a :func:`~libcst.MetadataWrapper.resolve` function and a
:func:`~libcst.MetadataWrapper.resolve_many` function to generate metadata.

.. autoclass:: libcst.MetadataWrapper

If you're working with visitors, which extend :class:`~libcst.MetadataDependent`, 
metadata dependencies will be automatically computed when visited by a 
:class:`~libcst.MetadataWrapper` and are accessible through
:func:`~libcst.MetadataDependent.get_metadata`

.. autoclass:: libcst.MetadataDependent

Providing Metadata
------------------

Metadata is generated through provider classes that can be declared as a dependency
by a subclass of :class:`~libcst.MetadataDependent`. These providers are then
resolved automatically using methods provided by :class:`~libcst.MetadataWrapper`.
In most cases, you should extend :class:`~libcst.BatchableMetadataProvider` when
writing a provider, unless you have a particular reason to not to use a
batchable visitor. Only extend from :class:`~libcst.BaseMetadataProvider` if
your provider does not use the visitor pattern for computing metadata for a tree.

.. autoclass:: libcst.BaseMetadataProvider
.. autoclass:: libcst.BatchableMetadataProvider
.. autoclass:: libcst.VisitorMetadataProvider

.. _libcst-metadata-position:

------------------
Metadata Providers
------------------
:class:`~libcst.metadata.BasicPositionProvider`, :class:`~libcst.metadata.SyntacticPositionProvider`,
:class:`~libcst.metadata.ExpressionContextProvider` and :class:`~libcst.metadata.ScopeProvider`
are currently provided. Each metadata provider may has its own custom data structure.

Position Metadata
-----------------

Position (line and column numbers) metadata are accessible through the metadata
interface by declaring the one of the following providers as a dependency. For
most cases, :class:`~libcst.SyntacticPositionProvider` is what you probably want.
Accessing position metadata through the :class:`~libcst.MetadataDepedent`
interface will return a :class:`~libcst.CodeRange` object. See
:ref:`the above example<libcst-metadata-position-example>`.

.. autoclass:: libcst.metadata.BasicPositionProvider
.. autoclass:: libcst.metadata.SyntacticPositionProvider

.. autoclass:: libcst.CodeRange
.. autoclass:: libcst.CodePosition


Expression Context Metadata
---------------------------
.. autoclass:: libcst.metadata.ExpressionContextProvider
   :no-undoc-members:

.. autoclass:: libcst.metadata.ExpressionContext

Scope Metadata
--------------
Scope is the block of naming binding. The bind name is not available
after existing the bind block. Python is
`function-scoped <https://en.wikipedia.org/wiki/Scope_(computer_science)#Function_scope>`_.
New scopes are created for classes and functions, but not other block constructs like
conditional statements, loops, or try…except, don't create their own scope.
In this example, the scopes of each name assignments and class/function definitions are
visualized:

.. image:: _static/img/python_scopes.png
   :alt: LibCST

There were four different type of scope in Python: :class:`~libcst.metadata.GlobalScope`,
:class:`~libcst.metadata.ClassScope`, :class:`~libcst.metadata.FunctionScope` and
:class:`~libcst.metadata.ComprehensionScope`.

.. autoclass:: libcst.metadata.ScopeProvider
   :no-undoc-members:

.. autoclass:: libcst.metadata.BaseAssignment
   :no-undoc-members:

.. autoclass:: libcst.metadata.Access
.. autoclass:: libcst.metadata.Assignment
.. autoclass:: libcst.metadata.BuiltinAssignment


.. autoclass:: libcst.metadata.Scope
   :no-undoc-members:

.. autoclass:: libcst.metadata.GlobalScope
   :no-undoc-members:

.. autoclass:: libcst.metadata.FunctionScope
.. autoclass:: libcst.metadata.ClassScope
.. autoclass:: libcst.metadata.ComprehensionScope
