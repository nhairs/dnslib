"""
    DNSLabel/DNSBuffer - DNS label handling & encoding/decoding
"""


import fnmatch
import re
import string
import sys
from typing import List, Tuple, Dict, Union

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from dnslib.bit import get_bits, set_bits
from dnslib.buffer import Buffer, BufferError

# In theory valid label characters should be letters,digits,hyphen,underscore (LDH)
# LDH = set(bytearray(b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'))
# For compatibility we only escape non-printable characters
LDH = set(range(33, 127))
ESCAPE = re.compile(r"\\([0-9][0-9][0-9])")


class DNSLabelError(Exception):
    """Exceptions relating to DNS Labels"""

    pass


class DNSLabel:
    """Container for DNS label (aka domain)

    Supports IDNA encoding for unicode domain names

    ```pycon
    >>> l1 = DNSLabel("aaa.bbb.ccc.")
    >>> l2 = DNSLabel([b"aaa",b"bbb",b"ccc"])
    >>> l1 == l2
    True
    >>> l3 = DNSLabel("AAA.BBB.CCC")
    >>> l1 == l3
    True
    >>> l1 == 'AAA.BBB.CCC'
    True
    >>> x = { l1 : 1 }
    >>> x[l1]
    1
    >>> l1
    <DNSLabel: 'aaa.bbb.ccc.'>
    >>> str(l1)
    'aaa.bbb.ccc.'
    >>> l3 = l1.add("xxx.yyy")
    >>> l3
    <DNSLabel: 'xxx.yyy.aaa.bbb.ccc.'>
    >>> l3.matchSuffix(l1)
    True
    >>> l3.matchSuffix("xxx.yyy.")
    False
    >>> l3.matchSuffix("Bbb.ccc.")
    True
    >>> l3.stripSuffix("bbb.ccc.")
    <DNSLabel: 'xxx.yyy.aaa.'>
    >>> l3.matchGlob("*.[abc]aa.BBB.ccc")
    True
    >>> l3.matchGlob("*.[abc]xx.bbb.ccc")
    False
    >>> u1 = DNSLabel("⊕.com")
    >>> str(u1) == "xn--keh.com."
    True
    >>> u1.idna == "⊕.com."
    True
    >>> u1.label == ( b"xn--keh", b"com" )
    True

    ```
    """

    label: Tuple[bytes, ...]

    def __init__(self, label: "DNSLabelCreateTypes") -> None:
        """
        Args:
            label: Label can be specified as:
                - a list/tuple of byte strings
                - a byte string (split into components separated by b'.')
                - a unicode string which will be encoded according to RFC3490/IDNA
        """
        if isinstance(label, DNSLabel):
            self.label = label.label
        elif isinstance(label, (list, tuple)):
            self.label = tuple(label)
        elif not label or label in (b".", "."):
            self.label = ()
        elif isinstance(label, str):
            # This substitution is from when dnslib supported python 2 and 3.
            # It is unclear if it is still needed (there are no relevant test
            # cases), so we leave it in here.
            label = ESCAPE.sub(lambda m: chr(int(m[1])), label)
            self.label = tuple(label.encode("idna").rstrip(b".").split(b"."))
        else:
            self.label = tuple(label.rstrip(b".").split(b"."))
        return

    def add(self, name: "DNSLabelCreateTypes") -> "DNSLabel":
        """Prepend name to label

        Args:
            name: name to prepend

        Returns:
            new `DNSLabel`
        """
        new = DNSLabel(name)
        if self.label:
            new.label += self.label
        return new

    def matchGlob(self, pattern: "DNSLabelCreateTypes") -> bool:
        if type(pattern) != DNSLabel:
            pattern = DNSLabel(pattern)
        return fnmatch.fnmatch(str(self).lower(), str(pattern).lower())

    def matchSuffix(self, suffix):
        """
        Return True if label suffix matches
        """
        suffix = DNSLabel(suffix)
        return DNSLabel(self.label[-len(suffix.label) :]) == suffix

    def stripSuffix(self, suffix):
        """
        Strip suffix from label
        """
        suffix = DNSLabel(suffix)
        if self.matchSuffix(suffix):
            return DNSLabel(self.label[: -len(suffix.label)])
        else:
            return self

    @property
    def idna(self) -> str:
        return ".".join([s.decode("idna") for s in self.label]) + "."

    def _decode(self, s):
        if set(s).issubset(LDH):
            # All chars in LDH
            return s.decode()
        else:
            # Need to encode
            return "".join([(chr(c) if (c in LDH) else "\\%03d" % c) for c in s])

    def __str__(self):
        return ".".join([self._decode(bytearray(s)) for s in self.label]) + "."

    def __repr__(self):
        return f"<DNSLabel: '{self}'>"

    def __hash__(self):
        return hash(tuple(map(lambda x: x.lower(), self.label)))

    def __ne__(self, other):
        return not self == other

    def __eq__(self, other):
        if type(other) != DNSLabel:
            return self.__eq__(DNSLabel(other))
        else:
            return [l.lower() for l in self.label] == [l.lower() for l in other.label]

    def __len__(self):
        return len(b".".join(self.label))


DNSLabelCreateTypes = Union[List[bytes], Tuple[bytes, ...], str, bytes, DNSLabel, None]


class DNSBuffer(Buffer):
    """Extends Buffer to provide DNS name encoding/decoding (with caching)

    Attributes:
        data: buffer data
        names: cached labels

    ```pycon
    >>> b = DNSBuffer()
    >>> b.encode_name(b'aaa.bbb.ccc.')
    >>> len(b)
    13
    >>> b.encode_name(b'aaa.bbb.ccc.')
    >>> len(b)
    15
    >>> b.encode_name(b'xxx.yyy.zzz')
    >>> len(b)
    28
    >>> b.encode_name(b'zzz.xxx.bbb.ccc.')
    >>> len(b)
    38
    >>> b.encode_name(b'aaa.xxx.bbb.ccc')
    >>> len(b)
    44
    >>> b.offset = 0
    >>> print(b.decode_name())
    aaa.bbb.ccc.
    >>> print(b.decode_name())
    aaa.bbb.ccc.
    >>> print(b.decode_name())
    xxx.yyy.zzz.
    >>> print(b.decode_name())
    zzz.xxx.bbb.ccc.
    >>> print(b.decode_name())
    aaa.xxx.bbb.ccc.

    >>> b = DNSBuffer()
    >>> b.encode_name([b'a.aa',b'b.bb',b'c.cc'])
    >>> b.offset = 0
    >>> len(b.decode_name().label)
    3

    >>> b = DNSBuffer()
    >>> b.encode_name_nocompress(b'aaa.bbb.ccc.')
    >>> len(b)
    13
    >>> b.encode_name_nocompress(b'aaa.bbb.ccc.')
    >>> len(b)
    26
    >>> b.offset = 0
    >>> print(b.decode_name())
    aaa.bbb.ccc.
    >>> print(b.decode_name())
    aaa.bbb.ccc.

    ```
    """

    def __init__(self, data=b"") -> None:
        """
        Args:
            data: initial data
        """

        super().__init__(data)
        self.names: Dict[Tuple[bytes, ...], int] = {}
        return

    def decode_name(self, last=-1) -> DNSLabel:
        """Decode label at current offset in buffer

        Follows pointers to cached elements where necessary
        """
        label: List[bytes] = []
        done = False
        while not done:
            length = self.unpack_one("!B")
            if get_bits(length, 6, 2) == 3:
                # Pointer
                self.offset -= 1
                pointer = get_bits(self.unpack_one("!H"), 0, 14)
                save = self.offset
                if last == save:
                    raise BufferError(
                        f"Recursive pointer in DNSLabel [offset={self.offset},pointer={pointer},length={len(self.data)}]"
                    )
                if pointer < self.offset:
                    self.offset = pointer
                else:
                    # Pointer can't point forwards
                    raise BufferError(
                        f"Invalid pointer in DNSLabel [offset={self.offset},pointer={pointer},length={len(self.data)}]"
                    )
                label.extend(self.decode_name(save).label)
                self.offset = save
                done = True
            else:
                if length > 0:
                    l = self.get(length)
                    try:
                        l.decode()
                    except UnicodeDecodeError:
                        raise BufferError(f"Invalid label {l!r}")
                    label.append(l)
                else:
                    done = True
        return DNSLabel(label)

    def encode_name(self, name: DNSLabelCreateTypes) -> None:
        """Encode label and store at end of the buffer

        (compressing cached elements where needed) and store elements in 'names' dict
        """
        if not isinstance(name, DNSLabel):
            name = DNSLabel(name)
        if len(name) > 253:
            raise DNSLabelError(f"Domain label too long: {name!r}")
        name = list(name.label)
        while name:
            if tuple(name) in self.names:
                # Cached - set pointer
                pointer = self.names[tuple(name)]
                pointer = set_bits(pointer, 3, 14, 2)
                self.pack("!H", pointer)
                return
            else:
                self.names[tuple(name)] = self.offset
                element = name.pop(0)
                if len(element) > 63:
                    raise DNSLabelError(f"Label component too long: {element!r}")
                self.append_with_length("!B", element)
        self.append(b"\x00")
        return

    def encode_name_nocompress(self, name: DNSLabelCreateTypes) -> None:
        """Encode and store label with no compression

        This is needed for `RRSIG`
        """
        if not isinstance(name, DNSLabel):
            name = DNSLabel(name)
        if len(name) > 253:
            raise DNSLabelError(f"Domain label too long: {name!r}")
        for element in name.label:
            if len(element) > 63:
                raise DNSLabelError(f"Label component too long: {element!r}")
            self.append_with_length("!B", element)
        self.append(b"\x00")
        return


if __name__ == "__main__":
    import doctest, sys

    sys.exit(0 if doctest.testmod().failed == 0 else 1)
