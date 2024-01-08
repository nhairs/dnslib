"""Basic bit mainpulation utilities"""

FILTER = bytearray([(i < 32 or i > 127) and 46 or i for i in range(256)])


def hexdump(src: bytes, length: int = 16, prefix: str = "") -> str:
    """Format a pretty hexdump of a byte string

    ```pycon
    >>> print(hexdump(b"abcd" * 4))
    0000  61 62 63 64 61 62 63 64  61 62 63 64 61 62 63 64  abcdabcd abcdabcd

    >>> print(hexdump(bytearray(range(48))))
    0000  00 01 02 03 04 05 06 07  08 09 0a 0b 0c 0d 0e 0f  ........ ........
    0010  10 11 12 13 14 15 16 17  18 19 1a 1b 1c 1d 1e 1f  ........ ........
    0020  20 21 22 23 24 25 26 27  28 29 2a 2b 2c 2d 2e 2f   !"#$%&' ()*+,-./

    ```

    """
    n = 0
    left = length // 2
    right = length - left
    result = []
    src = bytearray(src)
    while src:
        s, src = src[:length], src[length:]
        l, r = s[:left], s[left:]
        hexa = "%-*s" % (left * 3, " ".join(["%02x" % x for x in l]))
        hexb = "%-*s" % (right * 3, " ".join(["%02x" % x for x in r]))
        lf = l.translate(FILTER)
        rf = r.translate(FILTER)
        result.append(f"{prefix}{n:04x}  {hexa} {hexb} {lf.decode()} {rf.decode()}")
        n += length
    return "\n".join(result)


def get_bits(data: int, offset: int, bits: int = 1) -> int:
    """Get specified bits from integer

    ```pycon
    >>> bin(get_bits(0b0011100,2))
    '0b1'
    >>> bin(get_bits(0b0011100,0,4))
    '0b1100'

    ```
    """
    mask = ((1 << bits) - 1) << offset
    return (data & mask) >> offset


def set_bits(data: int, value: int, offset: int, bits: int = 1) -> int:
    """
    Set specified bits in integer

    ```pycon
    >>> bin(set_bits(0,0b1010,0,4))
    '0b1010'
    >>> bin(set_bits(0,0b1010,3,4))
    '0b1010000'

    ```
    """
    mask = ((1 << bits) - 1) << offset
    clear = 0xFFFF ^ mask
    return (data & clear) | ((value << offset) & mask)


def binary(n: int, count: int = 16, reverse: bool = False) -> str:
    """Convert an integer to a binary string

    (only difference from built-in `bin` is that this function returns a fixed
    width string and can optionally be reversed

    ```pycon
    >>> binary(6789)
    '0001101010000101'
    >>> binary(6789,8)
    '10000101'
    >>> binary(6789,reverse=True)
    '1010000101011000'

    ```
    """
    bits = [str((n >> y) & 1) for y in range(count - 1, -1, -1)]
    if reverse:
        bits.reverse()
    return "".join(bits)


if __name__ == "__main__":
    import doctest, sys

    sys.exit(0 if doctest.testmod().failed == 0 else 1)
