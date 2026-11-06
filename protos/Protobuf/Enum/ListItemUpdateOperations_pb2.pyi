from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from typing import ClassVar as _ClassVar

DESCRIPTOR: _descriptor.FileDescriptor

class ListItemUpdateOperations(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UnspecifiedOperation: _ClassVar[ListItemUpdateOperations]
    Add: _ClassVar[ListItemUpdateOperations]
    Update: _ClassVar[ListItemUpdateOperations]
    Remove: _ClassVar[ListItemUpdateOperations]
UnspecifiedOperation: ListItemUpdateOperations
Add: ListItemUpdateOperations
Update: ListItemUpdateOperations
Remove: ListItemUpdateOperations
